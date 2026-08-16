"""Deterministic global-catalog duplicate review and merge operations.

The candidate scanner deliberately uses bounded groups rather than a Cartesian
comparison. Merges retain the losing Product as an inactive redirect because
campaign and matching history hold product foreign keys as evidence.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations
from typing import Any, Iterable
from urllib.parse import urlparse
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Brand,
    CampaignItem,
    CatalogQualityDecision,
    Market,
    MarketProduct,
    MatchingSuggestion,
    PlatformAdmin,
    PlatformAuditLog,
    Product,
    ProductAlias,
    ProductImage,
)
from app.services.catalog import normalize_alias
from app.services.catalog_matching import canonical_name_key, canonical_package_key
from app.services.product_identity import normalize_barcode, normalize_product_identity, normalize_words
from app.services.product_normalization import normalize_package_type

QUALITY_STATES = frozenset(
    {
        "exact_duplicate",
        "strong_candidate",
        "barcode_conflict",
        "identity_conflict",
        "alias_conflict",
        "ignored",
    }
)
MAX_SCAN_PRODUCTS = 1000
MAX_SCAN_DECISIONS = 5000
MAX_BUCKET_MEMBERS = 50
MAX_DETECTED_CANDIDATES = 2000
MAX_COLLISION_CANDIDATES = 100
_SAFE_IMAGE_STATUSES = {"excellent", "good"}


@dataclass(frozen=True)
class CandidateBuildResult:
    items: list[dict[str, Any]]
    truncated: bool


def ordered_product_pair(product_a_id: UUID, product_b_id: UUID) -> tuple[UUID, UUID]:
    """Return the storage/API ordering for a product pair."""
    if product_a_id == product_b_id:
        raise ValueError("A catalog quality decision requires two different products.")
    return (
        (product_a_id, product_b_id)
        if str(product_a_id) < str(product_b_id)
        else (product_b_id, product_a_id)
    )


def product_brief(product: Product) -> dict[str, Any]:
    """Small, stable product representation used by quality candidates."""
    primary_image = next(
        (image for image in product.images if image.is_primary),
        None,
    )
    image_url = None
    if primary_image is not None and primary_image.storage_key:
        image_url = f"/api/catalog/shared/{product.id}/image/content"
    elif (
        primary_image is not None
        and primary_image.url
        and urlparse(primary_image.url).scheme in {"http", "https"}
    ):
        image_url = primary_image.url
    return {
        "id": str(product.id),
        "name": product.name,
        "brand_name": product.brand.name if product.brand else None,
        "package_size": product.package_size,
        "package_type": product.package_type,
        "barcode": product.barcode,
        "image_url": image_url,
    }


def _brand_keys(product: Product) -> set[str]:
    if product.brand is None:
        return set()
    values = {normalize_words(product.brand.name)}
    values.update(
        alias.normalized_alias
        for alias in product.brand.aliases
        if alias.normalized_alias
    )
    return {value for value in values if value}


def _brand_relation(left: Product, right: Product) -> bool | None:
    left_keys = _brand_keys(left)
    right_keys = _brand_keys(right)
    if not left_keys and not right_keys:
        return True
    if not left_keys or not right_keys:
        return None
    return bool(left_keys.intersection(right_keys))


def _name_keys(product: Product) -> set[str]:
    brand_name = product.brand.name if product.brand else None
    values = {canonical_name_key(product.name, brand_name)}
    values.update(
        canonical_name_key(alias.alias, brand_name)
        for alias in product.aliases
        if alias.alias
    )
    return {value for value in values if value}


def _alias_keys(product: Product) -> set[str]:
    """Persisted aliases only; canonical names have their own identity groups."""
    values = {
        alias.normalized_alias or normalize_alias(alias.alias)
        for alias in product.aliases
        if alias.alias
    }
    return {value for value in values if value}


def _package_identity(product: Product) -> tuple[str | None, str | None]:
    return (
        canonical_package_key(
            amount=product.package_amount,
            unit=product.package_unit,
            package_size=product.package_size,
            fallback_name=product.name,
        ),
        normalize_package_type(product.package_type_canonical or product.package_type),
    )


def _new_evidence() -> dict[str, set[str]]:
    return {
        "signals": set(),
        "barcodes": set(),
        "aliases": set(),
        "ambiguous_aliases": set(),
    }


def _record_bucket(
    bucket: Iterable[Product],
    *,
    signal: str,
    value: str | None,
    evidence_by_pair: dict[tuple[UUID, UUID], dict[str, set[str]]],
    max_candidates: int,
    ambiguous_alias: bool = False,
) -> bool:
    """Record a bounded set of pair evidence and return whether it was capped."""
    unique = {product.id: product for product in bucket}
    members = sorted(unique.values(), key=lambda product: str(product.id))
    truncated = len(members) > MAX_BUCKET_MEMBERS
    members = members[:MAX_BUCKET_MEMBERS]
    for left, right in combinations(members, 2):
        pair = ordered_product_pair(left.id, right.id)
        if pair not in evidence_by_pair and len(evidence_by_pair) >= max_candidates:
            return True
        evidence = evidence_by_pair.setdefault(pair, _new_evidence())
        evidence["signals"].add(signal)
        if signal == "barcode" and value:
            evidence["barcodes"].add(value)
        if signal == "alias" and value:
            evidence["aliases"].add(value)
            if ambiguous_alias:
                evidence["ambiguous_aliases"].add(value)
    return truncated


def _candidate_for_pair(
    left: Product,
    right: Product,
    evidence: dict[str, set[str]],
    *,
    ignored: bool,
) -> dict[str, Any]:
    shared_name = bool(_name_keys(left).intersection(_name_keys(right)))
    package_left, package_type_left = _package_identity(left)
    package_right, package_type_right = _package_identity(right)
    package_conflict = bool(
        (package_left and package_right and package_left != package_right)
        or (
            package_type_left
            and package_type_right
            and package_type_left != package_type_right
        )
    )
    brand_relation = _brand_relation(left, right)
    same_barcode = "barcode" in evidence["signals"]
    explicit_barcode_mismatch = bool(
        left.barcode
        and right.barcode
        and normalize_barcode(left.barcode) != normalize_barcode(right.barcode)
    )
    blockers: list[str] = []
    warnings: list[str] = []

    if brand_relation is False:
        blockers.append("Global brands do not resolve through a shared brand alias.")
    elif brand_relation is None:
        warnings.append("One product has no resolvable global brand; verify the winner.")
    if package_conflict:
        blockers.append("Canonical package amount, unit, or type differs.")
    elif not package_left or not package_right:
        warnings.append("One product has incomplete structured package data.")
    if not shared_name:
        blockers.append("Canonical names and aliases do not resolve to the same product identity.")
    if same_barcode and (package_conflict or brand_relation is False or not shared_name):
        blockers.append("The normalized barcode resolves to materially different product identities.")
    if evidence["ambiguous_aliases"]:
        blockers.append("A shared alias resolves to more than two active global products.")
    if explicit_barcode_mismatch:
        warnings.append(
            "Explicit barcodes differ; merge requires confirm_barcode_mismatch=true."
        )

    signals = evidence["signals"]
    if same_barcode and (
        package_conflict or brand_relation is False or not shared_name
    ):
        state_name, severity = "barcode_conflict", "critical"
    elif evidence["ambiguous_aliases"] or (
        "alias" in signals
        and (package_conflict or brand_relation is False or not shared_name)
    ):
        state_name, severity = "alias_conflict", "high"
    elif package_conflict or brand_relation is False:
        state_name, severity = "identity_conflict", "high"
    elif same_barcode or "identity" in signals:
        state_name, severity = "exact_duplicate", "high"
    else:
        state_name, severity = "strong_candidate", "medium"

    matching_fields: list[str] = []
    if evidence["barcodes"]:
        matching_fields.extend(
            f"normalized barcode: {barcode}"
            for barcode in sorted(evidence["barcodes"])
        )
    if "identity" in signals:
        matching_fields.append("canonical name + equivalent brand + package")
    if "name_brand" in signals:
        matching_fields.append("canonical name + brand")
    matching_fields.extend(
        f"shared alias: {alias}" for alias in sorted(evidence["aliases"])
    )

    if state_name == "exact_duplicate":
        reason = "Same normalized barcode and canonical product identity."
    elif state_name == "barcode_conflict":
        reason = "Same normalized barcode with a material identity conflict."
    elif state_name == "alias_conflict":
        reason = "An alias resolves to incompatible global products."
    elif state_name == "identity_conflict":
        reason = "Canonical identity evidence conflicts with package or brand data."
    else:
        reason = "Canonical name, brand, package, or alias evidence suggests a duplicate."

    if ignored:
        state_name = "ignored"
        severity = "low"
        blockers = []
        warnings = [*warnings, "This pair was previously marked as not duplicate."]
        reason = "Previously marked as not duplicate by a platform administrator."

    return {
        "id": f"{left.id}:{right.id}",
        "product_a": product_brief(left),
        "product_b": product_brief(right),
        "state": state_name,
        "reason": reason,
        "matching_fields": matching_fields,
        "severity": severity,
        "merge_allowed": not blockers and not ignored,
        "blockers": blockers,
        "warnings": warnings,
    }


def build_quality_candidates(
    products: Iterable[Product],
    *,
    ignored_pairs: set[tuple[UUID, UUID]] | None = None,
    include_ignored: bool = False,
    max_candidates: int = MAX_DETECTED_CANDIDATES,
) -> CandidateBuildResult:
    """Build deterministic candidates from loaded active global Product objects.

    This helper is intentionally pure so callers/tests can exercise the
    grouping rules without a database. Groups are capped before pair expansion.
    """
    product_rows = list(products)
    by_id = {product.id: product for product in product_rows}
    evidence_by_pair: dict[tuple[UUID, UUID], dict[str, set[str]]] = {}
    barcode_groups: dict[str, list[Product]] = defaultdict(list)
    identity_groups: dict[tuple[str, str, str, str], list[Product]] = defaultdict(list)
    name_brand_groups: dict[tuple[str, str], list[Product]] = defaultdict(list)
    alias_groups: dict[str, list[Product]] = defaultdict(list)
    canonical_alias_name_groups: dict[str, list[Product]] = defaultdict(list)

    for product in product_rows:
        barcode = normalize_barcode(product.barcode)
        if barcode:
            barcode_groups[barcode].append(product)

        package_key, package_type = _package_identity(product)
        name_keys = _name_keys(product)
        brand_keys = _brand_keys(product) or {""}
        if package_key:
            for name_key in name_keys:
                for brand_key in brand_keys:
                    identity_groups[
                        (name_key, brand_key, package_key, package_type or "")
                    ].append(product)
        for name_key in name_keys:
            for brand_key in brand_keys:
                name_brand_groups[(name_key, brand_key)].append(product)
        canonical_alias_name = normalize_alias(product.name)
        if canonical_alias_name:
            canonical_alias_name_groups[canonical_alias_name].append(product)
        for alias_key in _alias_keys(product):
            alias_groups[alias_key].append(product)

    truncated = False
    for barcode, bucket in barcode_groups.items():
        if len({product.id for product in bucket}) > 1:
            truncated = _record_bucket(
                bucket,
                signal="barcode",
                value=barcode,
                evidence_by_pair=evidence_by_pair,
                max_candidates=max_candidates,
            ) or truncated
    for bucket in identity_groups.values():
        if len({product.id for product in bucket}) > 1:
            truncated = _record_bucket(
                bucket,
                signal="identity",
                value=None,
                evidence_by_pair=evidence_by_pair,
                max_candidates=max_candidates,
            ) or truncated
    for bucket in name_brand_groups.values():
        if len({product.id for product in bucket}) > 1:
            truncated = _record_bucket(
                bucket,
                signal="name_brand",
                value=None,
                evidence_by_pair=evidence_by_pair,
                max_candidates=max_candidates,
            ) or truncated
    for alias_key, alias_bucket in alias_groups.items():
        # Only persisted aliases introduce alias evidence. Canonical product
        # names participate here solely as an alias resolution target.
        bucket = [
            *alias_bucket,
            *canonical_alias_name_groups.get(alias_key, ()),
        ]
        distinct_count = len({product.id for product in bucket})
        if distinct_count > 1:
            truncated = _record_bucket(
                bucket,
                signal="alias",
                value=alias_key,
                ambiguous_alias=distinct_count > 2,
                evidence_by_pair=evidence_by_pair,
                max_candidates=max_candidates,
            ) or truncated

    ignored_pairs = ignored_pairs or set()
    candidates = [
        _candidate_for_pair(
            by_id[pair[0]],
            by_id[pair[1]],
            evidence,
            ignored=pair in ignored_pairs,
        )
        for pair, evidence in evidence_by_pair.items()
    ]
    if not include_ignored:
        candidates = [candidate for candidate in candidates if candidate["state"] != "ignored"]
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    candidates.sort(
        key=lambda candidate: (
            severity_order.get(candidate["severity"], 9),
            candidate["state"],
            candidate["product_a"]["name"].casefold(),
            candidate["product_b"]["name"].casefold(),
            candidate["id"],
        )
    )
    return CandidateBuildResult(items=candidates, truncated=truncated)


def active_global_product_conditions() -> tuple[Any, ...]:
    """Predicates for a current canonical global product (never a tombstone)."""
    return (
        Product.is_global.is_(True),
        Product.market_id.is_(None),
        Product.is_active.is_(True),
        Product.merged_into_product_id.is_(None),
    )


async def scan_catalog_quality_candidates(
    session: AsyncSession,
    *,
    state_name: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Return a page from a bounded deterministic global-catalog scan."""
    if state_name is not None and state_name not in QUALITY_STATES:
        raise HTTPException(status_code=422, detail="Unknown catalog quality state.")

    rows = list(
        (
            await session.scalars(
                select(Product)
                .options(
                    selectinload(Product.aliases),
                    selectinload(Product.images),
                    selectinload(Product.brand).selectinload(Brand.aliases),
                )
                .where(*active_global_product_conditions())
                .order_by(Product.id)
                .limit(MAX_SCAN_PRODUCTS + 1)
            )
        ).unique()
    )
    products_truncated = len(rows) > MAX_SCAN_PRODUCTS
    products = rows[:MAX_SCAN_PRODUCTS]
    decisions = list(
        (
            await session.scalars(
                select(CatalogQualityDecision)
                .where(CatalogQualityDecision.decision == "ignored")
                .order_by(CatalogQualityDecision.created_at.desc())
                .limit(MAX_SCAN_DECISIONS + 1)
            )
        ).all()
    )
    decisions_truncated = len(decisions) > MAX_SCAN_DECISIONS
    ignored_pairs = {
        ordered_product_pair(decision.product_a_id, decision.product_b_id)
        for decision in decisions[:MAX_SCAN_DECISIONS]
    }
    built = build_quality_candidates(
        products,
        ignored_pairs=ignored_pairs,
        include_ignored=state_name == "ignored",
    )
    items = built.items
    if state_name:
        items = [item for item in items if item["state"] == state_name]
    total = len(items)
    return {
        "items": items[offset : offset + limit],
        "total": total,
        "limit": limit,
        "offset": offset,
        "truncated": products_truncated or decisions_truncated or built.truncated,
    }


