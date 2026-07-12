"""Canonical ORM loading for campaign preview and export rendering."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Campaign, CampaignItem, Product


def campaign_render_load_options():
    """Return the complete relationship graph read by the synchronous renderer."""
    return (
        selectinload(Campaign.market),
        selectinload(Campaign.template),
        selectinload(Campaign.items)
        .selectinload(CampaignItem.product)
        .selectinload(Product.brand),
        selectinload(Campaign.items)
        .selectinload(CampaignItem.product)
        .selectinload(Product.images),
    )


async def get_campaign_for_render(
    session: AsyncSession,
    campaign_id: UUID,
    market_id: UUID,
) -> Campaign | None:
    statement = (
        select(Campaign)
        .options(*campaign_render_load_options())
        .where(Campaign.id == campaign_id, Campaign.market_id == market_id)
    )
    return await session.scalar(statement)
