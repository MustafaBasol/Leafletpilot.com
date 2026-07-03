from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Campaign, CampaignFile, CampaignItem, ExportJob, MatchingSuggestion, Product
from app.schemas.campaign import (
    CampaignCreate,
    CampaignItemCreate,
    CampaignItemResolveMatch,
    CampaignItemUpdate,
    CampaignUpdate,
    MatchingSuggestionCreate,
)
from app.schemas.export import CampaignFileCreate, ExportJobCreate

MATCHED_STATUSES = {"matched", "manual_selected"}
MISSING_STATUSES = {"not_found", "new_product_needed", "use_without_image"}
LOW_CONFIDENCE_STATUS = "low_confidence"


def require_market_id(market_id: UUID | None) -> UUID:
    if market_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Market-Id is required for campaign routes.",
        )
    return market_id


def recalculate_campaign_counts(campaign: Campaign) -> Campaign:
    """Counts all non-excluded items as products shown in campaign workflow totals."""
    items = list(campaign.items)
    active_items = [item for item in items if item.match_status != "excluded"]
    campaign.product_count = len(active_items)
    campaign.matched_count = sum(1 for item in active_items if item.match_status in MATCHED_STATUSES)
    campaign.missing_count = sum(1 for item in active_items if item.match_status in MISSING_STATUSES)
    campaign.low_confidence_count = sum(
        1 for item in active_items if item.match_status == LOW_CONFIDENCE_STATUS
    )
    return campaign


async def list_campaigns(
    session: AsyncSession,
    *,
    market_id: UUID | None,
    search: str | None,
    status_filter: str | None,
    channel: str | None,
    source_type: str | None,
    date_from: datetime | None,
    date_to: datetime | None,
    limit: int,
    offset: int,
) -> tuple[list[Campaign], int]:
    scoped_market_id = require_market_id(market_id)
    statement = select(Campaign).where(Campaign.market_id == scoped_market_id)
    if search:
        statement = statement.where(
            or_(
                Campaign.title.ilike(f"%{search}%"),
                Campaign.raw_input_text.ilike(f"%{search}%"),
            )
        )
    if status_filter:
        statement = statement.where(Campaign.status == status_filter)
    if channel:
        statement = statement.where(Campaign.channel == channel)
    if source_type:
        statement = statement.where(Campaign.source_type == source_type)
    if date_from:
        statement = statement.where(Campaign.created_at >= date_from)
    if date_to:
        statement = statement.where(Campaign.created_at <= date_to)

    return await _list(session, statement.order_by(Campaign.created_at.desc()), limit, offset)


async def create_campaign(
    session: AsyncSession,
    payload: CampaignCreate,
    market_id: UUID | None,
) -> Campaign:
    scoped_market_id = require_market_id(market_id)
    data = payload.model_dump(exclude={"items"})
    campaign = Campaign(**data, market_id=scoped_market_id, status="draft")
    campaign.items = [
        _build_campaign_item(item, campaign_id=None, market_id=scoped_market_id, default_currency=campaign.currency)
        for item in payload.items
    ]
    recalculate_campaign_counts(campaign)
    await _persist(session, campaign)
    return await get_campaign(session, campaign.id, scoped_market_id)


async def get_campaign(session: AsyncSession, campaign_id: UUID, market_id: UUID | None) -> Campaign:
    scoped_market_id = require_market_id(market_id)
    statement = (
        select(Campaign)
        .options(
            selectinload(Campaign.items).selectinload(CampaignItem.matching_suggestions),
            selectinload(Campaign.files),
            selectinload(Campaign.export_jobs),
            selectinload(Campaign.matching_suggestions),
        )
        .where(Campaign.id == campaign_id, Campaign.market_id == scoped_market_id)
    )
    campaign = await session.scalar(statement)
    if campaign is None:
        raise _not_found("Campaign")
    return campaign


async def update_campaign(
    session: AsyncSession,
    campaign_id: UUID,
    payload: CampaignUpdate,
    market_id: UUID | None,
) -> Campaign:
    campaign = await get_campaign(session, campaign_id, market_id)
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(campaign, key, value)
    if "status" in updates:
        now = datetime.now(UTC)
        if campaign.status == "approved" and campaign.approved_at is None:
            campaign.approved_at = now
        elif campaign.status == "completed" and campaign.completed_at is None:
            campaign.completed_at = now
        elif campaign.status == "failed" and campaign.failed_at is None:
            campaign.failed_at = now
    return await _persist(session, campaign)


async def cancel_campaign(session: AsyncSession, campaign_id: UUID, market_id: UUID | None) -> Campaign:
    campaign = await get_campaign(session, campaign_id, market_id)
    campaign.status = "cancelled"
    return await _persist(session, campaign)


async def add_campaign_item(
    session: AsyncSession,
    campaign_id: UUID,
    payload: CampaignItemCreate,
    market_id: UUID | None,
) -> CampaignItem:
    campaign = await get_campaign(session, campaign_id, market_id)
    item = _build_campaign_item(
        payload,
        campaign_id=campaign.id,
        market_id=campaign.market_id,
        default_currency=campaign.currency,
    )
    campaign.items.append(item)
    recalculate_campaign_counts(campaign)
    await _persist(session, campaign)
    return item


async def update_campaign_item(
    session: AsyncSession,
    campaign_id: UUID,
    item_id: UUID,
    payload: CampaignItemUpdate,
    market_id: UUID | None,
) -> CampaignItem:
    campaign = await get_campaign(session, campaign_id, market_id)
    item = _find_item(campaign, item_id)
    updates = payload.model_dump(exclude_unset=True)
    product_id = updates.get("product_id")
    if product_id is not None:
        await validate_visible_product(session, product_id, campaign.market_id)
    for key, value in updates.items():
        setattr(item, key, value)
    recalculate_campaign_counts(campaign)
    await _persist(session, campaign)
    return item


