from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_catalog_session, get_current_platform_admin
from app.models import PlatformAdmin, Template
from app.schemas.common import ListResponse
from app.schemas.template import TemplateCreate, TemplateRead, TemplateUpdate
from app.services import templates as template_service

router = APIRouter(prefix="/platform/templates", tags=["platform-templates"])


@router.get("", response_model=ListResponse[TemplateRead])
async def list_platform_templates(search: str | None = None, category: str | None = None, status_filter: str | None = Query(None, alias="status"), limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), _: PlatformAdmin = Depends(get_current_platform_admin), session: AsyncSession = Depends(get_catalog_session)):
    items, total = await template_service.list_templates(session, market_id=None, include_global=False, search=search, is_active=None, is_global=True, limit=limit, offset=offset)
    if category or status_filter:
        items = [item for item in items if (not category or item.category == category) and (not status_filter or item.status == status_filter)]
        total = len(items)
    return ListResponse(items=items, total=total, limit=limit, offset=offset)


@router.post("", response_model=TemplateRead, status_code=status.HTTP_201_CREATED)
async def create_platform_template(payload: TemplateCreate, _: PlatformAdmin = Depends(get_current_platform_admin), session: AsyncSession = Depends(get_catalog_session)):
    return await template_service.create_global_template(session, payload)


@router.patch("/{template_id}", response_model=TemplateRead)
async def update_platform_template(template_id: UUID, payload: TemplateUpdate, _: PlatformAdmin = Depends(get_current_platform_admin), session: AsyncSession = Depends(get_catalog_session)):
    template = await session.get(Template, template_id)
    if template is None or not template.is_global:
        raise template_service._not_found()
    if template.status == "published":
        template = await template_service.duplicate_global_template(session, template)
    updates = payload.model_dump(exclude_unset=True)
    updates.pop("is_global", None)
    for key, value in updates.items():
        setattr(template, key, value)
    return await template_service._persist(session, template)


@router.post("/{template_id}/publish", response_model=TemplateRead)
async def publish_platform_template(template_id: UUID, _: PlatformAdmin = Depends(get_current_platform_admin), session: AsyncSession = Depends(get_catalog_session)):
    template = await session.get(Template, template_id)
    if template is None: raise template_service._not_found()
    return await template_service.publish_global_template(session, template)


@router.post("/{template_id}/duplicate", response_model=TemplateRead, status_code=201)
async def duplicate_platform_template(template_id: UUID, _: PlatformAdmin = Depends(get_current_platform_admin), session: AsyncSession = Depends(get_catalog_session)):
    template = await session.get(Template, template_id)
    if template is None: raise template_service._not_found()
    return await template_service.duplicate_global_template(session, template)


@router.post("/{template_id}/archive", response_model=TemplateRead)
async def archive_platform_template(template_id: UUID, _: PlatformAdmin = Depends(get_current_platform_admin), session: AsyncSession = Depends(get_catalog_session)):
    template = await session.get(Template, template_id)
    if template is None: raise template_service._not_found()
    return await template_service.set_global_archive(session, template, True)


@router.post("/{template_id}/restore", response_model=TemplateRead)
async def restore_platform_template(template_id: UUID, _: PlatformAdmin = Depends(get_current_platform_admin), session: AsyncSession = Depends(get_catalog_session)):
    template = await session.get(Template, template_id)
    if template is None: raise template_service._not_found()
    return await template_service.set_global_archive(session, template, False)
