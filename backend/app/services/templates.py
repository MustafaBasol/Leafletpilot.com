from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Campaign, CampaignItem, Market, Product, Template
from app.schemas.template import TemplateCreate, TemplateUpdate
from app.services.entitlements import has_capacity, require_capability, resolve_capabilities, resolve_plan_code
from app.services.preview_renderer import render_campaign_preview_html
from app.services.catalog import resolve_market_scope, slugify
from app.services.rendering import storage_path_for_key

THUMBNAIL_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
THUMBNAIL_SIGNATURES = {"image/png": b"\x89PNG\r\n\x1a\n", "image/jpeg": b"\xff\xd8\xff", "image/webp": b"RIFF"}
THUMBNAIL_LIMIT = 10 * 1024 * 1024


def apply_template_scope(
    statement: Select[tuple[Any]],
    market_id: UUID | None,
    include_global: bool,
) -> Select[tuple[Any]]:
    if market_id is None:
        return statement.where(Template.is_global.is_(True))
    if include_global:
        return statement.where(or_(Template.market_id == market_id, Template.is_global.is_(True)))
    return statement.where(Template.market_id == market_id)


async def list_templates(
    session: AsyncSession,
    *,
    market_id: UUID | None,
    include_global: bool,
    search: str | None,
    is_active: bool | None,
    is_global: bool | None,
    limit: int,
    offset: int,
) -> tuple[list[Template], int]:
    statement = apply_template_scope(select(Template), market_id, include_global)
    if search:
        statement = statement.where(
            or_(
                Template.name.ilike(f"%{search}%"),
                Template.slug.ilike(f"%{search}%"),
                Template.template_type.ilike(f"%{search}%"),
            )
        )
    if is_active is not None:
        statement = statement.where(Template.is_active.is_(is_active))
    if is_global is not None:
        statement = statement.where(Template.is_global.is_(is_global))
    if market_id is not None:
        statement = statement.where(
            or_(Template.is_global.is_(False), Template.status == "published")
        )
    return await _list(session, statement.order_by(Template.name), limit, offset)


async def create_template(session: AsyncSession, payload: TemplateCreate, market_id: UUID | None) -> Template:
    if payload.is_global:
        raise _global_mutation_forbidden()
    data = payload.model_dump()
    data["slug"] = data["slug"] or slugify(data["name"])
    data["market_id"] = resolve_market_scope(data["is_global"], market_id)
    return await _persist(session, Template(**data))


async def create_global_template(session: AsyncSession, payload: TemplateCreate) -> Template:
    data = payload.model_dump()
    data["slug"] = data["slug"] or slugify(data["name"])
    data.update({"is_global": True, "market_id": None, "status": "draft", "visibility": "shared", "version": 1})
    return await _persist(session, Template(**data))


async def duplicate_global_template(session: AsyncSession, source: Template) -> Template:
    if not source.is_global:
        raise _global_only()
    data = {key: getattr(source, key) for key in ("name", "slug", "description", "template_type", "config_json", "category", "minimum_plan")}
    data["name"] = f"{source.name} v{source.version + 1}"
    data["slug"] = f"{source.slug}-v{source.version + 1}"
    data.update({"market_id": None, "is_global": True, "status": "draft", "version": source.version + 1, "source_template_id": source.id, "source_version": source.version})
    template = Template(**data)
    session.add(template)
    await session.flush()
    if source.thumbnail_key:
        template.thumbnail_key = _copy_thumbnail(source.thumbnail_key, f"global/templates/{template.id}")
    await session.commit()
    return template


async def publish_global_template(session: AsyncSession, template: Template) -> Template:
    if not template.is_global:
        raise _global_only()
    template.status = "published"
    template.is_active = True
    template.published_at = datetime.now(UTC)
    template.archived_at = None
    return await _persist(session, template)


async def set_global_archive(session: AsyncSession, template: Template, archived: bool) -> Template:
    if not template.is_global:
        raise _global_only()
    template.status = "archived" if archived else "published"
    template.is_active = not archived
    template.archived_at = datetime.now(UTC) if archived else None
    return await _persist(session, template)


async def adopt_global_template(session: AsyncSession, source_id: UUID, market_id: UUID) -> Template:
    market = await session.get(Market, market_id)
    source = await session.scalar(select(Template).where(Template.id == source_id, Template.is_global.is_(True), Template.status == "published", Template.is_active.is_(True)))
    if market is None or source is None:
        raise _not_found()
    require_capability(market, "clone_global_template")
    existing = await session.scalar(select(Template).where(Template.market_id == market_id, Template.source_template_id == source.id))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This global template is already added to the market.")
    count = await session.scalar(select(func.count()).select_from(Template).where(Template.market_id == market_id, Template.is_active.is_(True))) or 0
    if not has_capacity(count, resolve_capabilities(market).private_templates_limit):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Your plan has reached its template limit.")
    data = {key: getattr(source, key) for key in ("name", "description", "template_type", "config_json", "category")}
    data.update({"slug": f"{source.slug}-adopted", "market_id": market_id, "is_global": False, "is_active": True, "status": "published", "visibility": "private", "minimum_plan": "starter", "source_template_id": source.id, "source_version": source.version, "version": 1})
    template = Template(**data)
    session.add(template)
    await session.flush()
    if source.thumbnail_key:
        template.thumbnail_key = _copy_thumbnail(source.thumbnail_key, f"markets/{market_id}/templates/{template.id}")
    await session.commit()
    return template


