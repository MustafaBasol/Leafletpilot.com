from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_catalog_session, get_current_market_id
from app.schemas.common import ListResponse
from app.schemas.template import TemplateCreate, TemplateRead, TemplateUpdate
from app.services import templates as template_service

router = APIRouter(prefix="/templates", tags=["templates"])


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
    market_id: UUID | None = Depends(get_current_market_id),
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


@router.patch("/{template_id}", response_model=TemplateRead)
async def update_template(
    template_id: UUID,
    payload: TemplateUpdate,
    market_id: UUID | None = Depends(get_current_market_id),
    session: AsyncSession = Depends(get_catalog_session),
) -> TemplateRead:
    return await template_service.update_template(session, template_id, payload, market_id)
