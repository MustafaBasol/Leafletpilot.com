from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Campaign, CampaignFile, CampaignItem, ExportJob, MatchingSuggestion, Product, Template, MarketProduct, Market
from app.schemas.campaign import (
    CampaignCreate,
    CampaignCreateFromTextRequest,
    CampaignCreateFromTextResponse,
    CampaignItemCreate,
    CampaignItemResolveMatch,
    CampaignItemUpdate,
    CampaignPreviewHtml,
    CampaignUpdate,
    CampaignBuilderOptions,
    CampaignFinalizeResponse,
    MatchingSuggestionCreate,
)
from app.schemas.export import CampaignFileCreate, ExportJobCreate
from app.services.rendering import (
    FORMAT_MEDIA_TYPES,
    normalize_requested_formats,
    render_campaign_export,
    storage_path_for_key,
)
from app.services.campaign_parser import ParsedCampaignLine, parse_campaign_text
from app.services.campaign_rendering import campaign_render_load_options
from app.services.preview_renderer import DEFAULT_TEMPLATE_NAME, DEFAULT_TEMPLATE_SLUG, render_campaign_preview_html
from app.services.catalog import list_my_market_products, resolved_market_product
from app.services.templates import list_templates
from app.services.entitlements import has_capacity, resolve_capabilities, resolve_plan_code

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
    statement = select(Campaign).options(selectinload(Campaign.template)).where(Campaign.market_id == scoped_market_id)
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
    *,
    commit: bool = True,
) -> Campaign:
    scoped_market_id = require_market_id(market_id)
    data = payload.model_dump(exclude={"items", "builder_config"})
    data["builder_config_json"] = payload.builder_config or {}
    if data.get("template_id") is not None:
        template = await validate_visible_template(session, data["template_id"], scoped_market_id)
        _validate_template_slots(template, len(payload.items))
    for item in payload.items:
        if item.market_product_id is not None:
            await validate_visible_market_product(session, item.market_product_id, scoped_market_id)
    campaign = Campaign(**data, market_id=scoped_market_id, status="draft")
    campaign.items = [
        await _build_campaign_item(session, item, campaign_id=None, market_id=scoped_market_id, default_currency=campaign.currency)
        for item in payload.items
    ]
    recalculate_campaign_counts(campaign)
    await _persist(session, campaign, commit=commit)
    return await get_campaign(session, campaign.id, scoped_market_id)


async def create_campaign_from_text(
    session: AsyncSession,
    payload: CampaignCreateFromTextRequest,
    market_id: UUID | None,
    *,
    commit: bool = True,
) -> CampaignCreateFromTextResponse:
    scoped_market_id = require_market_id(market_id)
    parsed_items = parse_campaign_text(payload.raw_text, default_currency=payload.currency)
    campaign_payload = CampaignCreate(
        title=payload.title,
        channel=payload.channel,
        source_type=payload.source_type,
        raw_input_text=payload.raw_text,
        template_id=payload.template_id,
        campaign_start_date=payload.campaign_start_date,
        campaign_end_date=payload.campaign_end_date,
        currency=payload.currency,
        language=payload.language,
        items=[_campaign_item_create_from_parsed(item) for item in parsed_items],
    )
    campaign = await create_campaign(session, campaign_payload, scoped_market_id, commit=commit)
    suggestions_created = 0
    if payload.generate_suggestions and parsed_items:
        if not commit:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Campaign suggestions require committed campaign creation.",
            )
        from app.services import product_matching

        summary = await product_matching.generate_suggestions_for_campaign(
            session,
            scoped_market_id,
            campaign.id,
            limit_per_item=payload.suggestion_limit,
        )
        suggestions_created = summary.suggestions_created
        campaign = await get_campaign(session, campaign.id, scoped_market_id)

    warning_count = sum(
        len(item.parsed_payload.get("warnings", []))
        for item in parsed_items
        if isinstance(item.parsed_payload, dict)
    )
    return CampaignCreateFromTextResponse(
        campaign_id=campaign.id,
        product_count=campaign.product_count,
        matched_count=campaign.matched_count,
        missing_count=campaign.missing_count,
        low_confidence_count=campaign.low_confidence_count,
        parsed_count=len(parsed_items),
        warning_count=warning_count,
        suggestions_created=suggestions_created,
        campaign=campaign,
    )