def _global_collision_conditions(
    *,
    exclude_product_id: UUID | None = None,
) -> list[Any]:
    conditions = list(active_global_product_conditions())
    if exclude_product_id is not None:
        conditions.append(Product.id != exclude_product_id)
    return conditions


def _barcode_condition(raw_barcode: str, normalized_barcode: str) -> Any:
    if normalized_barcode.startswith("raw:"):
        return func.lower(func.trim(Product.barcode)) == normalized_barcode[4:]
    compact_barcode = func.regexp_replace(Product.barcode, "[^0-9]", "", "g")
    return or_(
        Product.barcode == raw_barcode.strip(),
        Product.barcode == normalized_barcode,
        and_(
            Product.barcode.op("!~*")("[[:alpha:]]"),
            compact_barcode == normalized_barcode,
        ),
    )


def _requested_alias_keys(
    name: str,
    aliases: Iterable[Any] | None,
) -> set[str]:
    values = {normalize_alias(name)}
    for value in aliases or ():
        alias = value if isinstance(value, str) else getattr(value, "alias", None)
        if alias:
            normalized = normalize_alias(alias)
            if normalized:
                values.add(normalized)
    return {value for value in values if value}


def _brand_keys_for_brand(brand: Brand | None) -> set[str]:
    if brand is None:
        return set()
    values = {normalize_words(brand.name)}
    values.update(alias.normalized_alias for alias in brand.aliases if alias.normalized_alias)
    return {value for value in values if value}


