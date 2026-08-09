from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Protocol
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Brand,
    Campaign,
    CampaignItem,
    MarketProduct,
    Product,
    ProductAlias,
    ProductImage,
)
from app.services.catalog import resolve_effective_product
from app.services.product_identity import NormalizedProductIdentity, normalize_product_identity

logger = logging.getLogger(__name__)

AUTO_ASSIGN_THRESHOLD = Decimal("0.90")
CATALOG_CANDIDATE_LIMIT = 300
CATALOG_FALLBACK_LIMIT = 100
HISTORICAL_CANDIDATE_LIMIT = 100
SAFE_IMAGE_QUALITY = {"excellent", "good"}


@dataclass(frozen=True)
class ImageCandidate:
    identity: NormalizedProductIdentity
    aliases: tuple[NormalizedProductIdentity, ...]
    image_storage_key: str | None
    image_url: str | None
    image_mime_type: str | None
    image_has_alpha: bool | None
    product_id: UUID | None
    market_product_id: UUID | None
    catalog_scope: str
    historical_identity: NormalizedProductIdentity | None = None

    @property
    def has_usable_image(self) -> bool:
        return bool(self.image_storage_key)


@dataclass(frozen=True)
class ImageResolutionResult:
    image_storage_key: str | None
    image_url: str | None
    image_mime_type: str | None
    image_has_alpha: bool | None
    source: str
    confidence: Decimal
    matched_product_id: UUID | None
    matched_market_product_id: UUID | None
    match_reason: str
    requires_review: bool
    normalized_identity: NormalizedProductIdentity
    provider: str

    @property
    def resolved(self) -> bool:
        return bool(self.image_storage_key) and not self.requires_review

    def as_metadata(self) -> dict[str, object]:
        return {
            "image_storage_key": self.image_storage_key,
            "image_url": self.image_url,
            "image_mime_type": self.image_mime_type,
            "image_has_alpha": self.image_has_alpha,
            "source": self.source,
            "confidence": str(self.confidence),
            "matched_product_id": str(self.matched_product_id) if self.matched_product_id else None,
            "matched_market_product_id": (
                str(self.matched_market_product_id) if self.matched_market_product_id else None
            ),
            "match_reason": self.match_reason,
            "requires_review": self.requires_review,
            "decision": "resolved" if self.resolved else "fallback",
            "provider": self.provider,
            "normalized_identity": self.normalized_identity.as_dict(),
        }


@dataclass(frozen=True)
class CampaignImageResolutionSummary:
    campaign_id: UUID
    resolved_count: int
    unresolved_count: int
    review_count: int
    unresolved_names: tuple[str, ...]
    results: tuple[ImageResolutionResult, ...]


@dataclass(frozen=True)
class ResolutionContext:
    item: CampaignItem
    identity: NormalizedProductIdentity
    catalog_candidates: tuple[ImageCandidate, ...]
    historical_candidates: tuple[ImageCandidate, ...]


class ImageResolutionProvider(Protocol):
    name: str

    async def resolve(self, context: ResolutionContext) -> ImageResolutionResult | None: ...


@dataclass
class ProductImageResolver:
    providers: tuple[ImageResolutionProvider, ...]
    automatic_threshold: Decimal = AUTO_ASSIGN_THRESHOLD

    async def resolve(self, context: ResolutionContext) -> ImageResolutionResult:
        best_review: ImageResolutionResult | None = None
        for provider in self.providers:
            try:
                result = await provider.resolve(context)
            except Exception:
                logger.exception("Product image provider failed safely. provider=%s", provider.name)
                continue
            if result is None:
                continue
            if result.confidence >= self.automatic_threshold and not result.requires_review:
                return result
            if best_review is None or result.confidence > best_review.confidence:
                best_review = result
        if best_review is not None:
            return best_review
        return unresolved_result(context.identity)


