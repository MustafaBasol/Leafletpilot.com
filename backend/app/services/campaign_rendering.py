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
        selectinload(Campaign.items).selectinload(CampaignItem.market_product),
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
    market_product_ids = [item.market_product_id for item in campaign.items if item.market_product_id]
    if product_ids:
        rows = await session.scalars(
            select(MarketProduct).where(MarketProduct.market_id == market_id, MarketProduct.product_id.in_(product_ids))
        )
        by_product = {row.product_id: row for row in rows}
        for item in campaign.items:
            if item.product_id in by_product:
                item._market_product = by_product[item.product_id]
    if market_product_ids:
        rows = await session.scalars(
            select(MarketProduct).where(MarketProduct.market_id == market_id, MarketProduct.id.in_(market_product_ids))
        )
        by_id = {row.id: row for row in rows}
        for item in campaign.items:
            if item.market_product_id in by_id:
                item._market_product = by_id[item.market_product_id]
    return campaign


def build_campaign_render_payload(campaign: Campaign, template) -> dict:
    """Single preview/export input contract; frozen campaigns use this exact data."""
    if campaign.snapshot_json:
        return campaign.snapshot_json
    items = sorted((item for item in campaign.items if item.match_status != "excluded"), key=lambda item: (item.sort_order, str(item.id)))
    from app.services.preview_renderer import _live_payload
    return _live_payload(campaign, template)


def render_campaign_snapshot_html(snapshot: dict, *, generated_at) -> str:
    """Render a frozen campaign without consulting mutable catalog/template rows."""
    from app.services.preview_renderer import render_render_payload_html
    return render_render_payload_html(snapshot, generated_at=generated_at)
