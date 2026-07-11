from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Campaign, CampaignItem, Market, Product, Template
from app.schemas.template import TemplateCreate, TemplateUpdate
from app.services.preview_renderer import render_campaign_preview_html
from app.services.catalog import resolve_market_scope, slugify


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
    return await _list(session, statement.order_by(Template.name), limit, offset)


async def create_template(session: AsyncSession, payload: TemplateCreate, market_id: UUID | None) -> Template:
    data = payload.model_dump()
    data["slug"] = data["slug"] or slugify(data["name"])
    data["market_id"] = resolve_market_scope(data["is_global"], market_id)
    return await _persist(session, Template(**data))


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
                .options(selectinload(Product.images))
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
    updates = payload.model_dump(exclude_unset=True)
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