async def ensure_global_product_collision_free(
    session: AsyncSession,
    *,
    name: str,
    barcode: str | None,
    brand_id: UUID | None,
    package_size: str | None,
    package_type: str | None,
    package_amount: Any,
    package_unit: str | None,
    package_type_canonical: str | None,
    aliases: Iterable[Any] | None = None,
    exclude_product_id: UUID | None = None,
) -> None:
    """Reject deterministic global collisions without an all-catalog Python scan.

    Barcode and aliases are queried directly. Structured identity uses the same
    canonical name/package rules as Phase 28B and a bounded token prefilter.
    """
    conditions = _global_collision_conditions(exclude_product_id=exclude_product_id)
    normalized_barcode = normalize_barcode(barcode)
    if normalized_barcode and barcode:
        barcode_rows = list(
            (
                await session.scalars(
                    select(Product)
                    .options(
                        selectinload(Product.aliases),
                        selectinload(Product.brand).selectinload(Brand.aliases),
                    )
                    .where(
                        *conditions,
                        Product.barcode.is_not(None),
                        _barcode_condition(barcode, normalized_barcode),
                    )
                    .order_by(Product.id)
                    .limit(MAX_COLLISION_CANDIDATES + 1)
                )
            ).unique()
        )
        if len(barcode_rows) > MAX_COLLISION_CANDIDATES:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Global barcode collision search is truncated; resolve catalog quality first.",
            )
        if any(normalize_barcode(row.barcode) == normalized_barcode for row in barcode_rows):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A current global product already uses this normalized barcode/SKU.",
            )

    alias_keys = _requested_alias_keys(name, aliases)
    if alias_keys:
        alias_rows = list(
            (
                await session.scalars(
                    select(Product)
                    .join(ProductAlias, ProductAlias.product_id == Product.id)
                    .where(
                        *conditions,
                        ProductAlias.normalized_alias.in_(alias_keys),
                    )
                    .order_by(Product.id)
                    .limit(MAX_COLLISION_CANDIDATES + 1)
                )
            ).unique()
        )
        if len(alias_rows) > MAX_COLLISION_CANDIDATES:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Global alias collision search is truncated; resolve catalog quality first.",
            )
        if alias_rows:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A product name or alias already resolves to another current global product.",
            )

    requested_brand = None
    if brand_id is not None:
        requested_brand = await session.scalar(
            select(Brand)
            .options(selectinload(Brand.aliases))
            .where(
                Brand.id == brand_id,
                Brand.is_global.is_(True),
                Brand.market_id.is_(None),
                Brand.is_active.is_(True),
            )
        )
    requested_brand_name = requested_brand.name if requested_brand else None
    request_name_keys = {
        canonical_name_key(name, requested_brand_name),
        *(
            canonical_name_key(
                value if isinstance(value, str) else getattr(value, "alias", ""),
                requested_brand_name,
            )
            for value in aliases or ()
        ),
    }
    request_name_keys.discard("")
    request_package = canonical_package_key(
        amount=package_amount,
        unit=package_unit,
        package_size=package_size,
        fallback_name=name,
    )
    request_package_type = normalize_package_type(
        package_type_canonical or package_type
    )
    identity = normalize_product_identity(name, package_size=package_size)
    tokens = sorted(
        {token for token in identity.search_tokens if len(token) >= 3},
        key=lambda token: (-len(token), token),
    )[:4]
    name_conditions: list[Any] = [Product.name.ilike(name.strip())]
    if alias_keys:
        name_conditions.append(Product.aliases.any(ProductAlias.normalized_alias.in_(alias_keys)))
    if tokens:
        normalized_name = func.translate(
            func.lower(Product.name),
            "çğıöşü",
            "cgiosu",
        )
        name_conditions.extend(normalized_name.contains(token) for token in tokens)
    structured_rows = list(
        (
            await session.scalars(
                select(Product)
                .options(
                    selectinload(Product.aliases),
                    selectinload(Product.brand).selectinload(Brand.aliases),
                )
                .where(*conditions, or_(*name_conditions))
                .order_by(Product.id)
                .limit(MAX_COLLISION_CANDIDATES + 1)
            )
        ).unique()
    )
    if len(structured_rows) > MAX_COLLISION_CANDIDATES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Global identity collision search is truncated; resolve catalog quality first.",
        )

    requested_brand_keys = _brand_keys_for_brand(requested_brand)
    for candidate in structured_rows:
        if not request_name_keys.intersection(_name_keys(candidate)):
            continue
        candidate_package, candidate_package_type = _package_identity(candidate)
        package_matches = (
            request_package == candidate_package
            if request_package and candidate_package
            else not request_package and not candidate_package
        )
        type_matches = not (
            request_package_type
            and candidate_package_type
            and request_package_type != candidate_package_type
        )
        if not package_matches or not type_matches:
            continue
        candidate_brand_keys = _brand_keys(candidate)
        if (
            requested_brand_keys
            and candidate_brand_keys
            and not requested_brand_keys.intersection(candidate_brand_keys)
        ):
            detail = "Canonical name/package collides with a different global brand."
        else:
            detail = "A current global product already has this canonical identity."
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _merge_conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _validate_merge_products(source: Product, target: Product) -> None:
    if source.id == target.id:
        raise _merge_conflict("Source and target product must be different.")
    for label, product in (("Source", source), ("Target", target)):
        if not product.is_global or product.market_id is not None:
            raise _merge_conflict(f"{label} product must be a global catalog product.")
        if product.merged_into_product_id is not None:
            if label == "Source":
                raise _merge_conflict(
                    f"Source product is already merged into {product.merged_into_product_id}."
                )
            raise _merge_conflict("Target product is already a merged redirect.")
        if not product.is_active:
            raise _merge_conflict(f"{label} product is inactive and cannot participate in a merge.")


