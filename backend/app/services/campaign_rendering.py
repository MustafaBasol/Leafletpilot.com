"""Canonical ORM loading for campaign preview and export rendering."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Campaign, CampaignItem, MarketProduct, Product
from app.services.catalog import resolve_effective_product


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
    campaign = await session.scalar(statement)
    if campaign is None:
        return None
    product_ids = [item.product_id for item in campaign.items if item.product_id]
    if product_ids:
        rows = await session.scalars(
            select(MarketProduct).where(MarketProduct.market_id == market_id, MarketProduct.product_id.in_(product_ids))
        )
        by_product = {row.product_id: row for row in rows}
        for item in campaign.items:
            if item.product_id in by_product:
                item._market_product = by_product[item.product_id]
    return campaign