async def resolve_campaign_item_match(
    session: AsyncSession,
    campaign_id: UUID,
    item_id: UUID,
    payload: CampaignItemResolveMatch,
    market_id: UUID | None,
) -> CampaignItem:
    campaign = await get_campaign(session, campaign_id, market_id)
    item = _find_item(campaign, item_id)
    if payload.resolution == "manual_selected":
        if payload.product_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="product_id is required for manual_selected resolution.",
            )
        await validate_visible_product(session, payload.product_id, campaign.market_id)
        item.product_id = payload.product_id
        item.match_confidence = 100
    elif payload.product_id is not None:
        await validate_visible_product(session, payload.product_id, campaign.market_id)
        item.product_id = payload.product_id

    item.match_status = payload.resolution
    if payload.display_name is not None:
        item.display_name = payload.display_name
    if payload.notes is not None:
        item.matching_notes = payload.notes
    recalculate_campaign_counts(campaign)
    await _persist(session, campaign)
    return item


async def list_matching_suggestions(
    session: AsyncSession,
    campaign_id: UUID,
    item_id: UUID,
    market_id: UUID | None,
) -> list[MatchingSuggestion]:
    campaign = await get_campaign(session, campaign_id, market_id)
    _find_item(campaign, item_id)
    result = await session.scalars(
        select(MatchingSuggestion)
        .where(
            MatchingSuggestion.campaign_id == campaign_id,
            MatchingSuggestion.campaign_item_id == item_id,
            MatchingSuggestion.market_id == campaign.market_id,
        )
        .order_by(MatchingSuggestion.rank.asc(), MatchingSuggestion.score.desc())
    )
    return list(result.all())


async def create_matching_suggestion(
    session: AsyncSession,
    campaign_id: UUID,
    item_id: UUID,
    payload: MatchingSuggestionCreate,
    market_id: UUID | None,
) -> MatchingSuggestion:
    campaign = await get_campaign(session, campaign_id, market_id)
    _find_item(campaign, item_id)
    if payload.product_id is not None:
        await validate_visible_product(session, payload.product_id, campaign.market_id)
    suggestion = MatchingSuggestion(
        **payload.model_dump(),
        campaign_id=campaign_id,
        campaign_item_id=item_id,
        market_id=campaign.market_id,
    )
    return await _persist(session, suggestion)


async def list_campaign_files(
    session: AsyncSession,
    campaign_id: UUID,
    market_id: UUID | None,
) -> list[CampaignFile]:
    campaign = await get_campaign(session, campaign_id, market_id)
    result = await session.scalars(
        select(CampaignFile)
        .where(CampaignFile.campaign_id == campaign_id, CampaignFile.market_id == campaign.market_id)
        .order_by(CampaignFile.created_at.desc())
    )
    return list(result.all())


async def create_campaign_file(
    session: AsyncSession,
    campaign_id: UUID,
    payload: CampaignFileCreate,
    market_id: UUID | None,
) -> CampaignFile:
    campaign = await get_campaign(session, campaign_id, market_id)
    campaign_file = CampaignFile(**payload.model_dump(), campaign_id=campaign.id, market_id=campaign.market_id)
    return await _persist(session, campaign_file)


async def create_export_job(
    session: AsyncSession,
    campaign_id: UUID,
    payload: ExportJobCreate,
    market_id: UUID | None,
) -> ExportJob:
    campaign = await get_campaign(session, campaign_id, market_id)
    export_job = ExportJob(**payload.model_dump(), campaign_id=campaign.id, market_id=campaign.market_id)
    return await _persist(session, export_job)


async def list_export_jobs(
    session: AsyncSession,
    campaign_id: UUID,
    market_id: UUID | None,
) -> list[ExportJob]:
    campaign = await get_campaign(session, campaign_id, market_id)
    result = await session.scalars(
        select(ExportJob)
        .where(ExportJob.campaign_id == campaign_id, ExportJob.market_id == campaign.market_id)
        .order_by(ExportJob.created_at.desc())
    )
    return list(result.all())


async def validate_visible_product(session: AsyncSession, product_id: UUID, market_id: UUID) -> Product:
    product = await session.scalar(
        select(Product).where(
            Product.id == product_id,
            Product.is_active.is_(True),
            or_(
                Product.market_id == market_id,
                Product.is_global.is_(True),
            ),
        )
    )
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="product_id must reference an active product visible to the current market.",
        )
    return product


async def _list(
    session: AsyncSession,
    statement: Select[tuple[Any]],
    limit: int,
    offset: int,
) -> tuple[list[Any], int]:
    total_statement = select(func.count()).select_from(statement.order_by(None).subquery())
    total = await session.scalar(total_statement)
    result = await session.scalars(statement.limit(limit).offset(offset))
    return list(result.unique().all()), total or 0


async def _persist(session: AsyncSession, instance: Any) -> Any:
    session.add(instance)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Campaign record conflicts with existing data.",
        ) from exc
    return instance


def _build_campaign_item(
    payload: CampaignItemCreate,
    *,
    campaign_id: UUID | None,
    market_id: UUID,
    default_currency: str,
) -> CampaignItem:
    data = payload.model_dump()
    data["currency"] = data["currency"] or default_currency
    data["market_id"] = market_id
    if campaign_id is not None:
        data["campaign_id"] = campaign_id
    return CampaignItem(**data, match_status="not_found")


def _find_item(campaign: Campaign, item_id: UUID) -> CampaignItem:
    item = next((candidate for candidate in campaign.items if candidate.id == item_id), None)
    if item is None:
        raise _not_found("Campaign item")
    return item


def _not_found(label: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{label} not found.")