async def get_campaign(session: AsyncSession, campaign_id: UUID, market_id: UUID | None) -> Campaign:
    scoped_market_id = require_market_id(market_id)
    statement = (
        select(Campaign)
        .options(
            *campaign_render_load_options(),
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
    campaign.items.sort(key=lambda item: (item.sort_order, item.created_at, str(item.id)))
    return campaign


async def get_campaign_preview_html(
    session: AsyncSession,
    campaign_id: UUID,
    market_id: UUID | None,
    output_format: str | None = None,
) -> CampaignPreviewHtml:
    campaign = await get_campaign(session, campaign_id, market_id)
    generated_at = datetime.now(UTC).replace(microsecond=0)
    if campaign.snapshot_json:
        from app.services.campaign_rendering import render_campaign_snapshot_html

        snapshot = campaign.snapshot_json
        return CampaignPreviewHtml(
            campaign_id=campaign.id,
            template_id=snapshot.get("template_id"),
            template_name=snapshot.get("template_name") or "Frozen template",
            html=render_campaign_snapshot_html(snapshot, generated_at=generated_at),
            generated_at=generated_at,
            template_version=snapshot.get("template_version"),
            page_count=1,
        )
    template = campaign.template
    if template is None:
        template = await _get_default_template(session, campaign.market_id)

    return CampaignPreviewHtml(
        campaign_id=campaign.id,
        template_id=template.id if template else None,
        template_name=template.name if template else DEFAULT_TEMPLATE_NAME,
        html=render_campaign_preview_html(campaign, template, generated_at=generated_at, output_format=output_format),
        generated_at=generated_at,
        template_version=template.version if template else None,
        page_count=1,
    )


async def update_campaign(
    session: AsyncSession,
    campaign_id: UUID,
    payload: CampaignUpdate,
    market_id: UUID | None,
) -> Campaign:
    campaign = await get_campaign(session, campaign_id, market_id)
    if campaign.frozen_at is not None or campaign.finalized_at is not None:
        raise HTTPException(status_code=409, detail="Finalized campaigns are immutable; duplicate to create a new revision.")
    updates = payload.model_dump(exclude_unset=True)
    item_payloads = updates.pop("items", None)
    if "builder_config" in updates:
        updates["builder_config_json"] = updates.pop("builder_config") or {}
    if updates.get("template_id") is not None:
        await validate_visible_template(session, updates["template_id"], campaign.market_id)
    for key, value in updates.items():
        setattr(campaign, key, value)
    if item_payloads is not None:
        campaign.items = [
            await _build_campaign_item(
                session,
                CampaignItemCreate.model_validate(item),
                campaign_id=None,
                market_id=campaign.market_id,
                default_currency=campaign.currency,
            )
            for item in item_payloads
        ]
        recalculate_campaign_counts(campaign)
    if "status" in updates:
        now = datetime.now(UTC)
        if campaign.status == "approved" and campaign.approved_at is None:
            campaign.approved_at = now
        elif campaign.status == "completed" and campaign.completed_at is None:
            campaign.completed_at = now
        elif campaign.status == "failed" and campaign.failed_at is None:
            campaign.failed_at = now
    return await _persist(session, campaign)


async def cancel_campaign(
    session: AsyncSession,
    campaign_id: UUID,
    market_id: UUID | None,
    *,
    commit: bool = True,
) -> Campaign:
    campaign = await get_campaign(session, campaign_id, market_id)
    campaign.status = "cancelled"
    return await _persist(session, campaign, commit=commit)


async def add_campaign_item(
    session: AsyncSession,
    campaign_id: UUID,
    payload: CampaignItemCreate,
    market_id: UUID | None,
) -> CampaignItem:
    campaign = await get_campaign(session, campaign_id, market_id)
    item = await _build_campaign_item(
        session,
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
    if campaign.frozen_at is not None or campaign.finalized_at is not None:
        raise HTTPException(status_code=409, detail="Finalized campaigns are immutable; duplicate to create a new revision.")
    item = _find_item(campaign, item_id)
    updates = payload.model_dump(exclude_unset=True)
    product_id = updates.get("product_id")
    if product_id is not None:
        await validate_visible_product(session, product_id, campaign.market_id)
    if updates.get("market_product_id") is not None:
        await validate_visible_market_product(session, updates["market_product_id"], campaign.market_id)
    for key, value in updates.items():
        setattr(item, key, value)
    recalculate_campaign_counts(campaign)
    await _persist(session, campaign)
    return item


async def reorder_campaign_items(session: AsyncSession, campaign_id: UUID, item_ids: list[UUID], market_id: UUID | None) -> Campaign:
    campaign = await get_campaign(session, campaign_id, market_id)
    if campaign.frozen_at is not None or campaign.finalized_at is not None:
        raise HTTPException(status_code=409, detail="Finalized campaigns are immutable; duplicate to create a new revision.")
    current = {str(item.id): item for item in campaign.items}
    requested_ids = [str(item_id) for item_id in item_ids]
    if set(current) != set(requested_ids) or len(requested_ids) != len(current):
        raise HTTPException(
            status_code=422,
            detail={
                "message": "item_ids must contain each campaign item exactly once.",
                "expected_item_ids": list(current),
                "received_item_ids": requested_ids,
            },
        )
    for index, item_id in enumerate(requested_ids):
        current[item_id].sort_order = index
    await _persist(session, campaign)
    return await get_campaign(session, campaign.id, campaign.market_id)


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
    *,
    commit: bool = True,
    after_flush: Callable[[ExportJob], Awaitable[None]] | None = None,
) -> ExportJob:
    campaign = await get_campaign(session, campaign_id, market_id)
    formats = normalize_requested_formats(payload.requested_formats)
    if payload.job_type == "final_export" and campaign.frozen_at is None:
        # Legacy Telegram campaigns may not have a template reference. Keep
        # those exports renderable while still freezing every campaign that
        # has an eligible template (explicit or default).
        template = campaign.template or await _get_default_template(session, campaign.market_id)
        if template is not None:
            await finalize_campaign(session, campaign.id, campaign.market_id)
            campaign = await get_campaign(session, campaign_id, market_id)
    existing = await session.scalar(
        select(ExportJob).where(
            ExportJob.campaign_id == campaign.id,
            ExportJob.market_id == campaign.market_id,
            ExportJob.job_type == (payload.job_type or "final_export"),
            ExportJob.status.in_(["queued", "running", "completed"]),
            ExportJob.requested_formats == formats,
        ).order_by(ExportJob.created_at.desc())
    )
    if existing is not None:
        return existing
    market = campaign.market or await session.get(Market, campaign.market_id)
    capabilities = resolve_capabilities(market)
    if capabilities.monthly_exports_limit is not None:
        month_start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        completed_exports = await session.scalar(
            select(func.count(ExportJob.id)).where(
                ExportJob.market_id == campaign.market_id,
                ExportJob.status == "completed",
                ExportJob.completed_at >= month_start,
            )
        )
        if not has_capacity(completed_exports or 0, capabilities.monthly_exports_limit):
            raise HTTPException(
                status_code=403,
                detail=f"The {resolve_plan_code(market)} plan has reached its monthly export limit.",
            )
    export_job = ExportJob(
        **payload.model_dump(exclude={"requested_formats", "status"}),
        campaign_id=campaign.id,
        market_id=campaign.market_id,
        requested_formats=formats,
        status="queued",
    )
    session.add(export_job)
    if commit:
        await session.commit()
    else:
        await session.flush()
    if after_flush is not None:
        await after_flush(export_job)
        await session.flush()
    await session.refresh(export_job)
    await render_campaign_export(
        session,
        market_id=campaign.market_id,
        campaign_id=campaign.id,
        requested_formats=formats,
        export_job_id=export_job.id,
        commit=commit,
    )
    await session.refresh(export_job)
    return export_job


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


async def get_campaign_file_download(
    session: AsyncSession,
    campaign_id: UUID,
    file_id: UUID,
    market_id: UUID | None,
) -> tuple[str, str, str]:
    campaign = await get_campaign(session, campaign_id, market_id)
    statement = select(CampaignFile).where(
        CampaignFile.id == file_id,
        CampaignFile.campaign_id == campaign.id,
        CampaignFile.market_id == campaign.market_id,
    )
    campaign_file = await session.scalar(statement)
    if campaign_file is None or campaign_file.storage_key is None:
        raise _not_found("Campaign file")
    if campaign_file.status != "ready":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign file is not ready for download.",
        )

    try:
        file_path = storage_path_for_key(campaign_file.storage_key)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign file not found.") from None

    if not file_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign file not found.")

    file_format = (campaign_file.format or "").lower()
    media_type = FORMAT_MEDIA_TYPES.get(file_format, "application/octet-stream")
    return str(file_path), media_type, file_path.name


async def validate_visible_product(session: AsyncSession, product_id: UUID, market_id: UUID) -> Product:
    product = await session.scalar(
        select(Product).where(
            Product.id == product_id,
            Product.is_active.is_(True),
            or_(
                Product.market_id == market_id,
                and_(Product.is_global.is_(True), Product.market_id.is_(None)),
            ),
        )
    )
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="product_id must reference an active product visible to the current market.",
        )
    return product


