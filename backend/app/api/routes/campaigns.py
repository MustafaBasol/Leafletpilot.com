from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_campaign_session,
    get_current_user,
    get_required_market_id,
    require_market_role,
)
from app.core.roles import MARKET_MUTATION_ROLES
from app.models import User
from app.schemas.ai import (
    AIRevisionApplyResult,
    AIRevisionProposalRead,
    ProfessionalizationApplyResult,
    ProfessionalizationHistoryRead,
    ProfessionalizationRequest,
    ProfessionalizationRunRead,
    RevisionIntentRequest,
)
from app.schemas.campaign import (
    CampaignBuilderOptions,
    CampaignCreate,
    CampaignCreateFromTextRequest,
    CampaignCreateFromTextResponse,
    CampaignDetail,
    CampaignFinalizeResponse,
    CampaignIntelligenceEnvelope,
    CampaignItemCreate,
    CampaignItemOrderUpdate,
    CampaignItemRead,
    CampaignItemResolveMatch,
    CampaignItemSuggestionResult,
    CampaignItemUpdate,
    CampaignListItem,
    CampaignParseRequest,
    CampaignParseResponse,
    CampaignPreviewHtml,
    CampaignSuggestionSummary,
    CampaignUpdate,
    GenerateCampaignSuggestionsRequest,
    GenerateItemSuggestionsRequest,
    MatchingSuggestionCreate,
    MatchingSuggestionRead,
    ParsedCampaignLineRead,
)
from app.schemas.common import ListResponse
from app.schemas.export import CampaignFileCreate, CampaignFileRead, ExportJobCreate, ExportJobRead
from app.schemas.revision import (
    CampaignApprovalRequest,
    CampaignItemImageOptionRead,
    CampaignRevisionRead,
    PanelRevisionCommand,
    PanelUndoRevisionRequest,
    RevisionResult,
)
from app.services import campaign as campaign_service
from app.services import product_matching
from app.services import revision as revision_service
from app.services.ai.dependencies import get_ai_professionalization_service, get_ai_revision_service
from app.services.ai.professionalization import AIProfessionalizationService, process_automatic_professionalization, queue_automatic_professionalization
from app.services.ai.revision_parser import AIRevisionService
from app.services.campaign_parser import parse_campaign_text

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


async def require_campaign_approval_scope(
    campaign_id: UUID,
    market_id: UUID = Depends(require_market_role(*MARKET_MUTATION_ROLES)),
    session: AsyncSession = Depends(get_campaign_session),
) -> None:
    """Establish tenant-scoped campaign access before approval-body validation."""
    await campaign_service.get_campaign(session, campaign_id, market_id)


@router.get("/builder/options", response_model=CampaignBuilderOptions)
async def campaign_builder_options(
    market_id: UUID = Depends(get_required_market_id),
    session: AsyncSession = Depends(get_campaign_session),
) -> CampaignBuilderOptions:
    return await campaign_service.get_builder_options(session, market_id)


@router.get("", response_model=ListResponse[CampaignListItem])
async def list_campaigns(
    search: str | None = None,
    status: str | None = None,
    channel: str | None = None,
    source_type: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    has_missing_products: bool | None = None,
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
        has_missing_products=has_missing_products,
        limit=limit,
        offset=offset,
    )
    return ListResponse(items=items, total=total, limit=limit, offset=offset)


@router.post("", response_model=CampaignDetail, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    payload: CampaignCreate,
    market_id: UUID = Depends(require_market_role(*MARKET_MUTATION_ROLES)),
    session: AsyncSession = Depends(get_campaign_session),
) -> CampaignDetail:
    return await campaign_service.create_campaign(session, payload, market_id)


@router.post("/parse-text", response_model=CampaignParseResponse)
async def parse_campaign_text_endpoint(
    payload: CampaignParseRequest,
    market_id: UUID = Depends(require_market_role(*MARKET_MUTATION_ROLES)),
) -> CampaignParseResponse:
    _ = market_id
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
    market_id: UUID = Depends(require_market_role(*MARKET_MUTATION_ROLES)),
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


