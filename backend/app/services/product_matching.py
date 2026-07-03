from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from difflib import SequenceMatcher
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Campaign, CampaignItem, MatchingSuggestion, Product
from app.services.campaign import recalculate_campaign_counts, require_market_id

TURKISH_TRANSLATION = str.maketrans(
    {
        "ç": "c",
        "Ç": "c",
        "ğ": "g",
        "Ğ": "g",
        "ı": "i",
        "İ": "i",
        "ö": "o",
        "Ö": "o",
        "ş": "s",
        "Ş": "s",
        "ü": "u",
        "Ü": "u",
    }
)
PUNCTUATION_RE = re.compile(r"[^\w\s]", re.UNICODE)
SPACES_RE = re.compile(r"\s+")
UNIT_REPLACEMENTS = (
    (re.compile(r"\b(kilogram|kilograms|kilo|kg)\b"), "kg"),
    (re.compile(r"\b(gram|grams|gr|g)\b"), "g"),
    (re.compile(r"\b(litre|liter|litreler|literler|lt|l)\b"), "l"),
)
GENERATED_REASONS = {"barcode", "exact", "alias", "fuzzy", "ai_normalized"}


@dataclass(frozen=True)
class ProductSuggestion:
    product: Product
    suggested_name: str
    score: Decimal
    reason: str
    rank: int = 0


@dataclass(frozen=True)
class CampaignSuggestionSummary:
    campaign_id: UUID
    items_processed: int
    auto_matched: int
    low_confidence: int
    not_found: int
    suggestions_created: int


def normalize_product_text(value: str) -> str:
    normalized = value.strip().translate(TURKISH_TRANSLATION).lower()
    normalized = normalized.replace("/", " ").replace("-", " ")
    normalized = PUNCTUATION_RE.sub(" ", normalized)
    normalized = SPACES_RE.sub(" ", normalized).strip()
    for pattern, replacement in UNIT_REPLACEMENTS:
        normalized = pattern.sub(replacement, normalized)
    normalized = re.sub(r"\b(\d+)\s+(kg|g|l)\b", r"\1\2", normalized)
    return SPACES_RE.sub(" ", normalized).strip()