async def _load_merge_products(
    session: AsyncSession,
    *,
    source_product_id: UUID,
    target_product_id: UUID,
    lock: bool,
) -> tuple[Product, Product]:
    if source_product_id == target_product_id:
        raise _merge_conflict("Source and target product must be different.")
    statement = (
        select(Product)
        .options(
            selectinload(Product.aliases),
            selectinload(Product.images),
            selectinload(Product.brand).selectinload(Brand.aliases),
        )
        .where(Product.id.in_((source_product_id, target_product_id)))
        .order_by(Product.id)
    )
    if lock:
        statement = statement.with_for_update()
    rows = list((await session.scalars(statement)).unique())
    by_id = {product.id: product for product in rows}
    source = by_id.get(source_product_id)
    target = by_id.get(target_product_id)
    if source is None or target is None:
        raise HTTPException(status_code=404, detail="Global product not found.")
    _validate_merge_products(source, target)
    return source, target


async def _load_merge_related_rows(
    session: AsyncSession,
    *,
    source_product_id: UUID,
    target_product_id: UUID,
    lock: bool,
) -> tuple[list[ProductAlias], list[ProductImage], list[MarketProduct]]:
    product_ids = (source_product_id, target_product_id)
    aliases_statement = (
        select(ProductAlias)
        .where(ProductAlias.product_id.in_(product_ids))
        .order_by(ProductAlias.product_id, ProductAlias.id)
    )
    images_statement = (
        select(ProductImage)
        .where(ProductImage.product_id.in_(product_ids))
        .order_by(ProductImage.product_id, ProductImage.id)
    )
    market_statement = (
        select(MarketProduct)
        .where(
            or_(
                MarketProduct.product_id.in_(product_ids),
                MarketProduct.legacy_product_id == source_product_id,
            )
        )
        .order_by(MarketProduct.market_id, MarketProduct.id)
    )
    if lock:
        aliases_statement = aliases_statement.with_for_update()
        images_statement = images_statement.with_for_update()
        market_statement = market_statement.with_for_update()
    aliases = list((await session.scalars(aliases_statement)).all())
    images = list((await session.scalars(images_statement)).all())
    market_rows = list((await session.scalars(market_statement)).all())
    return aliases, images, market_rows


