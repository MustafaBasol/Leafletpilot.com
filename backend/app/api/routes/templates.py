from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_catalog_session, get_current_market_id, require_market_role
from app.core.roles import MarketRole
from app.schemas.common import ListResponse
from app.schemas.template import TemplateCreate, TemplatePreviewResponse, TemplateRead, TemplateUpdate
from app.services import templates as template_service
from app.services.template_gallery import generated_preview_path, recommendation_for
from app.services.template_presets import FLYER_PRESETS, SUPERMARKET_PRESETS, SUPERMARKET_STYLE_OPTIONS

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("/presets")
async def list_template_builder_presets() -> dict:
    """Return grid presets, page formats, price styles, and badge styles for the template builder."""
    return {
        "items": [*FLYER_PRESETS.values(), *SUPERMARKET_PRESETS.values()],
        "page_formats": [
            {"value": "a4_portrait", "label": "A4 dikey"},
            {"value": "a4_landscape", "label": "A4 yatay"},
        ],
        "price_styles": ["bold", "compact", *SUPERMARKET_STYLE_OPTIONS["price_style"]],
        "badge_styles": ["pill", "square", "sticker", "burst", "ribbon"],
        "header_styles": list(SUPERMARKET_STYLE_OPTIONS["header_style"]),
        "card_styles": list(SUPERMARKET_STYLE_OPTIONS["card_style"]),
        "image_treatments": list(SUPERMARKET_STYLE_OPTIONS["image_treatment"]),
    }


@router.get("/shared", response_model=ListResponse[TemplateRead])
async def shared_templates(market_id: UUID = Depends(get_current_market_id), session: AsyncSession = Depends(get_catalog_session)):
    # Intentionally returns ALL published global templates, including ones above
    # the market's current plan rank: customers must be able to see and preview
    # templates outside their plan (locked, with an upsell CTA), not have them
    # hidden entirely. The actual entitlement gate lives in adopt_global_template.
    items, total = await template_service.list_templates(session, market_id=market_id, include_global=True, search=None, is_active=True, is_global=True, limit=100, offset=0)
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


@router.post("/{template_id}/default", response_model=TemplateRead)
async def set_default_template(template_id: UUID, market_id: UUID = Depends(require_market_role(MarketRole.MARKET_ADMIN)), session: AsyncSession = Depends(get_catalog_session)) -> TemplateRead:
    """Keep the existing market default-template semantic behind a compact UI action."""
    template = await template_service.get_template(session, template_id, market_id)
    if template.is_global or template.market_id != market_id or not template.is_active:
        raise template_service._global_mutation_forbidden()
    from app.models import Market
    market = await session.get(Market, market_id)
    if market is None:
        raise template_service._not_found()
    market.default_template_id = template.id
    await session.commit()
    return template


@router.get("/{template_id}/preview-thumbnail", include_in_schema=False)
async def generated_preview_thumbnail(template_id: UUID, market_id: UUID = Depends(get_current_market_id), session: AsyncSession = Depends(get_catalog_session)):
    """Renderer-produced PNG. Access is guarded by the normal template scope."""
    template = await template_service.get_template(session, template_id, market_id)
    return FileResponse(await generated_preview_path(template), media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})


@router.get("/gallery")
async def template_gallery(product_count: int | None = Query(default=None, ge=1, le=100), market_id: UUID = Depends(get_current_market_id), session: AsyncSession = Depends(get_catalog_session)) -> dict:
    """A deduplicated gallery: stock templates appear once; adopted copies stay hidden."""
    templates, _ = await template_service.list_templates(session, market_id=market_id, include_global=True, search=None, is_active=None, is_global=None, limit=200, offset=0)
    mine = [item for item in templates if not item.is_global and item.source_template_id is None]
    ready = [item for item in templates if item.is_global and item.is_active and item.status == "published"]
    adopted = {item.source_template_id for item in templates if not item.is_global and item.source_template_id is not None}
    from app.models import Market
    market = await session.get(Market, market_id)
    recommended = recommendation_for([*ready, *mine], product_count, getattr(market, "default_template_id", None))
    return {"recommended": recommended, "ready": ready, "mine": mine, "adopted_template_ids": [str(item) for item in adopted if item], "product_count": product_count}


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