@router.get("/{campaign_id}/items/{item_id}/image/content", include_in_schema=False)
async def campaign_item_image_content(
    campaign_id: UUID,
    item_id: UUID,
    market_id: UUID = Depends(get_required_market_id),
    session: AsyncSession = Depends(get_campaign_session),
):
    """Serve the exact effective campaign image behind a tenant-scoped URL."""
    from app.services.campaign_item_images import get_campaign_item_effective_image
    from app.services.rendering import storage_path_for_key

    image = await get_campaign_item_effective_image(session, campaign_id, item_id, market_id)
    if image is None or not image.storage_key:
        raise HTTPException(status_code=404, detail="Image not found.")
    path = storage_path_for_key(image.storage_key)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Image file not found.")
    return FileResponse(
        path,
        media_type=image.mime_type or "application/octet-stream",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/{campaign_id}/revisions", response_model=list[CampaignRevisionRead])
async def get_campaign_revisions(
    campaign_id: UUID,
    market_id: UUID = Depends(get_required_market_id),
    session: AsyncSession = Depends(get_campaign_session),
) -> list[CampaignRevisionRead]:
    return await revision_service.list_revisions(session, campaign_id, market_id)


@router.post("/{campaign_id}/revisions", response_model=RevisionResult)
async def create_campaign_revision(
    campaign_id: UUID,
    payload: PanelRevisionCommand,
    market_id: UUID = Depends(require_market_role(*MARKET_MUTATION_ROLES)),
    actor: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_campaign_session),
) -> RevisionResult:
    result = await revision_service.apply_revision(
        session, campaign_id, payload.trusted_command(), market_id, actor_id=actor.id
    )
    return RevisionResult(
        revision=CampaignRevisionRead.model_validate(result.revision),
        draft_revision=result.draft_revision,
        idempotent=result.idempotent,
    )


@router.post("/{campaign_id}/revisions/undo", response_model=RevisionResult)
async def undo_campaign_revision(
    campaign_id: UUID,
    payload: PanelUndoRevisionRequest,
    market_id: UUID = Depends(require_market_role(*MARKET_MUTATION_ROLES)),
    actor: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_campaign_session),
) -> RevisionResult:
    result = await revision_service.undo_latest_revision(
        session, campaign_id, payload.trusted_request(), market_id, actor_id=actor.id
    )
    return RevisionResult(
        revision=CampaignRevisionRead.model_validate(result.revision),
        draft_revision=result.draft_revision,
        idempotent=result.idempotent,
    )


@router.post("/{campaign_id}/revision-intent", response_model=AIRevisionProposalRead)
async def create_revision_intent_proposal(
    campaign_id: UUID,
    payload: RevisionIntentRequest,
    market_id: UUID = Depends(require_market_role(*MARKET_MUTATION_ROLES)),
    actor: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_campaign_session),
    ai_service: AIRevisionService = Depends(get_ai_revision_service),
) -> AIRevisionProposalRead:
    """Parse natural language into a stored proposal; never mutate the campaign."""
    return await ai_service.create_proposal(
        session,
        campaign_id=campaign_id,
        market_id=market_id,
        user_id=actor.id,
        request=payload,
    )


@router.post(
    "/{campaign_id}/revision-intent/{proposal_id}/apply",
    response_model=AIRevisionApplyResult,
)
async def apply_revision_intent_proposal(
    campaign_id: UUID,
    proposal_id: UUID,
    market_id: UUID = Depends(require_market_role(*MARKET_MUTATION_ROLES)),
    actor: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_campaign_session),
    ai_service: AIRevisionService = Depends(get_ai_revision_service),
) -> AIRevisionApplyResult:
    """Apply server-stored actions through the deterministic AI-1 service."""
    return await ai_service.apply_proposal(
        session,
        campaign_id=campaign_id,
        proposal_id=proposal_id,
        market_id=market_id,
        user_id=actor.id,
    )