async def _historical_reference_counts(
    session: AsyncSession,
    product_id: UUID,
) -> dict[str, int]:
    campaign_items = int(
        await session.scalar(
            select(func.count(CampaignItem.id)).where(CampaignItem.product_id == product_id)
        )
        or 0
    )
    matching_suggestions = int(
        await session.scalar(
            select(func.count(MatchingSuggestion.id)).where(
                MatchingSuggestion.product_id == product_id
            )
        )
        or 0
    )
    return {
        "campaign_items": campaign_items,
        "matching_suggestions": matching_suggestions,
    }


async def _third_product_alias_rows(
    session: AsyncSession,
    *,
    normalized_aliases: set[str],
    source_product_id: UUID,
    target_product_id: UUID,
    lock: bool,
) -> list[ProductAlias]:
    if not normalized_aliases:
        return []
    statement = (
        select(ProductAlias)
        .join(Product, Product.id == ProductAlias.product_id)
        .where(
            *active_global_product_conditions(),
            Product.id.not_in((source_product_id, target_product_id)),
            ProductAlias.normalized_alias.in_(normalized_aliases),
        )
        .order_by(ProductAlias.product_id, ProductAlias.id)
    )
    if lock:
        statement = statement.with_for_update()
    return list((await session.scalars(statement)).all())


