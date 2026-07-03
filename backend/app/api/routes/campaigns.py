from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_campaign_session, get_required_market_id
from app.schemas.campaign import (
    CampaignCreate,
    CampaignCreateFromTextRequest,
    CampaignCreateFromTextResponse,
    CampaignDetail,
    CampaignItemCreate,
    CampaignItemRead,
    CampaignItemResolveMatch,
    CampaignItemSuggestionResult,
    CampaignItemUpdate,
    CampaignListItem,
    CampaignSuggestionSummary,
    CampaignUpdate,
    GenerateCampaignSuggestionsRequest,
    GenerateItemSuggestionsRequest,
    MatchingSuggestionCreate,
    MatchingSuggestionRead,
    CampaignParseRequest,
    CampaignParseResponse,
    ParsedCampaignLineRead,
)
from app.schemas.common import ListResponse
from app.schemas.export import CampaignFileCreate, CampaignFileRead, ExportJobCreate, ExportJobRead
from app.services import campaign as campaign_service
from app.services.campaign_parser import parse_campaign_text
from app.services import product_matching

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


@router.get("", response_model=ListResponse[CampaignListItem])
async def list_campaigns(
    search: str | None = None,
    status: str | None = None,
    channel: str | None = None,
    source_type: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    market_id: UUID = Depends(get_required_market_id),
    session: AsyncSession = Depends(get_campaign_session),
) -> ListResponse[CampaignListItem]:
    items, total = await campaign_service.list_campaigns(
        session,
        market_id=market_id,
        search=search,
        status_filter=status,
        channel=channel,
        source_type=source_type,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return ListResponse(items=items, total=total, limit=limit, offset=offset)


@router.post("", response_model=CampaignDetail, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    payload: CampaignCreate,
    market_id: UUID = Depends(get_required_market_id),
    session: AsyncSession = Depends(get_campaign_session),
) -> CampaignDetail:
    return await campaign_service.create_campaign(session, payload, market_id)


@router.post("/parse-text", response_model=CampaignParseResponse)
async def parse_campaign_text_endpoint(payload: CampaignParseRequest) -> CampaignParseResponse:
    parsed_items = parse_campaign_text(payload.raw_text, default_currency=payload.default_currency)
    items = [
        ParsedCampaignLineRead(
            **item.__dict__,
            warnings=item.parsed_payload.get("warnings", []),
        )
        for item in parsed_items
    ]
    return CampaignParseResponse(
        items=items,
        total_lines=len([line for line in payload.raw_text.splitlines() if line.strip()]),
        parsed_count=len(items),
        warning_count=sum(len(item.warnings) for item in items),
    )


@router.post(
    "/from-text",
    response_model=CampaignCreateFromTextResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_campaign_from_text(
    payload: CampaignCreateFromTextRequest,
    market_id: UUID = Depends(get_required_market_id),
    session: AsyncSession = Depends(get_campaign_session),
) -> CampaignCreateFromTextResponse:
    return await campaign_service.create_campaign_from_text(session, payload, market_id)


@router.get("/{campaign_id}", response_model=CampaignDetail)
async def get_campaign(
    campaign_id: UUID,
    market_id: UUID = Depends(get_required_market_id),
    session: AsyncSession = Depends(get_campaign_session),
) -> CampaignDetail:
    return await campaign_service.get_campaign(session, campaign_id, market_id)


@router.patch("/{campaign_id}", response_model=CampaignDetail)
async def update_campaign(
    campaign_id: UUID,
    payload: CampaignUpdate,
    market_id: UUID = Depends(get_required_market_id),
    session: AsyncSession = Depends(get_campaign_session),
) -> CampaignDetail:
    return await campaign_service.update_campaign(session, campaign_id, payload, market_id)


@router.delete("/{campaign_id}", response_model=CampaignDetail)
async def cancel_campaign(
    campaign_id: UUID,
    market_id: UUID = Depends(get_required_market_id),
    session: AsyncSession = Depends(get_campaign_session),
) -> CampaignDetail:
    return await campaign_service.cancel_campaign(session, campaign_id, market_id)


@router.post("/{campaign_id}/items", response_model=CampaignItemRead, status_code=status.HTTP_201_CREATED)
async def add_campaign_item(
    campaign_id: UUID,
    payload: CampaignItemCreate,
    market_id: UUID = Depends(get_required_market_id),
    session: AsyncSession = Depends(get_campaign_session),
) -> CampaignItemRead:
    return await campaign_service.add_campaign_item(session, campaign_id, payload, market_id)


@router.patch("/{campaign_id}/items/{item_id}", response_model=CampaignItemRead)
async def update_campaign_item(
    campaign_id: UUID,
    item_id: UUID,
    payload: CampaignItemUpdate,
    market_id: UUID = Depends(get_required_market_id),
    session: AsyncSession = Depends(get_campaign_session),
) -> CampaignItemRead:
    return await campaign_service.update_campaign_item(session, campaign_id, item_id, payload, market_id)


@router.post("/{campaign_id}/items/{item_id}/resolve-match", response_model=CampaignItemRead)
async def resolve_campaign_item_match(
    campaign_id: UUID,
    item_id: UUID,
    payload: CampaignItemResolveMatch,
    market_id: UUID = Depends(get_required_market_id),
    session: AsyncSession = Depends(get_campaign_session),
) -> CampaignItemRead:
    return await campaign_service.resolve_campaign_item_match(
        session,
        campaign_id,
        item_id,
        payload,
        market_id,
    )


@router.get("/{campaign_id}/items/{item_id}/suggestions", response_model=list[MatchingSuggestionRead])
async def list_matching_suggestions(
    campaign_id: UUID,
    item_id: UUID,
    market_id: UUID = Depends(get_required_market_id),
    session: AsyncSession = Depends(get_campaign_session),
) -> list[MatchingSuggestionRead]:
    return await campaign_service.list_matching_suggestions(session, campaign_id, item_id, market_id)


@router.post(
    "/{campaign_id}/items/{item_id}/suggestions",
    response_model=MatchingSuggestionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_matching_suggestion(
    campaign_id: UUID,
    item_id: UUID,
    payload: MatchingSuggestionCreate,
    market_id: UUID = Depends(get_required_market_id),
    session: AsyncSession = Depends(get_campaign_session),
) -> MatchingSuggestionRead:
    return await campaign_service.create_matching_suggestion(
        session,
        campaign_id,
        item_id,
        payload,
        market_id,
    )


@router.post(
    "/{campaign_id}/items/{item_id}/generate-suggestions",
    response_model=CampaignItemSuggestionResult,
)
async def generate_item_suggestions(
    campaign_id: UUID,
    item_id: UUID,
    payload: GenerateItemSuggestionsRequest | None = None,
    market_id: UUID = Depends(get_required_market_id),
    session: AsyncSession = Depends(get_campaign_session),
) -> CampaignItemSuggestionResult:
    request = payload or GenerateItemSuggestionsRequest()
    item, suggestions = await product_matching.generate_suggestions_for_campaign_item(
        session,
        market_id,
        campaign_id,
        item_id,
        limit=request.limit,
    )
    return CampaignItemSuggestionResult(item=item, suggestions=suggestions)


@router.post(
    "/{campaign_id}/generate-suggestions",
    response_model=CampaignSuggestionSummary,
)
async def generate_campaign_suggestions(
    campaign_id: UUID,
    payload: GenerateCampaignSuggestionsRequest | None = None,
    market_id: UUID = Depends(get_required_market_id),
    session: AsyncSession = Depends(get_campaign_session),
) -> CampaignSuggestionSummary:
    request = payload or GenerateCampaignSuggestionsRequest()
    return await product_matching.generate_suggestions_for_campaign(
        session,
        market_id,
        campaign_id,
        limit_per_item=request.limit_per_item,
    )


@router.get("/{campaign_id}/files", response_model=list[CampaignFileRead])
async def list_campaign_files(
    campaign_id: UUID,
    market_id: UUID = Depends(get_required_market_id),
    session: AsyncSession = Depends(get_campaign_session),
) -> list[CampaignFileRead]:
    return await campaign_service.list_campaign_files(session, campaign_id, market_id)


@router.post("/{campaign_id}/files", response_model=CampaignFileRead, status_code=status.HTTP_201_CREATED)
async def create_campaign_file(
    campaign_id: UUID,
    payload: CampaignFileCreate,
    market_id: UUID = Depends(get_required_market_id),
    session: AsyncSession = Depends(get_campaign_session),
) -> CampaignFileRead:
    return await campaign_service.create_campaign_file(session, campaign_id, payload, market_id)


@router.post(
    "/{campaign_id}/export-jobs",
    response_model=ExportJobRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_export_job(
    campaign_id: UUID,
    payload: ExportJobCreate,
    market_id: UUID = Depends(get_required_market_id),
    session: AsyncSession = Depends(get_campaign_session),
) -> ExportJobRead:
    return await campaign_service.create_export_job(session, campaign_id, payload, market_id)


@router.get("/{campaign_id}/export-jobs", response_model=list[ExportJobRead])
async def list_export_jobs(
    campaign_id: UUID,
    market_id: UUID = Depends(get_required_market_id),
    session: AsyncSession = Depends(get_campaign_session),
) -> list[ExportJobRead]:
    return await campaign_service.list_export_jobs(session, campaign_id, market_id)