@router.get("/{campaign_id}/professionalization", response_model=ProfessionalizationHistoryRead)
async def get_professionalization_history(campaign_id: UUID, market_id: UUID = Depends(get_required_market_id), session: AsyncSession = Depends(get_campaign_session), ai_service: AIProfessionalizationService = Depends(get_ai_professionalization_service)) -> ProfessionalizationHistoryRead:
    return await ai_service.history(session, campaign_id=campaign_id, market_id=market_id)

@router.post("/{campaign_id}/professionalization", response_model=ProfessionalizationRunRead)
async def create_professionalization_run(campaign_id: UUID, payload: ProfessionalizationRequest, market_id: UUID = Depends(require_market_role(*MARKET_MUTATION_ROLES)), actor: User = Depends(get_current_user), session: AsyncSession = Depends(get_campaign_session), ai_service: AIProfessionalizationService = Depends(get_ai_professionalization_service)) -> ProfessionalizationRunRead:
    return await ai_service.create_run(session, campaign_id=campaign_id, market_id=market_id, user_id=actor.id, request=payload)

@router.post("/{campaign_id}/professionalization/{run_id}/apply", response_model=ProfessionalizationApplyResult)
async def apply_professionalization_run(campaign_id: UUID, run_id: UUID, market_id: UUID = Depends(require_market_role(*MARKET_MUTATION_ROLES)), actor: User = Depends(get_current_user), session: AsyncSession = Depends(get_campaign_session), ai_service: AIProfessionalizationService = Depends(get_ai_professionalization_service)) -> ProfessionalizationApplyResult:
    return await ai_service.apply_run(session, campaign_id=campaign_id, run_id=run_id, market_id=market_id, user_id=actor.id)

@router.post("/{campaign_id}/professionalization/original", response_model=ProfessionalizationHistoryRead)
async def restore_original_professionalization(campaign_id: UUID, market_id: UUID = Depends(require_market_role(*MARKET_MUTATION_ROLES)), session: AsyncSession = Depends(get_campaign_session), ai_service: AIProfessionalizationService = Depends(get_ai_professionalization_service)) -> ProfessionalizationHistoryRead:
    return await ai_service.restore_original(session, campaign_id=campaign_id, market_id=market_id)
@router.get("/{campaign_id}/items/{item_id}/image-options", response_model=list[CampaignItemImageOptionRead])
async def campaign_item_image_options(
    campaign_id: UUID,
    item_id: UUID,
    market_id: UUID = Depends(require_market_role(*MARKET_MUTATION_ROLES)),
    session: AsyncSession = Depends(get_campaign_session),
) -> list[CampaignItemImageOptionRead]:
    item, images = await revision_service.list_item_image_options(session, campaign_id, item_id, market_id)
    return [
        CampaignItemImageOptionRead(
            id=image.id,
            label=f"Katalog görseli {index + 1}",
            is_primary=image.is_primary,
            is_selected=image.id == item.image_override_product_image_id,
        )
        for index, image in enumerate(images)
    ]
@router.get("/{campaign_id}/intelligence", response_model=CampaignIntelligenceEnvelope)
async def get_campaign_intelligence(
    campaign_id: UUID,
    market_id: UUID = Depends(get_required_market_id),
    session: AsyncSession = Depends(get_campaign_session),
) -> CampaignIntelligenceEnvelope:
    return await campaign_service.get_campaign_intelligence(session, campaign_id, market_id)


@router.post("/{campaign_id}/intelligence/analyze", response_model=CampaignIntelligenceEnvelope)
async def analyze_campaign_intelligence(
    campaign_id: UUID,
    market_id: UUID = Depends(require_market_role(*MARKET_MUTATION_ROLES)),
    session: AsyncSession = Depends(get_campaign_session),
) -> CampaignIntelligenceEnvelope:
    return await campaign_service.analyze_campaign_intelligence(session, campaign_id, market_id)