def _image_identity(image: ProductImage) -> str | None:
    return image.storage_key or image.url


async def _market_names(
    session: AsyncSession,
    market_ids: set[UUID],
) -> dict[UUID, str]:
    if not market_ids:
        return {}
    rows = await session.execute(
        select(Market.id, Market.name).where(Market.id.in_(market_ids))
    )
    return {market_id: name for market_id, name in rows.all()}


async def _build_merge_preview(
    session: AsyncSession,
    *,
    source: Product,
    target: Product,
    aliases: list[ProductAlias],
    images: list[ProductImage],
    market_rows: list[MarketProduct],
    lock_alias_collisions: bool,
) -> dict[str, Any]:
    source_aliases = [
        alias for alias in aliases if alias.product_id == source.id
    ]
    target_aliases = [
        alias for alias in aliases if alias.product_id == target.id
    ]
    source_images = [image for image in images if image.product_id == source.id]
    target_images = [image for image in images if image.product_id == target.id]
    source_market_rows = [
        row for row in market_rows if row.product_id == source.id
    ]
    target_market_rows = [
        row for row in market_rows if row.product_id == target.id
    ]
    legacy_rows = [
        row for row in market_rows if row.legacy_product_id == source.id
    ]

    source_market_ids = {row.market_id for row in source_market_rows}
    target_market_ids = {row.market_id for row in target_market_rows}
    conflict_market_ids = source_market_ids.intersection(target_market_ids)
    market_names = await _market_names(session, conflict_market_ids)

    target_alias_norms = {
        alias.normalized_alias for alias in target_aliases if alias.normalized_alias
    }
    target_alias_norms.add(normalize_alias(target.name))
    source_alias_norms = {
        alias.normalized_alias for alias in source_aliases if alias.normalized_alias
    }
    merge_alias_normalized = normalize_alias(source.name)
    aliases_to_move = [
        alias
        for alias in source_aliases
        if alias.normalized_alias not in target_alias_norms
    ]
    aliases_to_dedupe = [
        alias
        for alias in source_aliases
        if alias.normalized_alias in target_alias_norms
    ]
    merge_alias_needed = bool(
        merge_alias_normalized
        and merge_alias_normalized not in target_alias_norms
        and merge_alias_normalized not in source_alias_norms
    )
    collision_aliases = {
        *source_alias_norms,
        *target_alias_norms,
        *( {merge_alias_normalized} if merge_alias_needed else set() ),
    }
    third_alias_rows = await _third_product_alias_rows(
        session,
        normalized_aliases=collision_aliases,
        source_product_id=source.id,
        target_product_id=target.id,
        lock=lock_alias_collisions,
    )

    historical_references = await _historical_reference_counts(session, source.id)
    historical_count = sum(historical_references.values())
    target_image_keys = {
        key for image in target_images if (key := _image_identity(image))
    }
    seen_image_keys = set(target_image_keys)
    image_move_ids: list[UUID] = []
    if historical_count == 0:
        for image in source_images:
            key = _image_identity(image)
            if not key or key in seen_image_keys:
                continue
            seen_image_keys.add(key)
            image_move_ids.append(image.id)

    source_name_keys = _name_keys(source)
    target_name_keys = _name_keys(target)
    name_overlap = bool(source_name_keys.intersection(target_name_keys))
    source_package, source_package_type = _package_identity(source)
    target_package, target_package_type = _package_identity(target)
    package_conflict = bool(
        (source_package and target_package and source_package != target_package)
        or (
            source_package_type
            and target_package_type
            and source_package_type != target_package_type
        )
    )
    brand_relation = _brand_relation(source, target)
    barcode_match = bool(
        source.barcode
        and target.barcode
        and normalize_barcode(source.barcode) == normalize_barcode(target.barcode)
    )
    explicit_barcode_mismatch = bool(
        source.barcode
        and target.barcode
        and normalize_barcode(source.barcode) != normalize_barcode(target.barcode)
    )
    blockers: list[str] = []
    warnings: list[str] = []
    if not name_overlap:
        blockers.append("Canonical names and aliases do not resolve to the same product identity.")
    if package_conflict:
        blockers.append("Canonical package amount, unit, or type differs.")
    elif not source_package or not target_package:
        warnings.append("One product has incomplete structured package data.")
    if brand_relation is False:
        blockers.append("Global brands do not resolve through a shared brand alias.")
    elif brand_relation is None:
        warnings.append("One product has no resolvable global brand; verify the winner.")
    if barcode_match and (not name_overlap or package_conflict or brand_relation is False):
        blockers.append("The normalized barcode resolves to materially different product identities.")
    if explicit_barcode_mismatch:
        warnings.append(
            "Explicit barcodes differ; merge requires confirm_barcode_mismatch=true."
        )
    if conflict_market_ids:
        blockers.append(
            "One or more markets already adopt both products; override data requires manual resolution."
        )
    if legacy_rows:
        blockers.append(
            "A market product has a legacy_product_id pointing to the source product and requires manual review."
        )
    if third_alias_rows:
        blockers.append(
            "Moving aliases would leave an alias resolving to another active global product."
        )

    if historical_count:
        warnings.append(
            "Source images remain on the redirect because campaign or matching history references it."
        )
    elif source_images and len(image_move_ids) < len(source_images):
        warnings.append(
            "Duplicate or unidentifiable source images remain on the redirect for provenance."
        )

    operational_source_rows = [
        row for row in source_market_rows if row.is_active
    ]
    return {
        "source": product_brief(source),
        "target": product_brief(target),
        "market_adoptions": {
            "source_count": len(operational_source_rows),
            "target_count": len(target_market_rows),
            "inactive_source_count": len(source_market_rows) - len(operational_source_rows),
            "conflict_markets": [
                {"id": str(market_id), "name": market_names.get(market_id)}
                for market_id in sorted(conflict_market_ids, key=str)
            ],
            "legacy_reference_count": len(legacy_rows),
        },
        "aliases": {
            "move_count": len(aliases_to_move),
            "deduplicated_count": len(aliases_to_dedupe),
            "merge_alias_added": merge_alias_needed,
        },
        "images": {
            "source_count": len(source_images),
            "target_count": len(target_images),
            "move_count": len(image_move_ids),
            "retained_count": len(source_images) - len(image_move_ids),
            "historical_retention": bool(historical_count),
        },
        "historical_references": historical_references,
        "blockers": blockers,
        "warnings": warnings,
        "can_merge": not blockers,
        "requires_barcode_confirmation": explicit_barcode_mismatch,
        "_operation": {
            "alias_move_ids": [alias.id for alias in aliases_to_move],
            "alias_dedupe_ids": [alias.id for alias in aliases_to_dedupe],
            "merge_alias_needed": merge_alias_needed,
            "image_move_ids": image_move_ids,
            "operational_market_product_ids": [
                row.id for row in operational_source_rows
            ],
        },
    }