class CurrentAssignmentProvider:
    name = "current_assignment"

    async def resolve(self, context: ResolutionContext) -> ImageResolutionResult | None:
        candidate = _candidate_from_item(context.item)
        if context.item.product_id is not None and context.item.market_product_id is None:
            candidate = next(
                (
                    catalog_candidate
                    for catalog_candidate in context.catalog_candidates
                    if catalog_candidate.product_id == context.item.product_id
                    and catalog_candidate.market_product_id is not None
                    and catalog_candidate.has_usable_image
                ),
                candidate,
            )
        if candidate is None or not candidate.has_usable_image:
            return None
        source = "explicit_market_image" if candidate.market_product_id else "current_product_image"
        return _result(
            context.identity,
            candidate,
            source=source,
            confidence=Decimal("1.00"),
            reason="Existing campaign product assignment has a usable image.",
            provider=self.name,
        )


class InternalCatalogProvider:
    name = "internal_catalog"

    async def resolve(self, context: ResolutionContext) -> ImageResolutionResult | None:
        candidates = _compatible_with_existing_assignment(context.item, context.catalog_candidates)
        return _best_candidate_result(context.identity, candidates, provider=self.name)


class HistoricalImageProvider:
    name = "historical_catalog"

    async def resolve(self, context: ResolutionContext) -> ImageResolutionResult | None:
        candidates = _compatible_with_existing_assignment(
            context.item, context.historical_candidates
        )
        return _best_candidate_result(
            context.identity,
            candidates,
            provider=self.name,
            historical=True,
        )


class FutureProviderHook:
    """No-op extension point for a future external or internal provider implementation."""

    name = "future_provider_hook"

    async def resolve(self, context: ResolutionContext) -> ImageResolutionResult | None:
        return None


def default_resolver() -> ProductImageResolver:
    return ProductImageResolver(
        providers=(
            CurrentAssignmentProvider(),
            InternalCatalogProvider(),
            HistoricalImageProvider(),
            FutureProviderHook(),
        )
    )


async def resolve_campaign_product_images(
    session: AsyncSession,
    market_id: UUID,
    campaign_id: UUID,
    *,
    resolver: ProductImageResolver | None = None,
) -> CampaignImageResolutionSummary:
    campaign = await _load_campaign(session, market_id, campaign_id)
    catalog_candidates = await _load_catalog_candidates(session, market_id, campaign.items)
    historical_candidates = await _load_historical_candidates(
        session,
        market_id,
        campaign_id,
    )
    active_resolver = resolver or default_resolver()
    results: list[ImageResolutionResult] = []
    unresolved_names: list[str] = []

    for item in sorted(campaign.items, key=lambda row: (row.sort_order, str(row.id))):
        if item.match_status == "excluded":
            continue
        identity = normalize_product_identity(item.incoming_name)
        context = ResolutionContext(
            item=item,
            identity=identity,
            catalog_candidates=tuple(catalog_candidates),
            historical_candidates=tuple(historical_candidates),
        )
        result = await active_resolver.resolve(context)
        _apply_resolution(item, result)
        results.append(result)
        if not result.resolved:
            unresolved_names.append(item.display_name or item.incoming_name)

    await session.commit()
    return CampaignImageResolutionSummary(
        campaign_id=campaign.id,
        resolved_count=sum(result.resolved for result in results),
        unresolved_count=sum(not result.resolved for result in results),
        review_count=sum(result.requires_review for result in results),
        unresolved_names=tuple(unresolved_names),
        results=tuple(results),
    )


def unresolved_result(
    identity: NormalizedProductIdentity,
    *,
    confidence: Decimal = Decimal("0.00"),
    reason: str = "No image candidate met the safe automatic assignment threshold.",
    provider: str = "resolver",
) -> ImageResolutionResult:
    return ImageResolutionResult(
        image_storage_key=None,
        image_url=None,
        image_mime_type=None,
        image_has_alpha=None,
        source="fallback",
        confidence=confidence,
        matched_product_id=None,
        matched_market_product_id=None,
        match_reason=reason,
        requires_review=confidence > 0,
        normalized_identity=identity,
        provider=provider,
    )