@router.post("/{campaign_id}/intelligence/apply", response_model=CampaignIntelligenceEnvelope)
async def apply_campaign_intelligence(
    campaign_id: UUID,
    market_id: UUID = Depends(require_market_role(*MARKET_MUTATION_ROLES)),
    actor: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_campaign_session),
) -> CampaignIntelligenceEnvelope:
    return await campaign_service.apply_campaign_intelligence(session, campaign_id, market_id, actor_id=actor.id)


@router.get("/{campaign_id}/preview-html", response_model=CampaignPreviewHtml)
async def get_campaign_preview_html(
    campaign_id: UUID,
    format: str | None = Query(default=None, pattern="^(pdf|png|instagram_post|instagram_story|whatsapp)$"),
    market_id: UUID = Depends(get_required_market_id),
    session: AsyncSession = Depends(get_campaign_session),
) -> CampaignPreviewHtml:
    return await campaign_service.get_campaign_preview_html(session, campaign_id, market_id, output_format=format)


@router.patch("/{campaign_id}", response_model=CampaignDetail)
async def update_campaign(
    campaign_id: UUID,
    payload: CampaignUpdate,
    market_id: UUID = Depends(require_market_role(*MARKET_MUTATION_ROLES)),
    actor: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_campaign_session),
) -> CampaignDetail:
    return await campaign_service.update_campaign(session, campaign_id, payload, market_id, actor_id=actor.id)


@router.post("/{campaign_id}/finalize", response_model=CampaignFinalizeResponse)
async def finalize_campaign(
    campaign_id: UUID,
    payload: CampaignApprovalRequest,
    market_id: UUID = Depends(require_market_role(*MARKET_MUTATION_ROLES)),
    actor: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_campaign_session),
    _: None = Depends(require_campaign_approval_scope),
    background_tasks: BackgroundTasks = None,
    ai_service: AIProfessionalizationService = Depends(get_ai_professionalization_service),
) -> CampaignFinalizeResponse:
    result = await campaign_service.finalize_campaign(session, campaign_id, market_id, expected_revision=payload.expected_revision, actor_id=actor.id)
    run = await queue_automatic_professionalization(session, campaign_id=campaign_id, market_id=market_id, user_id=actor.id)
    if run is not None and background_tasks is not None:
        background_tasks.add_task(_process_professionalization_background, run.id)
    return result


@router.post("/{campaign_id}/approve", response_model=CampaignFinalizeResponse)
async def approve_campaign(
    campaign_id: UUID,
    payload: CampaignApprovalRequest,
    market_id: UUID = Depends(require_market_role(*MARKET_MUTATION_ROLES)),
    actor: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_campaign_session),
    _: None = Depends(require_campaign_approval_scope),
    background_tasks: BackgroundTasks = None,
    ai_service: AIProfessionalizationService = Depends(get_ai_professionalization_service),
) -> CampaignFinalizeResponse:
    result = await campaign_service.finalize_campaign(session, campaign_id, market_id, expected_revision=payload.expected_revision, actor_id=actor.id)
    run = await queue_automatic_professionalization(session, campaign_id=campaign_id, market_id=market_id, user_id=actor.id)
    if run is not None and background_tasks is not None:
        background_tasks.add_task(_process_professionalization_background, run.id)
    return result


@router.delete("/{campaign_id}", response_model=CampaignDetail)
async def cancel_campaign(
    campaign_id: UUID,
    market_id: UUID = Depends(require_market_role(*MARKET_MUTATION_ROLES)),
    session: AsyncSession = Depends(get_campaign_session),
) -> CampaignDetail:
    return await campaign_service.cancel_campaign(session, campaign_id, market_id)


@router.post("/{campaign_id}/items", response_model=CampaignItemRead, status_code=status.HTTP_201_CREATED)
async def add_campaign_item(
    campaign_id: UUID,
    payload: CampaignItemCreate,
    market_id: UUID = Depends(require_market_role(*MARKET_MUTATION_ROLES)),
    actor: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_campaign_session),
) -> CampaignItemRead:
    return await campaign_service.add_campaign_item(session, campaign_id, payload, market_id, actor_id=actor.id)