async def create_custom_template(session: AsyncSession, payload: TemplateCreate, market_id: UUID) -> Template:
    market = await session.get(Market, market_id)
    if market is None:
        raise _not_found()
    require_capability(market, "custom_template")
    count = await session.scalar(select(func.count()).select_from(Template).where(Template.market_id == market_id, Template.is_active.is_(True))) or 0
    if not has_capacity(count, resolve_capabilities(market).private_templates_limit):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Your plan has reached its template limit.")
    data = payload.model_dump(); data["slug"] = data["slug"] or slugify(data["name"])
    data.update({"market_id": market_id, "is_global": False, "status": "published", "visibility": "private", "version": 1})
    return await _persist(session, Template(**data))


async def upload_thumbnail(session: AsyncSession, template: Template, content: bytes, mime_type: str) -> Template:
    if mime_type not in THUMBNAIL_TYPES:
        raise HTTPException(status_code=415, detail="Only PNG, JPEG, and WebP images are allowed.")
    if len(content) > THUMBNAIL_LIMIT:
        raise HTTPException(status_code=413, detail="Template thumbnail must be 10 MiB or smaller.")
    if not content.startswith(THUMBNAIL_SIGNATURES[mime_type]) or (mime_type == "image/webp" and content[8:12] != b"WEBP"):
        raise HTTPException(status_code=422, detail="Image signature does not match the declared MIME type.")
    namespace = f"global/templates/{template.id}" if template.is_global else f"markets/{template.market_id}/templates/{template.id}"
    key = f"{namespace}/{uuid4()}{THUMBNAIL_TYPES[mime_type]}"
    path = storage_path_for_key(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    old_key = template.thumbnail_key
    template.thumbnail_key = key
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        path.unlink(missing_ok=True)
        raise
    if old_key:
        _remove_thumbnail(old_key)
    return template


async def remove_thumbnail(session: AsyncSession, template: Template) -> Template:
    old_key = template.thumbnail_key
    template.thumbnail_key = None
    await session.commit()
    if old_key:
        _remove_thumbnail(old_key)
    return template


def thumbnail_path(template: Template) -> tuple[Path, str]:
    if not template.thumbnail_key:
        raise _thumbnail_not_found()
    path = storage_path_for_key(template.thumbnail_key)
    if not path.is_file():
        raise _thumbnail_not_found()
    mime_type = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(path.suffix.lower(), "application/octet-stream")
    return path, mime_type


def _copy_thumbnail(source_key: str, namespace: str) -> str | None:
    try:
        source = storage_path_for_key(source_key)
        if not source.is_file():
            return None
        key = f"{namespace}/{uuid4()}{source.suffix.lower()}"
        target = storage_path_for_key(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
        return key
    except (OSError, ValueError):
        return None


def _remove_thumbnail(key: str) -> None:
    try:
        storage_path_for_key(key).unlink(missing_ok=True)
    except (OSError, ValueError):
        return


async def get_template(session: AsyncSession, template_id: UUID, market_id: UUID | None) -> Template:
    template = await session.scalar(apply_template_scope(select(Template).where(Template.id == template_id), market_id, True))
    if template is None:
        raise _not_found()
    return template


async def render_template_preview(session: AsyncSession, template_id: UUID, market_id: UUID | None) -> dict[str, Any]:
    if market_id is None:
        raise _not_found()
    template = await get_template(session, template_id, market_id)
    market = await session.get(Market, market_id)
    if market is None:
        raise _not_found()
    products = list(
        (
            await session.scalars(
                select(Product)
                .options(selectinload(Product.brand), selectinload(Product.images))
                .where(Product.market_id == market_id, Product.is_active.is_(True))
                .order_by(Product.name)
                .limit(8)
            )
        ).all()
    )
    generated_at = datetime.now(UTC)
    campaign = Campaign(
        id=uuid4(),
        market_id=market_id,
        title="Demo template preview",
        language=market.language,
        currency=market.currency,
        items=[],
    )
    campaign.market = market
    campaign.items = [
        CampaignItem(
            id=uuid4(),
            campaign_id=campaign.id,
            market_id=market_id,
            product_id=product.id,
            product=product,
            raw_line=product.name,
            incoming_name=product.name,
            display_name=product.name,
            price=Decimal("0.00"),
            currency=market.currency,
            sort_order=index,
            match_status="matched",
            created_at=generated_at,
        )
        for index, product in enumerate(products)
    ]
    return {
        "html": render_campaign_preview_html(campaign, template, generated_at=generated_at),
        "template_name": template.name,
        "generated_at": generated_at,
    }


async def update_template(
    session: AsyncSession,
    template_id: UUID,
    payload: TemplateUpdate,
    market_id: UUID | None,
) -> Template:
    template = await get_template(session, template_id, market_id)
    if template.is_global:
        raise _global_mutation_forbidden()
    updates = payload.model_dump(exclude_unset=True)
    if updates.get("is_global"):
        raise _global_mutation_forbidden()
    if "name" in updates and "slug" not in updates:
        updates["slug"] = slugify(updates["name"])
    if "is_global" in updates:
        updates["market_id"] = resolve_market_scope(updates["is_global"], market_id)
    for key, value in updates.items():
        setattr(template, key, value)
    return await _persist(session, template)


async def _list(
    session: AsyncSession,
    statement: Select[tuple[Any]],
    limit: int,
    offset: int,
) -> tuple[list[Template], int]:
    total_statement = select(func.count()).select_from(statement.order_by(None).subquery())
    total = await session.scalar(total_statement)
    result = await session.scalars(statement.limit(limit).offset(offset))
    return list(result.unique().all()), total or 0


async def _persist(session: AsyncSession, template: Template) -> Template:
    session.add(template)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Template record conflicts with existing data.",
        ) from exc
    return template


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found.")


def _global_mutation_forbidden() -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Global templates are platform-managed.")


def _global_only() -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This operation is only available for global templates.")


def _thumbnail_not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template thumbnail not found.")