async def preview_global_product_merge(
    session: AsyncSession,
    *,
    source_product_id: UUID,
    target_product_id: UUID,
) -> dict[str, Any]:
    """Build a read-only impact preview. Mutation revalidates it under locks."""
    source, target = await _load_merge_products(
        session,
        source_product_id=source_product_id,
        target_product_id=target_product_id,
        lock=False,
    )
    aliases, images, market_rows = await _load_merge_related_rows(
        session,
        source_product_id=source.id,
        target_product_id=target.id,
        lock=False,
    )
    preview = await _build_merge_preview(
        session,
        source=source,
        target=target,
        aliases=aliases,
        images=images,
        market_rows=market_rows,
        lock_alias_collisions=False,
    )
    preview.pop("_operation", None)
    return preview


def _first_blocker(preview: dict[str, Any]) -> str | None:
    blockers = preview.get("blockers") or []
    return str(blockers[0]) if blockers else None


async def merge_global_products(
    session: AsyncSession,
    *,
    actor: PlatformAdmin,
    source_product_id: UUID,
    target_product_id: UUID,
    confirm_barcode_mismatch: bool = False,
) -> dict[str, Any]:
    """Atomically redirect a loser global Product to its chosen canonical winner."""
    try:
        # Product IDs are ordered in the SELECT before FOR UPDATE so concurrent
        # A->B, A->C, and B->C attempts acquire their shared rows consistently.
        source, target = await _load_merge_products(
            session,
            source_product_id=source_product_id,
            target_product_id=target_product_id,
            lock=True,
        )
        aliases, images, market_rows = await _load_merge_related_rows(
            session,
            source_product_id=source.id,
            target_product_id=target.id,
            lock=True,
        )
        preview = await _build_merge_preview(
            session,
            source=source,
            target=target,
            aliases=aliases,
            images=images,
            market_rows=market_rows,
            lock_alias_collisions=True,
        )
        blocker = _first_blocker(preview)
        if blocker:
            raise _merge_conflict(blocker)
        if (
            preview["requires_barcode_confirmation"]
            and not confirm_barcode_mismatch
        ):
            raise _merge_conflict(
                "Explicit barcodes differ; confirm_barcode_mismatch=true is required."
            )

        operation = preview["_operation"]
        alias_by_id = {alias.id: alias for alias in aliases}
        for alias_id in operation["alias_dedupe_ids"]:
            alias = alias_by_id[alias_id]
            await session.delete(alias)
        for alias_id in operation["alias_move_ids"]:
            alias_by_id[alias_id].product_id = target.id
        if operation["merge_alias_needed"]:
            session.add(
                ProductAlias(
                    product_id=target.id,
                    alias=source.name,
                    normalized_alias=normalize_alias(source.name),
                    source="product_merge",
                )
            )

        image_by_id = {image.id: image for image in images}
        for image_id in operation["image_move_ids"]:
            image = image_by_id[image_id]
            image.product_id = target.id
            # A loser image is never promoted implicitly; winner image selection
            # remains an explicit platform-admin action.
            image.is_primary = False

        market_by_id = {row.id: row for row in market_rows}
        for market_product_id in operation["operational_market_product_ids"]:
            market_by_id[market_product_id].product_id = target.id

        source.merged_into_product_id = target.id
        source.is_active = False
        # Flatten any prior redirects that pointed at this now-merged source so
        # a chained merge (A->source, source->target) never leaves A's pointer
        # stale on an inactive intermediate tombstone.
        descendant_result = await session.execute(
            Product.__table__.update()
            .where(Product.merged_into_product_id == source.id)
            .values(merged_into_product_id=target.id)
        )
        migration_counts = {
            "redirects_flattened": descendant_result.rowcount or 0,
            "market_adoptions_relinked": len(
                operation["operational_market_product_ids"]
            ),
            "aliases_moved": len(operation["alias_move_ids"]),
            "aliases_deduplicated": len(operation["alias_dedupe_ids"]),
            "merge_alias_added": int(bool(operation["merge_alias_needed"])),
            "images_moved": len(operation["image_move_ids"]),
            "images_retained": preview["images"]["retained_count"],
            "campaign_items_retained": preview["historical_references"]["campaign_items"],
            "matching_suggestions_retained": preview["historical_references"][
                "matching_suggestions"
            ],
        }
        session.add(
            PlatformAuditLog(
                actor_platform_admin_id=actor.id,
                action="catalog_product_merged",
                target_type="product",
                target_id=target.id,
                metadata_={
                    "winner_product_id": str(target.id),
                    "loser_product_id": str(source.id),
                    "migration_counts": migration_counts,
                    "barcode_mismatch_confirmed": bool(
                        preview["requires_barcode_confirmation"]
                    ),
                },
            )
        )
        await session.commit()
    except HTTPException:
        await session.rollback()
        raise
    except IntegrityError as exc:
        await session.rollback()
        raise _merge_conflict(
            "Catalog merge conflicted with a concurrent catalog change; refresh and retry."
        ) from exc
    except Exception:
        await session.rollback()
        raise

    return {
        "winner": product_brief(target),
        "loser": product_brief(source),
        "migration_counts": migration_counts,
        "redirect_product_id": str(target.id),
    }


