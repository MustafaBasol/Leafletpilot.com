from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal
from urllib.parse import urlparse
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Brand, BrandAlias, Category, MarketProduct, Product, ProductAlias
from app.services.product_identity import (
    normalize_barcode,
    normalize_product_identity,
    normalize_product_text,
    normalize_words,
)
from app.services.product_normalization import (
    format_package,
    normalize_package_type,
    normalize_package_unit,
    parse_package,
)

MatchType = Literal["exact", "strong", "none", "ambiguous"]
CandidateMatchType = Literal["exact", "strong"]
MAX_MATCH_CANDIDATES = 5
MAX_STRUCTURED_QUERY_ROWS = 100
_SAFE_IMAGE_STATUSES = {"excellent", "good"}


@dataclass(frozen=True)
class CatalogMatchCandidate:
    product: Product
    match_type: CandidateMatchType
    match_reason: str
    already_adopted: bool

    def as_dict(self) -> dict:
        product = self.product
        primary_image = next(
            (
                image
                for image in product.images
                if image.is_primary and image.quality_status in _SAFE_IMAGE_STATUSES
            ),
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
            "product_id": product.id,
            "name": product.name,
            "brand": product.brand.name if product.brand else None,
            "package_size": product.package_size
            or format_package(product.package_amount, product.package_unit),
            "package_type": product.package_type,
            "package_amount": product.package_amount,
            "package_unit": product.package_unit,
            "package_type_canonical": product.package_type_canonical,
            "image_url": image_url,
            "match_type": self.match_type,
            "match_reason": self.match_reason,
            "already_adopted": self.already_adopted,
        }


@dataclass(frozen=True)
class CatalogMatchResult:
    match_type: MatchType
    match_reason: str
    candidates: tuple[CatalogMatchCandidate, ...]
    candidate_count: int

    def as_dict(self) -> dict:
        return {
            "match_type": self.match_type,
            "match_reason": self.match_reason,
            "candidate_count": self.candidate_count,
            "candidates": [candidate.as_dict() for candidate in self.candidates],
        }


async def match_global_products(
    session: AsyncSession,
    *,
    market_id: UUID,
    name: str,
    barcode: str | None = None,
    brand: str | None = None,
    brand_id: UUID | None = None,
    package_size: str | None = None,
    package_type: str | None = None,
    package_amount: Decimal | None = None,
    package_unit: str | None = None,
    package_type_canonical: str | None = None,
) -> CatalogMatchResult:
    """Resolve a bounded, global-only candidate set without fuzzy matching."""
    normalized_barcode = normalize_barcode(barcode)
    if normalized_barcode:
        barcode_products, barcode_count = await _barcode_candidates(
            session,
            raw_barcode=barcode or normalized_barcode,
            normalized_barcode=normalized_barcode,
        )
        if barcode_products:
            return await _result_for_products(
                session,
                market_id=market_id,
                products=barcode_products,
                total=barcode_count,
                evidence_type="exact",
                evidence_reason="exact barcode",
            )

    explicit_brand = bool(brand_id or (brand and brand.strip()))
    brand_ids = await _resolve_global_brand_ids(
        session,
        market_id=market_id,
        brand=brand,
        brand_id=brand_id,
    )
    if explicit_brand and not brand_ids:
        return _none_result()

    request_package_key = canonical_package_key(
        amount=package_amount,
        unit=package_unit,
        package_size=package_size,
        fallback_name=name,
    )
    if request_package_key is None:
        return _none_result()

    products = await _structured_candidates(
        session,
        name=name,
        brand_ids=brand_ids,
    )
    structured_query_truncated = len(products) >= MAX_STRUCTURED_QUERY_ROWS
    request_package_type = normalize_package_type(package_type_canonical or package_type)
    matches: list[Product] = []
    for product in products:
        product_brand = product.brand.name if product.brand else None
        request_name_key = canonical_name_key(name, product_brand)
        candidate_name_keys = {
            canonical_name_key(product.name, product_brand),
            *(canonical_name_key(alias.alias, product_brand) for alias in product.aliases),
        }
        if request_name_key not in candidate_name_keys:
            continue
        product_package_key = canonical_package_key(
            amount=product.package_amount,
            unit=product.package_unit,
            package_size=product.package_size,
            fallback_name=product.name,
        )
        if request_package_key and product_package_key != request_package_key:
            continue
        product_package_type = normalize_package_type(
            product.package_type_canonical or product.package_type
        )
        if (
            request_package_type
            and product_package_type
            and request_package_type != product_package_type
        ):
            continue
        matches.append(product)

    if not matches:
        # A capped prefilter cannot prove that no matching row exists.  Treat
        # this as ambiguous so create mutations require an explicit decision
        # instead of accepting a false-negative advisory result.
        if structured_query_truncated:
            return CatalogMatchResult(
                match_type="ambiguous",
                match_reason="candidate search truncated",
                candidates=(),
                candidate_count=0,
            )
        return _none_result()
    brand_reason = bool(brand_ids)
    package_reason = request_package_key is not None
    if brand_reason and package_reason:
        reason = "canonical name + brand + package"
    elif package_reason:
        reason = "canonical name + package"
    elif brand_reason:
        reason = "canonical name + brand"
    else:
        reason = "canonical name"
    return await _result_for_products(
        session,
        market_id=market_id,
        products=matches,
        total=len(matches),
        evidence_type="strong",
        evidence_reason=reason,
        force_ambiguous=len(brand_ids) > 1 or structured_query_truncated,
        ambiguity_reason=(
            "candidate search truncated" if structured_query_truncated else "ambiguous candidates"
        ),
    )