@router.patch("/{campaign_id}/items/order", response_model=CampaignDetail)
async def reorder_campaign_items_before_item_route(
    campaign_id: UUID,
    payload: CampaignItemOrderUpdate,
    market_id: UUID = Depends(require_market_role(*MARKET_MUTATION_ROLES)),
    actor: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_campaign_session),
) -> CampaignDetail:
    return await campaign_service.reorder_campaign_items(session, campaign_id, payload.item_ids, market_id, actor_id=actor.id)


@router.patch("/{campaign_id}/items/{item_id}", response_model=CampaignItemRead)
async def update_campaign_item(
    campaign_id: UUID,
    item_id: UUID,
    payload: CampaignItemUpdate,
    market_id: UUID = Depends(require_market_role(*MARKET_MUTATION_ROLES)),
    actor: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_campaign_session),
) -> CampaignItemRead:
    return await campaign_service.update_campaign_item(session, campaign_id, item_id, payload, market_id, actor_id=actor.id)


@router.patch("/{campaign_id}/items/order", response_model=CampaignDetail)
async def reorder_campaign_items(
    campaign_id: UUID,
    payload: CampaignItemOrderUpdate,
    market_id: UUID = Depends(require_market_role(*MARKET_MUTATION_ROLES)),
    actor: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_campaign_session),
) -> CampaignDetail:
    return await campaign_service.reorder_campaign_items(session, campaign_id, payload.item_ids, market_id, actor_id=actor.id)


@router.post("/{campaign_id}/items/{item_id}/resolve-match", response_model=CampaignItemRead)
async def resolve_campaign_item_match(
    campaign_id: UUID,
    item_id: UUID,
    payload: CampaignItemResolveMatch,
    market_id: UUID = Depends(require_market_role(*MARKET_MUTATION_ROLES)),
    session: AsyncSession = Depends(get_campaign_session),
    actor: User = Depends(get_current_user),
) -> CampaignItemRead:
    return await campaign_service.resolve_campaign_item_match(
        session,
        campaign_id,
        item_id,
        payload,
        market_id,
        actor_id=actor.id,
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
    market_id: UUID = Depends(require_market_role(*MARKET_MUTATION_ROLES)),
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
    market_id: UUID = Depends(require_market_role(*MARKET_MUTATION_ROLES)),
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
    market_id: UUID = Depends(require_market_role(*MARKET_MUTATION_ROLES)),
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
    market_id: UUID = Depends(require_market_role(*MARKET_MUTATION_ROLES)),
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
    market_id: UUID = Depends(require_market_role(*MARKET_MUTATION_ROLES)),
    session: AsyncSession = Depends(get_campaign_session),
) -> ExportJobRead:
    return await campaign_service.create_export_job(session, campaign_id, payload, market_id)


@router.get("/{campaign_id}/files/{file_id}/download")
async def download_campaign_file(
    campaign_id: UUID,
    file_id: UUID,
    market_id: UUID = Depends(get_required_market_id),
    session: AsyncSession = Depends(get_campaign_session),
) -> FileResponse:
    path, media_type, filename = await campaign_service.get_campaign_file_download(
        session,
        campaign_id,
        file_id,
        market_id,
    )
    return FileResponse(path, media_type=media_type, filename=filename)


@router.get("/{campaign_id}/export-jobs", response_model=list[ExportJobRead])
async def list_export_jobs(
    campaign_id: UUID,
    market_id: UUID = Depends(get_required_market_id),
    session: AsyncSession = Depends(get_campaign_session),
) -> list[ExportJobRead]:
    return await campaign_service.list_export_jobs(session, campaign_id, market_id)

async def _process_professionalization_background(run_id: UUID) -> None:
    from app.core.database import AsyncSessionLocal
    if AsyncSessionLocal is None:
        return
    async with AsyncSessionLocal() as worker_session:
        await process_automatic_professionalization(worker_session, run_id=run_id, service=get_ai_professionalization_service())