async def validate_visible_market_product(session: AsyncSession, market_product_id: UUID, market_id: UUID) -> MarketProduct:
    row = await session.scalar(
        select(MarketProduct)
        .options(
            selectinload(MarketProduct.product).selectinload(Product.brand),
            selectinload(MarketProduct.product).selectinload(Product.category),
            selectinload(MarketProduct.product).selectinload(Product.images),
        )
        .where(MarketProduct.id == market_product_id, MarketProduct.market_id == market_id, MarketProduct.is_active.is_(True))
    )
    if row is None:
        raise HTTPException(status_code=400, detail="market_product_id must reference an active product owned by the current market.")
    return row


async def get_builder_options(session: AsyncSession, market_id: UUID) -> CampaignBuilderOptions:
    templates, _ = await list_templates(session, market_id=market_id, include_global=True, search=None, is_active=True, is_global=None, limit=200, offset=0)
    products = await list_my_market_products(session, market_id)
    market = await session.get(Market, market_id)
    capabilities = resolve_capabilities(market) if market else None
    market_plan = (market.subscription_plan if market else "starter")
    ranks = {"starter": 0, "growth": 1, "pro": 2}
    rank = ranks.get(market_plan, 0)
    eligible_templates = [template for template in templates if template.status not in {"draft", "archived"} and ranks.get(template.minimum_plan, 0) <= rank]
    return CampaignBuilderOptions(
        templates=[{
            "id": template.id, "name": template.name, "slug": template.slug,
            "template_type": template.template_type, "config_json": template.config_json,
            "is_global": template.is_global, "market_id": template.market_id,
            "status": template.status, "visibility": template.visibility,
            "minimum_plan": template.minimum_plan, "version": template.version,
            "thumbnail_key": template.thumbnail_key,
        } for template in eligible_templates],
        products=[resolved_market_product(row) for row in products if row.is_active],
        limits={"max_products": getattr(capabilities, "max_products_per_campaign", None) if capabilities else None, "export_formats": ["pdf", "png"]},
    )