async def ignore_catalog_quality_candidate(
    session: AsyncSession,
    *,
    actor: PlatformAdmin,
    product_a_id: UUID,
    product_b_id: UUID,
    note: str | None = None,
) -> dict[str, Any]:
    """Persist an idempotent platform-admin 'not duplicate' decision."""
    try:
        product_a_id, product_b_id = ordered_product_pair(
            product_a_id,
            product_b_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None

    try:
        products = list(
            (
                await session.scalars(
                    select(Product)
                    .where(
                        Product.id.in_((product_a_id, product_b_id)),
                        *active_global_product_conditions(),
                    )
                    .order_by(Product.id)
                    .with_for_update()
                )
            ).all()
        )
        if len(products) != 2:
            raise _merge_conflict(
                "Only current active global products can be marked as not duplicate."
            )
        decision = await session.scalar(
            select(CatalogQualityDecision)
            .where(
                CatalogQualityDecision.product_a_id == product_a_id,
                CatalogQualityDecision.product_b_id == product_b_id,
            )
            .with_for_update()
        )
        created = decision is None
        if decision is None:
            decision = CatalogQualityDecision(
                product_a_id=product_a_id,
                product_b_id=product_b_id,
                decision="ignored",
                note=note.strip() if note and note.strip() else None,
                created_by_platform_admin_id=actor.id,
            )
            session.add(decision)
        else:
            decision.decision = "ignored"
            decision.note = note.strip() if note and note.strip() else decision.note
        session.add(
            PlatformAuditLog(
                actor_platform_admin_id=actor.id,
                action=(
                    "catalog_quality_candidate_ignored"
                    if created
                    else "catalog_quality_candidate_ignore_reaffirmed"
                ),
                target_type="catalog_quality_decision",
                target_id=decision.id,
                metadata_={
                    "product_a_id": str(product_a_id),
                    "product_b_id": str(product_b_id),
                },
            )
        )
        await session.commit()
    except HTTPException:
        await session.rollback()
        raise
    except IntegrityError as exc:
        await session.rollback()
        raise _merge_conflict(
            "Catalog quality decision conflicted with another administrator action; refresh and retry."
        ) from exc
    except Exception:
        await session.rollback()
        raise

    return {
        "id": str(decision.id),
        "product_a_id": str(decision.product_a_id),
        "product_b_id": str(decision.product_b_id),
        "decision": decision.decision,
        "note": decision.note,
        "created_at": decision.created_at,
    }