def canonical_name_key(name: str, brand: str | None = None) -> str:
    identity = normalize_product_identity(name, brand=brand)
    parts = [identity.normalized_product_family]
    if identity.normalized_variant:
        parts.append(identity.normalized_variant)
    if identity.pack_count:
        parts.append(f"{identity.pack_count}x")
    return " ".join(part for part in parts if part)


def canonical_package_key(
    *,
    amount: Decimal | None = None,
    unit: str | None = None,
    package_size: str | None = None,
    fallback_name: str | None = None,
) -> str | None:
    canonical_unit = normalize_package_unit(unit)
    canonical_amount = amount if amount is not None and canonical_unit is not None else None
    if canonical_amount is None:
        parsed_amount, parsed_unit = parse_package(package_size, unit)
        if parsed_amount is not None and parsed_unit is not None:
            canonical_amount, canonical_unit = parsed_amount, parsed_unit
    if (canonical_amount is None or canonical_unit is None) and fallback_name:
        identity = normalize_product_identity(fallback_name)
        if identity.normalized_quantity and identity.normalized_unit:
            canonical_amount = Decimal(identity.normalized_quantity)
            canonical_unit = identity.normalized_unit
    if canonical_amount is None or canonical_unit is None:
        return None
    if canonical_unit == "kg":
        canonical_amount *= Decimal(1000)
        canonical_unit = "g"
    elif canonical_unit == "cl":
        canonical_amount *= Decimal(10)
        canonical_unit = "ml"
    elif canonical_unit == "l":
        canonical_amount *= Decimal(1000)
        canonical_unit = "ml"
    return f"{format(canonical_amount.normalize(), 'f')}:{canonical_unit}"


async def _barcode_candidates(
    session: AsyncSession,
    *,
    raw_barcode: str,
    normalized_barcode: str,
) -> tuple[list[Product], int]:
    if normalized_barcode.startswith("raw:"):
        condition = func.lower(func.trim(Product.barcode)) == normalized_barcode[4:]
    else:
        compact_barcode = func.regexp_replace(Product.barcode, "[^0-9]", "", "g")
        condition = or_(
            Product.barcode == raw_barcode.strip(),
            Product.barcode == normalized_barcode,
            and_(
                Product.barcode.op("!~*")("[[:alpha:]]"),
                compact_barcode == normalized_barcode,
            ),
        )
    scope = (
        *_eligible_global_product_conditions(),
        condition,
    )
    total = int(await session.scalar(select(func.count(Product.id)).where(*scope)) or 0)
    rows = list(
        (
            await session.scalars(
                select(Product)
                .options(selectinload(Product.brand), selectinload(Product.images))
                .where(*scope)
                .order_by(Product.name, Product.id)
                .limit(MAX_MATCH_CANDIDATES)
            )
        ).unique()
    )
    rows = [product for product in rows if normalize_barcode(product.barcode) == normalized_barcode]
    return rows, total