async def _load_campaign(session: AsyncSession, market_id: UUID, campaign_id: UUID) -> Campaign:
    campaign = await session.scalar(
        select(Campaign)
        .options(
            selectinload(Campaign.items)
            .selectinload(CampaignItem.product)
            .selectinload(Product.brand),
            selectinload(Campaign.items)
            .selectinload(CampaignItem.product)
            .selectinload(Product.aliases),
            selectinload(Campaign.items)
            .selectinload(CampaignItem.product)
            .selectinload(Product.images),
            selectinload(Campaign.items)
            .selectinload(CampaignItem.market_product)
            .selectinload(MarketProduct.product)
            .selectinload(Product.brand),
            selectinload(Campaign.items)
            .selectinload(CampaignItem.market_product)
            .selectinload(MarketProduct.product)
            .selectinload(Product.aliases),
            selectinload(Campaign.items)
            .selectinload(CampaignItem.market_product)
            .selectinload(MarketProduct.product)
            .selectinload(Product.images),
        )
        .where(Campaign.id == campaign_id, Campaign.market_id == market_id)
    )
    if campaign is None:
        raise ValueError("Campaign not found for image resolution.")
    return campaign


async def _load_catalog_candidates(
    session: AsyncSession,
    market_id: UUID,
    items: list[CampaignItem],
) -> list[ImageCandidate]:
    safe_product_image = Product.images.any(
        and_(
            ProductImage.is_primary.is_(True),
            ProductImage.quality_status.in_(SAFE_IMAGE_QUALITY),
            or_(ProductImage.storage_key.is_not(None), ProductImage.url.is_not(None)),
        )
    )
    market_rows = await session.scalars(
        select(MarketProduct)
        .options(
            selectinload(MarketProduct.product).selectinload(Product.brand),
            selectinload(MarketProduct.product).selectinload(Product.aliases),
            selectinload(MarketProduct.product).selectinload(Product.images),
        )
        .where(
            MarketProduct.market_id == market_id,
            MarketProduct.is_active.is_(True),
            or_(
                MarketProduct.image_storage_key.is_not(None),
                MarketProduct.image_url.is_not(None),
                MarketProduct.product.has(safe_product_image),
            ),
        )
        .order_by(MarketProduct.updated_at.desc())
        .limit(CATALOG_CANDIDATE_LIMIT)
    )

    search_tokens = _campaign_search_tokens(items)
    product_conditions = [Product.name.ilike(f"%{token}%") for token in search_tokens]
    product_conditions.extend(
        Product.aliases.any(ProductAlias.normalized_alias.ilike(f"%{token}%"))
        for token in search_tokens
    )
    product_conditions.extend(
        Product.brand.has(Brand.name.ilike(f"%{token}%")) for token in search_tokens
    )
    product_rows: list[Product] = []
    if product_conditions:
        rows = await session.scalars(
            select(Product)
            .options(
                selectinload(Product.brand),
                selectinload(Product.aliases),
                selectinload(Product.images),
            )
            .where(
                Product.is_active.is_(True),
                or_(
                    Product.market_id == market_id,
                    and_(Product.is_global.is_(True), Product.market_id.is_(None)),
                ),
                safe_product_image,
                or_(*product_conditions),
            )
            .order_by(Product.usage_count.desc(), Product.name)
            .limit(CATALOG_CANDIDATE_LIMIT)
        )
        product_rows = list(rows.unique().all())

    fallback_rows = await session.scalars(
        select(Product)
        .options(
            selectinload(Product.brand),
            selectinload(Product.aliases),
            selectinload(Product.images),
        )
        .where(
            Product.is_active.is_(True),
            or_(
                Product.market_id == market_id,
                and_(Product.is_global.is_(True), Product.market_id.is_(None)),
            ),
            safe_product_image,
        )
        .order_by(Product.usage_count.desc(), Product.name)
        .limit(CATALOG_FALLBACK_LIMIT)
    )
    product_rows.extend(fallback_rows.unique().all())

    candidates = [_candidate_from_market_product(row) for row in market_rows.unique().all()]
    candidates.extend(_candidate_from_product(row) for row in product_rows)
    return _deduplicate_candidates(candidate for candidate in candidates if candidate is not None)


