from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_catalog_session, get_current_market_id, require_market_role
from app.core.roles import MarketRole
from app.schemas.common import ListResponse
from app.schemas.template import TemplateCreate, TemplatePreviewResponse, TemplateRead, TemplateUpdate
from app.services import templates as template_service
from app.services.template_presets import FLYER_PRESETS
from app.services.entitlements import resolve_plan_code
from app.models import Market

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("/presets")
async def list_flyer_presets() -> dict:
    """Return the supported slot-count presets for the constrained flyer builder."""
    return {"items": list(FLYER_PRESETS.values())}


@router.get("/shared", response_model=ListResponse[TemplateRead])
async def shared_templates(market_id: UUID = Depends(get_current_market_id), session: AsyncSession = Depends(get_catalog_session)):
    items, total = await template_service.list_templates(session, market_id=market_id, include_global=True, search=None, is_active=True, is_global=True, limit=100, offset=0)
    market = await session.get(Market, market_id)
    ranks = {"starter": 0, "growth": 1, "pro": 2}
    rank = ranks.get(resolve_plan_code(market), 0)
    items = [item for item in items if ranks.get(item.minimum_plan, 0) <= rank]
    return ListResponse(items=items, total=total, limit=100, offset=0)


@router.post("/shared/{template_id}/adopt", response_model=TemplateRead, status_code=status.HTTP_201_CREATED)
async def adopt_template(template_id: UUID, market_id: UUID = Depends(require_market_role(MarketRole.MARKET_ADMIN)), session: AsyncSession = Depends(get_catalog_session)):
    return await template_service.adopt_global_template(session, template_id, market_id)


@router.get("/my-templates", response_model=ListResponse[TemplateRead])
async def my_templates(market_id: UUID = Depends(get_current_market_id), session: AsyncSession = Depends(get_catalog_session)):
    items, total = await template_service.list_templates(session, market_id=market_id, include_global=False, search=None, is_active=None, is_global=False, limit=100, offset=0)
    return ListResponse(items=items, total=total, limit=100, offset=0)


@router.post("/custom", response_model=TemplateRead, status_code=status.HTTP_201_CREATED)
async def custom_template(payload: TemplateCreate, market_id: UUID = Depends(require_market_role(MarketRole.MARKET_ADMIN)), session: AsyncSession = Depends(get_catalog_session)):
    return await template_service.create_custom_template(session, payload, market_id)


@router.post("/{template_id}/thumbnail", response_model=TemplateRead)
async def upload_market_thumbnail(template_id: UUID, request: Request, market_id: UUID = Depends(require_market_role(MarketRole.MARKET_ADMIN)), session: AsyncSession = Depends(get_catalog_session)):
    template = await template_service.get_template(session, template_id, market_id)
    if template.is_global or template.market_id != market_id:
        raise template_service._global_mutation_forbidden()
    return await template_service.upload_thumbnail(session, template, await request.body(), request.headers.get("content-type", "").split(";", 1)[0].lower())


@router.delete("/{template_id}/thumbnail", status_code=status.HTTP_204_NO_CONTENT)
async def delete_market_thumbnail(template_id: UUID, market_id: UUID = Depends(require_market_role(MarketRole.MARKET_ADMIN)), session: AsyncSession = Depends(get_catalog_session)):
    template = await template_service.get_template(session, template_id, market_id)
    if template.is_global or template.market_id != market_id:
        raise template_service._global_mutation_forbidden()
    await template_service.remove_thumbnail(session, template)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{template_id}/thumbnail", include_in_schema=False)
async def market_thumbnail(template_id: UUID, market_id: UUID = Depends(get_current_market_id), session: AsyncSession = Depends(get_catalog_session)):
    template = await template_service.get_template(session, template_id, market_id)
    path, mime_type = template_service.thumbnail_path(template)
    return FileResponse(path, media_type=mime_type)


@router.get("", response_model=ListResponse[TemplateRead])
async def list_templates(
    search: str | None = None,
    is_active: bool | None = None,
    is_global: bool | None = None,
    include_global: bool = True,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    market_id: UUID | None = Depends(get_current_market_id),
    session: AsyncSession = Depends(get_catalog_session),
) -> ListResponse[TemplateRead]:
    items, total = await template_service.list_templates(
        session,
        market_id=market_id,
        include_global=include_global,
        search=search,
        is_active=is_active,
        is_global=is_global,
        limit=limit,
        offset=offset,
    )
    return ListResponse(items=items, total=total, limit=limit, offset=offset)


@router.post("", response_model=TemplateRead, status_code=status.HTTP_201_CREATED)
async def create_template(
    payload: TemplateCreate,
    market_id: UUID = Depends(require_market_role(MarketRole.MARKET_ADMIN)),
    session: AsyncSession = Depends(get_catalog_session),
) -> TemplateRead:
    return await template_service.create_template(session, payload, market_id)


@router.get("/{template_id}", response_model=TemplateRead)
async def get_template(
    template_id: UUID,
    market_id: UUID | None = Depends(get_current_market_id),
    session: AsyncSession = Depends(get_catalog_session),
) -> TemplateRead:
    return await template_service.get_template(session, template_id, market_id)


@router.get("/{template_id}/preview-html", response_model=TemplatePreviewResponse)
async def preview_template(
    template_id: UUID,
    market_id: UUID | None = Depends(get_current_market_id),
    session: AsyncSession = Depends(get_catalog_session),
) -> TemplatePreviewResponse:
    result = await template_service.render_template_preview(session, template_id, market_id)
    return TemplatePreviewResponse(**result)


@router.patch("/{template_id}", response_model=TemplateRead)
async def update_template(
    template_id: UUID,
    payload: TemplateUpdate,
    market_id: UUID = Depends(require_market_role(MarketRole.MARKET_ADMIN)),
    session: AsyncSession = Depends(get_catalog_session),
) -> TemplateRead:
    return await template_service.update_template(session, template_id, payload, market_id)