async def _resolve_global_brand_ids(
    session: AsyncSession,
    *,
    market_id: UUID,
    brand: str | None,
    brand_id: UUID | None,
) -> set[UUID]:
    normalized_values: set[str] = set()
    if brand_id is not None:
        scoped_brand = await session.scalar(
            select(Brand)
            .options(selectinload(Brand.aliases))
            .where(
                Brand.id == brand_id,
                Brand.is_active.is_(True),
                or_(
                    and_(Brand.is_global.is_(True), Brand.market_id.is_(None)),
                    and_(Brand.is_global.is_(False), Brand.market_id == market_id),
                ),
            )
        )
        if scoped_brand is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found.")
        if scoped_brand.is_global and scoped_brand.market_id is None:
            return {scoped_brand.id}
        normalized_values.add(normalize_words(scoped_brand.name))
        normalized_values.update(alias.normalized_alias for alias in scoped_brand.aliases)
    if brand and brand.strip():
        normalized_values.add(normalize_words(brand))
    if not normalized_values:
        return set()
    rows = list(
        (
            await session.scalars(
                select(Brand)
                .options(selectinload(Brand.aliases))
                .where(
                    Brand.is_global.is_(True),
                    Brand.market_id.is_(None),
                    Brand.is_active.is_(True),
                    or_(
                        Brand.aliases.any(BrandAlias.normalized_alias.in_(normalized_values)),
                        Brand.name.ilike(brand.strip()) if brand and brand.strip() else False,
                    ),
                )
                .limit(10)
            )
        ).unique()
    )
    return {
        row.id
        for row in rows
        if normalize_words(row.name) in normalized_values
        or any(alias.normalized_alias in normalized_values for alias in row.aliases)
    }


async def _structured_candidates(
    session: AsyncSession,
    *,
    name: str,
    brand_ids: set[UUID],
) -> list[Product]:
    normalized_identity = normalize_product_text(name)
    normalized_name = func.translate(
        func.lower(Product.name),
        "çğıöşü",
        "cgiosu",
    )
    tokens = sorted(
        {token for token in normalize_product_identity(name).search_tokens if len(token) >= 3},
        key=lambda token: (-len(token), token),
    )[:4]
    name_conditions = [
        Product.aliases.any(ProductAlias.normalized_alias == normalized_identity),
        Product.name.ilike(name.strip()),
    ]
    if tokens:
        name_conditions.append(or_(*(normalized_name.contains(token) for token in tokens)))
    statement = (
        select(Product)
        .options(
            selectinload(Product.aliases),
            selectinload(Product.brand),
            selectinload(Product.images),
        )
        .where(
            *_eligible_global_product_conditions(),
            or_(*name_conditions),
        )
        .order_by(Product.name, Product.id)
        .limit(MAX_STRUCTURED_QUERY_ROWS)
    )
    if brand_ids:
        statement = statement.where(Product.brand_id.in_(brand_ids))
    return list((await session.scalars(statement)).unique())


async def _result_for_products(
    session: AsyncSession,
    *,
    market_id: UUID,
    products: list[Product],
    total: int,
    evidence_type: CandidateMatchType,
    evidence_reason: str,
    force_ambiguous: bool = False,
    ambiguity_reason: str = "ambiguous candidates",
) -> CatalogMatchResult:
    product_ids = [product.id for product in products]
    adopted = set(
        (
            await session.scalars(
                select(MarketProduct.product_id).where(
                    MarketProduct.market_id == market_id,
                    MarketProduct.product_id.in_(product_ids),
                )
            )
        ).all()
    )
    candidates = tuple(
        CatalogMatchCandidate(
            product=product,
            match_type=evidence_type,
            match_reason=evidence_reason,
            already_adopted=product.id in adopted,
        )
        for product in products[:MAX_MATCH_CANDIDATES]
    )
    if total == 1 and not force_ambiguous:
        return CatalogMatchResult(evidence_type, evidence_reason, candidates, total)
    return CatalogMatchResult("ambiguous", ambiguity_reason, candidates, total)


def _none_result() -> CatalogMatchResult:
    return CatalogMatchResult("none", "no global match", (), 0)


def eligible_global_product_conditions() -> tuple:
    """Public query predicates for a valid shared-catalog identity."""
    return _eligible_global_product_conditions()


def _eligible_global_product_conditions() -> tuple:
    return (
        Product.is_global.is_(True),
        Product.market_id.is_(None),
        Product.is_active.is_(True),
        or_(
            Product.brand_id.is_(None),
            Product.brand.has(
                and_(
                    Brand.is_global.is_(True),
                    Brand.market_id.is_(None),
                    Brand.is_active.is_(True),
                )
            ),
        ),
        or_(
            Product.category_id.is_(None),
            Product.category.has(
                and_(
                    Category.is_global.is_(True),
                    Category.market_id.is_(None),
                    Category.is_active.is_(True),
                )
            ),
        ),
    )