async def _load_historical_candidates(
    session: AsyncSession,
    market_id: UUID,
    campaign_id: UUID,
) -> list[ImageCandidate]:
    rows = await session.scalars(
        select(CampaignItem)
        .options(
            selectinload(CampaignItem.product).selectinload(Product.brand),
            selectinload(CampaignItem.product).selectinload(Product.aliases),
            selectinload(CampaignItem.product).selectinload(Product.images),
            selectinload(CampaignItem.market_product)
            .selectinload(MarketProduct.product)
            .selectinload(Product.brand),
            selectinload(CampaignItem.market_product)
            .selectinload(MarketProduct.product)
            .selectinload(Product.aliases),
            selectinload(CampaignItem.market_product)
            .selectinload(MarketProduct.product)
            .selectinload(Product.images),
        )
        .where(
            CampaignItem.market_id == market_id,
            CampaignItem.campaign_id != campaign_id,
            CampaignItem.match_status.in_(("matched", "manual_selected")),
            or_(CampaignItem.product_id.is_not(None), CampaignItem.market_product_id.is_not(None)),
        )
        .order_by(CampaignItem.updated_at.desc())
        .limit(HISTORICAL_CANDIDATE_LIMIT)
    )
    candidates: list[ImageCandidate] = []
    for row in rows.unique().all():
        candidate = _candidate_from_item(row)
        if candidate is None or not candidate.has_usable_image:
            continue
        candidates.append(
            ImageCandidate(
                **{
                    **candidate.__dict__,
                    "historical_identity": normalize_product_identity(row.incoming_name),
                }
            )
        )
    return _deduplicate_candidates(candidates)


def _candidate_from_item(item: CampaignItem) -> ImageCandidate | None:
    if item.market_product is not None:
        return _candidate_from_market_product(item.market_product)
    if item.product is not None:
        return _candidate_from_product(item.product)
    return None


def _candidate_from_market_product(row: MarketProduct) -> ImageCandidate | None:
    product = row.product
    effective = resolve_effective_product(product, row)
    global_image = _primary_image(product)
    brand = row.private_brand_text or (product.brand.name if product and product.brand else None)
    package_size = row.private_package_size or (product.package_size if product else None)
    identity = normalize_product_identity(effective.name, brand=brand, package_size=package_size)
    aliases = tuple(
        normalize_product_identity(alias.alias, package_size=package_size)
        for alias in (product.aliases if product else [])
    )
    return ImageCandidate(
        identity=identity,
        aliases=aliases,
        image_storage_key=row.image_storage_key
        or (global_image.storage_key if global_image else None),
        image_url=row.image_url or (global_image.url if global_image else None),
        image_mime_type=row.image_mime_type or (global_image.mime_type if global_image else None),
        image_has_alpha=(
            global_image.has_transparent_background
            if not row.image_storage_key and global_image
            else None
        ),
        product_id=row.product_id or row.legacy_product_id,
        market_product_id=row.id,
        catalog_scope="market",
    )


def _candidate_from_product(product: Product) -> ImageCandidate | None:
    image = _primary_image(product)
    if image is None:
        return None
    brand = product.brand.name if product.brand else None
    return ImageCandidate(
        identity=normalize_product_identity(
            product.name, brand=brand, package_size=product.package_size
        ),
        aliases=tuple(
            normalize_product_identity(alias.alias, package_size=product.package_size)
            for alias in product.aliases
        ),
        image_storage_key=image.storage_key,
        image_url=image.url,
        image_mime_type=image.mime_type,
        image_has_alpha=image.has_transparent_background,
        product_id=product.id,
        market_product_id=None,
        catalog_scope="global" if product.is_global else "market",
    )


def _primary_image(product: Product | None) -> ProductImage | None:
    if product is None:
        return None
    return next(
        (
            image
            for image in product.images
            if image.is_primary
            and image.quality_status in SAFE_IMAGE_QUALITY
            and (image.storage_key or _safe_remote_url(image.url))
        ),
        None,
    )