async def finalize_campaign(session: AsyncSession, campaign_id: UUID, market_id: UUID) -> CampaignFinalizeResponse:
    campaign = await get_campaign(session, campaign_id, market_id)
    if campaign.frozen_at is not None:
        return CampaignFinalizeResponse(campaign=campaign, frozen_at=campaign.frozen_at, snapshot=campaign.snapshot_json or {})
    template = campaign.template or await _get_default_template(session, campaign.market_id)
    if template is None:
        raise HTTPException(status_code=422, detail="A published template is required before finalization.")
    _validate_template_slots(template, len([item for item in campaign.items if item.match_status != "excluded"]))
    for item in campaign.items:
        if item.market_product_id is not None:
            await _refresh_catalog_item(session, item, campaign.market_id, campaign.currency)
    from app.services.campaign_rendering import build_campaign_render_payload
    now = datetime.now(UTC).replace(microsecond=0)
    campaign.snapshot_json = build_campaign_render_payload(campaign, template)
    campaign.frozen_at = now
    campaign.finalized_at = now
    campaign.status = "approved"
    campaign.approved_at = campaign.approved_at or now
    await _persist(session, campaign)
    return CampaignFinalizeResponse(campaign=await get_campaign(session, campaign.id, market_id), frozen_at=now, snapshot=campaign.snapshot_json)


async def validate_visible_template(session: AsyncSession, template_id: UUID, market_id: UUID) -> Template:
    template = await session.scalar(
        select(Template).where(
            Template.id == template_id,
            Template.is_active.is_(True),
            or_(
                Template.market_id == market_id,
                and_(Template.is_global.is_(True), Template.market_id.is_(None), Template.status == "published"),
            ),
        )
    )
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="template_id must reference an active template visible to the current market.",
        )
    return template