def normalize_barcode(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = re.sub(r"\D", "", value)
    return normalized or None


async def find_product_suggestions_for_text(
    session: AsyncSession,
    market_id: UUID,
    incoming_name: str,
    barcode: str | None = None,
    limit: int = 5,
) -> list[ProductSuggestion]:
    products = await _load_visible_active_products(session, market_id)
    return rank_product_suggestions(products, incoming_name, barcode=barcode, limit=limit)


def rank_product_suggestions(
    products: list[Product],
    incoming_name: str,
    *,
    barcode: str | None = None,
    limit: int = 5,
) -> list[ProductSuggestion]:
    normalized_name = normalize_product_text(incoming_name)
    normalized_barcode = normalize_barcode(barcode)
    best_by_product: dict[UUID, ProductSuggestion] = {}

    for product in products:
        suggestion = _score_product(product, normalized_name, normalized_barcode)
        if suggestion is None:
            continue
        current = best_by_product.get(product.id)
        if current is None or suggestion.score > current.score:
            best_by_product[product.id] = suggestion

    ranked = sorted(
        best_by_product.values(),
        key=lambda suggestion: (-suggestion.score, _reason_priority(suggestion.reason), suggestion.suggested_name),
    )
    return [
        ProductSuggestion(
            product=suggestion.product,
            suggested_name=suggestion.suggested_name,
            score=suggestion.score,
            reason=suggestion.reason,
            rank=index,
        )
        for index, suggestion in enumerate(ranked[:limit], start=1)
    ]


async def generate_suggestions_for_campaign_item(
    session: AsyncSession,
    market_id: UUID | None,
    campaign_id: UUID,
    item_id: UUID,
    limit: int = 5,
) -> tuple[CampaignItem, list[MatchingSuggestion]]:
    scoped_market_id = require_market_id(market_id)
    campaign = await _get_campaign_with_item(session, campaign_id, item_id, scoped_market_id)
    item = next(candidate for candidate in campaign.items if candidate.id == item_id)
    suggestions = await find_product_suggestions_for_text(
        session,
        scoped_market_id,
        item.incoming_name,
        barcode=_barcode_from_item(item),
        limit=limit,
    )

    await session.execute(
        delete(MatchingSuggestion).where(
            MatchingSuggestion.campaign_id == campaign.id,
            MatchingSuggestion.campaign_item_id == item.id,
            MatchingSuggestion.market_id == scoped_market_id,
            MatchingSuggestion.reason.in_(GENERATED_REASONS),
        )
    )

    rows = [
        MatchingSuggestion(
            campaign_id=campaign.id,
            campaign_item_id=item.id,
            market_id=scoped_market_id,
            product_id=suggestion.product.id,
            suggested_name=suggestion.suggested_name,
            score=suggestion.score,
            reason=suggestion.reason,
            rank=suggestion.rank,
        )
        for suggestion in suggestions
    ]
    session.add_all(rows)
    _apply_item_match_result(item, suggestions)
    recalculate_campaign_counts(campaign)
    await session.commit()
    return item, rows


async def generate_suggestions_for_campaign(
    session: AsyncSession,
    market_id: UUID | None,
    campaign_id: UUID,
    limit_per_item: int = 5,
) -> CampaignSuggestionSummary:
    scoped_market_id = require_market_id(market_id)
    campaign = await _get_campaign(session, campaign_id, scoped_market_id)
    items = sorted(campaign.items, key=lambda item: item.sort_order)
    suggestions_created = 0

    for item in items:
        _, suggestions = await generate_suggestions_for_campaign_item(
            session,
            scoped_market_id,
            campaign.id,
            item.id,
            limit=limit_per_item,
        )
        suggestions_created += len(suggestions)

    refreshed = await _get_campaign(session, campaign_id, scoped_market_id)
    return CampaignSuggestionSummary(
        campaign_id=campaign_id,
        items_processed=len(items),
        auto_matched=refreshed.matched_count,
        low_confidence=refreshed.low_confidence_count,
        not_found=refreshed.missing_count,
        suggestions_created=suggestions_created,
    )


async def _load_visible_active_products(session: AsyncSession, market_id: UUID) -> list[Product]:
    result = await session.scalars(
        select(Product)
        .options(selectinload(Product.aliases))
        .where(
            Product.is_active.is_(True),
            or_(
                Product.market_id == market_id,
                and_(Product.is_global.is_(True), Product.market_id.is_(None)),
            ),
        )
        .order_by(Product.name)
    )
    return list(result.unique().all())


def _score_product(
    product: Product,
    normalized_name: str,
    normalized_barcode: str | None,
) -> ProductSuggestion | None:
    product_barcode = normalize_barcode(product.barcode)
    if normalized_barcode and product_barcode and normalized_barcode == product_barcode:
        return ProductSuggestion(product, product.name, Decimal("100.00"), "barcode")

    product_name = normalize_product_text(product.name)
    if normalized_name and normalized_name == product_name:
        return ProductSuggestion(product, product.name, Decimal("98.00"), "exact")

    for alias in product.aliases:
        alias_name = normalize_product_text(alias.alias)
        stored_alias = normalize_product_text(alias.normalized_alias)
        if normalized_name and normalized_name in {alias_name, stored_alias}:
            return ProductSuggestion(product, alias.alias, Decimal("96.00"), "alias")

    product_ratio = _ratio_score(normalized_name, product_name)
    best_fuzzy: ProductSuggestion | None = None
    if product_ratio >= 70:
        best_fuzzy = ProductSuggestion(
            product,
            product.name,
            _clamped_score(product_ratio, maximum=Decimal("95.00")),
            "fuzzy",
        )

    best_alias_score = Decimal("0.00")
    best_alias_name = None
    for alias in product.aliases:
        alias_score = _clamped_score(
            _ratio_score(normalized_name, normalize_product_text(alias.alias)),
            maximum=Decimal("93.00"),
        )
        if alias_score > best_alias_score:
            best_alias_score = alias_score
            best_alias_name = alias.alias
    if best_alias_name is not None and best_alias_score >= 65:
        alias_fuzzy = ProductSuggestion(product, best_alias_name, best_alias_score, "fuzzy")
        if best_fuzzy is None or alias_fuzzy.score > best_fuzzy.score:
            return alias_fuzzy

    if best_fuzzy is not None:
        return best_fuzzy

    return None


def _ratio_score(left: str, right: str) -> float:
    if not left or not right:
        return 0
    return SequenceMatcher(None, left, right).ratio() * 100


def _clamped_score(value: float, *, maximum: Decimal) -> Decimal:
    score = Decimal(str(value)).quantize(Decimal("0.01"))
    return min(score, maximum)


def _reason_priority(reason: str) -> int:
    return {"barcode": 0, "exact": 1, "alias": 2, "fuzzy": 3}.get(reason, 9)


def _apply_item_match_result(item: CampaignItem, suggestions: list[ProductSuggestion]) -> None:
    if not suggestions:
        item.product_id = None
        item.match_status = "not_found"
        item.match_confidence = None
        item.matching_notes = "No deterministic product match found."
        return

    top = suggestions[0]
    item.match_confidence = top.score
    if top.reason in {"barcode", "exact", "alias"} and top.score >= Decimal("95.00"):
        item.product_id = top.product.id
        item.match_status = "matched"
        item.matching_notes = f"Auto-matched by deterministic {top.reason} match."
        return

    item.product_id = None
    item.match_status = "low_confidence"
    item.matching_notes = "Fuzzy deterministic match requires operator review."


async def _get_campaign(
    session: AsyncSession,
    campaign_id: UUID,
    market_id: UUID,
) -> Campaign:
    campaign = await session.scalar(
        select(Campaign)
        .options(selectinload(Campaign.items))
        .where(Campaign.id == campaign_id, Campaign.market_id == market_id)
    )
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found.")
    return campaign


async def _get_campaign_with_item(
    session: AsyncSession,
    campaign_id: UUID,
    item_id: UUID,
    market_id: UUID,
) -> Campaign:
    campaign = await _get_campaign(session, campaign_id, market_id)
    if not any(item.id == item_id for item in campaign.items):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign item not found.")
    return campaign


def _barcode_from_item(item: CampaignItem) -> str | None:
    if not isinstance(item.parsed_payload, dict):
        return None
    value = item.parsed_payload.get("barcode")
    return str(value) if value is not None else None