def _best_candidate_result(
    incoming: NormalizedProductIdentity,
    candidates: tuple[ImageCandidate, ...] | list[ImageCandidate],
    *,
    provider: str,
    historical: bool = False,
) -> ImageResolutionResult | None:
    scored: list[tuple[Decimal, int, str, ImageCandidate]] = []
    for candidate in candidates:
        if not candidate.has_usable_image:
            continue
        score, source, reason = _score_candidate(incoming, candidate, historical=historical)
        if score <= 0:
            continue
        scope_rank = 0 if candidate.catalog_scope == "market" else 1
        scored.append((score, scope_rank, f"{source}:{reason}", candidate))
    if not scored:
        return None
    scored.sort(
        key=lambda row: (-row[0], row[1], str(row[3].market_product_id or row[3].product_id))
    )
    top_score, _, detail, candidate = scored[0]
    source, reason = detail.split(":", 1)
    ambiguous = any(
        other_score == top_score
        and (other.product_id or other.market_product_id)
        != (candidate.product_id or candidate.market_product_id)
        for other_score, _, _, other in scored[1:]
    )
    requires_review = top_score < AUTO_ASSIGN_THRESHOLD or ambiguous
    if ambiguous:
        reason = f"{reason} Equally strong candidates make automatic assignment unsafe."
    return _result(
        incoming,
        candidate,
        source=source,
        confidence=top_score,
        reason=reason,
        provider=provider,
        requires_review=requires_review,
    )


def _score_candidate(
    incoming: NormalizedProductIdentity,
    candidate: ImageCandidate,
    *,
    historical: bool,
) -> tuple[Decimal, str, str]:
    identities = [(candidate.identity, "catalog")]
    identities.extend((alias, "alias") for alias in candidate.aliases)
    if historical and not any(_identity_score(incoming, target)[0] > 0 for target, _ in identities):
        return (
            Decimal("0.00"),
            "historical_image",
            "Historical identity conflicts with catalog facts.",
        )
    if historical and candidate.historical_identity is not None:
        identities.append((candidate.historical_identity, "historical"))

    best = (Decimal("0.00"), "candidate", "Insufficient identity evidence.")
    for target, kind in identities:
        score, reason = _identity_score(incoming, target)
        if kind == "alias" and score >= Decimal("0.97"):
            score, source = Decimal("0.99"), "exact_alias"
            reason = "Normalized catalog alias matched exactly."
        elif kind == "historical":
            score, source = min(score, Decimal("0.92")), "historical_image"
            reason = f"Previously resolved identity matched safely. {reason}"
        elif score == Decimal("1.00"):
            source = "exact_catalog_identity"
        elif score >= Decimal("0.90"):
            source = "normalized_catalog_identity"
        else:
            source = "plausible_candidate"
        if score > best[0]:
            best = (score, source, reason)
    return best


def _identity_score(
    incoming: NormalizedProductIdentity,
    candidate: NormalizedProductIdentity,
) -> tuple[Decimal, str]:
    incoming_for_brand = incoming
    if candidate.normalized_brand:
        incoming_words = incoming.normalized_full_name
        if not (
            incoming_words == candidate.normalized_brand
            or incoming_words.startswith(f"{candidate.normalized_brand} ")
        ):
            return Decimal("0.00"), "Candidate brand is not present in the incoming identity."
        incoming_for_brand = normalize_product_identity(
            incoming.original_name,
            brand=candidate.brand,
        )

    if incoming_for_brand.normalized_full_name == candidate.normalized_full_name:
        return Decimal("1.00"), "Canonical product identity matched exactly."
    if not incoming_for_brand.normalized_product_family or not candidate.normalized_product_family:
        return Decimal("0.00"), "Product family evidence is missing."

    if (
        incoming_for_brand.normalized_variant
        and candidate.normalized_variant
        and incoming_for_brand.normalized_variant != candidate.normalized_variant
    ):
        return Decimal("0.00"), "Conflicting product variants were rejected."
    if (
        incoming_for_brand.size_key
        and candidate.size_key
        and incoming_for_brand.size_key != candidate.size_key
    ):
        return Decimal("0.00"), "Conflicting package quantities were rejected."
    if (
        incoming_for_brand.pack_count
        and candidate.pack_count
        and incoming_for_brand.pack_count != candidate.pack_count
    ):
        return Decimal("0.00"), "Conflicting pack counts were rejected."

    family_ratio = Decimal(
        str(
            SequenceMatcher(
                None,
                incoming_for_brand.normalized_product_family,
                candidate.normalized_product_family,
            ).ratio()
        )
    )
    incoming_tokens = set(incoming_for_brand.normalized_product_family.split())
    candidate_tokens = set(candidate.normalized_product_family.split())
    token_overlap = Decimal(
        str(len(incoming_tokens & candidate_tokens) / len(incoming_tokens | candidate_tokens))
    )
    family_score = max(family_ratio, token_overlap)
    if family_score < Decimal("0.78"):
        return Decimal("0.00"), "Product family similarity is below the safe candidate floor."

    score = Decimal("0.72") + family_score * Decimal("0.20")
    if candidate.normalized_brand:
        score += Decimal("0.04")
    if incoming_for_brand.normalized_variant == candidate.normalized_variant:
        score += Decimal("0.02")
    elif incoming_for_brand.normalized_variant or candidate.normalized_variant:
        score -= Decimal("0.12")
    if incoming_for_brand.size_key == candidate.size_key:
        score += Decimal("0.02")
    elif incoming_for_brand.size_key or candidate.size_key:
        score -= Decimal("0.10")
    if incoming_for_brand.pack_count == candidate.pack_count:
        score += Decimal("0.01")
    elif incoming_for_brand.pack_count or candidate.pack_count:
        score -= Decimal("0.10")
    score = max(Decimal("0.00"), min(Decimal("0.98"), score.quantize(Decimal("0.01"))))
    return score, "Brand, product family, variant, and package evidence were scored conservatively."