def _validate_template_slots(template: Template, item_count: int) -> None:
    config = template.config_json if isinstance(template.config_json, dict) else {}
    slot_count = config.get("slot_count")
    if slot_count is None:
        return
    try:
        slots = int(slot_count)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Template slot_count must be an integer.") from exc
    if item_count > slots:
        raise HTTPException(status_code=422, detail=f"Template requires at most {slots} products.")


async def _get_default_template(session: AsyncSession, market_id: UUID) -> Template | None:
    return await session.scalar(
        select(Template)
        .where(
            Template.slug == DEFAULT_TEMPLATE_SLUG,
            Template.is_active.is_(True),
            or_(
                Template.market_id == market_id,
                and_(Template.is_global.is_(True), Template.market_id.is_(None), Template.status == "published"),
            ),
        )
        .order_by(Template.market_id.is_(None).desc())
        .limit(1)
    )


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


async def _persist(session: AsyncSession, instance: Any, *, commit: bool = True) -> Any:
    session.add(instance)
    try:
        if commit:
            await session.commit()
        else:
            await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Campaign record conflicts with existing data.",
        ) from exc
    return instance


async def _build_campaign_item(
    session: AsyncSession,
    payload: CampaignItemCreate,
    *,
    campaign_id: UUID | None,
    market_id: UUID,
    default_currency: str,
) -> CampaignItem:
    data = payload.model_dump()
    if payload.market_product_id is not None:
        market_product = await validate_visible_market_product(session, payload.market_product_id, market_id)
        effective = resolved_market_product(market_product)
        data.update(
            product_id=effective.get("product_id"),
            incoming_name=effective.get("name") or payload.incoming_name,
            display_name=effective.get("name") or payload.display_name,
            price=effective.get("promo_price") or effective.get("regular_price"),
            old_price=effective.get("regular_price"),
            currency=effective.get("currency") or default_currency,
            unit_label=effective.get("package_type") or payload.unit_label,
            quantity_label=effective.get("package_size") or payload.quantity_label,
            parsed_payload={**(payload.parsed_payload or {}), "catalog_source": "market_product", "effective_image_url": effective.get("image_url")},
        )
    data["currency"] = data["currency"] or default_currency
    data["market_id"] = market_id
    if campaign_id is not None:
        data["campaign_id"] = campaign_id
    return CampaignItem(
        **data,
        match_status="matched" if payload.market_product_id is not None else "not_found",
        match_confidence=100 if payload.market_product_id is not None else None,
    )


async def _refresh_catalog_item(session: AsyncSession, item: CampaignItem, market_id: UUID, default_currency: str) -> None:
    market_product = await validate_visible_market_product(session, item.market_product_id, market_id)
    effective = resolved_market_product(market_product)
    item.market_product = market_product
    item.product = market_product.product
    item.product_id = effective.get("product_id")
    item.incoming_name = effective.get("name") or item.incoming_name
    item.display_name = effective.get("name") or item.display_name
    item.price = effective.get("promo_price") or effective.get("regular_price")
    item.old_price = effective.get("regular_price")
    item.currency = effective.get("currency") or default_currency
    item.unit_label = effective.get("package_type") or item.unit_label
    item.quantity_label = effective.get("package_size") or item.quantity_label
    item.parsed_payload = {**(item.parsed_payload or {}), "catalog_source": "market_product", "effective_image_url": effective.get("image_url")}
    item.match_status = "matched"
    item.match_confidence = 100


def _campaign_item_create_from_parsed(item: ParsedCampaignLine) -> CampaignItemCreate:
    return CampaignItemCreate(
        raw_line=item.raw_line,
        incoming_name=item.incoming_name,
        display_name=item.display_name,
        price=item.price,
        old_price=item.old_price,
        currency=item.currency,
        unit_label=item.unit_label,
        quantity_label=item.quantity_label,
        category_hint=item.category_hint,
        sort_order=item.sort_order,
        parsed_payload=item.parsed_payload,
    )


def _find_item(campaign: Campaign, item_id: UUID) -> CampaignItem:
    item = next((candidate for candidate in campaign.items if candidate.id == item_id), None)
    if item is None:
        raise _not_found("Campaign item")
    return item


def _not_found(label: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{label} not found.")