def _result(
    identity: NormalizedProductIdentity,
    candidate: ImageCandidate,
    *,
    source: str,
    confidence: Decimal,
    reason: str,
    provider: str,
    requires_review: bool = False,
) -> ImageResolutionResult:
    return ImageResolutionResult(
        image_storage_key=candidate.image_storage_key,
        image_url=_safe_remote_url(candidate.image_url),
        image_mime_type=candidate.image_mime_type,
        image_has_alpha=candidate.image_has_alpha,
        source=source,
        confidence=confidence,
        matched_product_id=candidate.product_id,
        matched_market_product_id=candidate.market_product_id,
        match_reason=reason,
        requires_review=requires_review,
        normalized_identity=identity,
        provider=provider,
    )


def _apply_resolution(item: CampaignItem, result: ImageResolutionResult) -> None:
    payload = dict(item.parsed_payload or {})
    payload["image_resolution"] = result.as_metadata()
    item.parsed_payload = payload
    item.normalized_name = result.normalized_identity.normalized_full_name
    if not result.resolved:
        return
    if item.product_id is None and item.market_product_id is None:
        item.product_id = result.matched_product_id
        item.market_product_id = result.matched_market_product_id
        item.match_status = "matched"
        item.match_confidence = result.confidence * 100
        item.matching_notes = f"Image resolver: {result.match_reason}"
    elif item.market_product_id is None and result.matched_product_id == item.product_id:
        item.market_product_id = result.matched_market_product_id


def _compatible_with_existing_assignment(
    item: CampaignItem,
    candidates: tuple[ImageCandidate, ...],
) -> tuple[ImageCandidate, ...]:
    if item.market_product_id is not None:
        return tuple(
            candidate
            for candidate in candidates
            if candidate.market_product_id == item.market_product_id
        )
    if item.product_id is not None:
        return tuple(
            candidate for candidate in candidates if candidate.product_id == item.product_id
        )
    return candidates


def _campaign_search_tokens(items: list[CampaignItem]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            token
            for item in items
            for token in normalize_product_identity(item.incoming_name).search_tokens
            if len(token) >= 3
        )
    )[:40]


def _deduplicate_candidates(candidates) -> list[ImageCandidate]:
    deduplicated: dict[tuple[UUID | None, UUID | None, str | None, str | None], ImageCandidate] = {}
    for candidate in candidates:
        key = (
            candidate.product_id,
            candidate.market_product_id,
            candidate.image_storage_key,
            candidate.image_url,
        )
        current = deduplicated.get(key)
        if current is None or (
            current.catalog_scope == "global" and candidate.catalog_scope == "market"
        ):
            deduplicated[key] = candidate
    return list(deduplicated.values())


def _safe_remote_url(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    return value if parsed.scheme in {"http", "https"} and parsed.netloc else None
