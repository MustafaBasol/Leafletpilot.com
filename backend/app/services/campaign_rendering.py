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
    return {
        "template_id": str(template.id) if template else None,
        "template_version": getattr(template, "version", None),
        "template_name": getattr(template, "name", None),
        "template_slug": getattr(template, "slug", None),
        "template_config": dict(template.config_json) if template and isinstance(template.config_json, dict) else {},
        "campaign_id": str(campaign.id),
        "title": campaign.title,
        "language": campaign.language,
        "currency": campaign.currency,
        "market_name": campaign.market.name if campaign.market is not None else "LeafletPilot",
        "builder_config": campaign.builder_config_json or {},
        "items": [
            {
                "id": str(item.id), "product_id": str(item.product_id) if item.product_id else None,
                "market_product_id": str(item.market_product_id) if item.market_product_id else None,
                "name": item.display_name or item.incoming_name,
                "resolved_name": resolve_effective_product(item.product, getattr(item, "_market_product", None) or item.market_product).name,
                "market_regular_price": str((getattr(item, "_market_product", None) or item.market_product).regular_price) if (getattr(item, "_market_product", None) or item.market_product) and (getattr(item, "_market_product", None) or item.market_product).regular_price is not None else None,
                "market_promo_price": str((getattr(item, "_market_product", None) or item.market_product).promo_price) if (getattr(item, "_market_product", None) or item.market_product) and (getattr(item, "_market_product", None) or item.market_product).promo_price is not None else None,
                "image_key": getattr((getattr(item, "_market_product", None) or item.market_product), "image_storage_key", None),
                "image_url": getattr((getattr(item, "_market_product", None) or item.market_product), "image_url", None),
                "price": str(item.price) if item.price is not None else None,
                "old_price": str(item.old_price) if item.old_price is not None else None,
                "currency": item.currency, "sort_order": item.sort_order,
            }
            for item in items
        ],
    }


def render_campaign_snapshot_html(snapshot: dict, *, generated_at) -> str:
    """Render a frozen campaign without consulting mutable catalog/template rows."""
    from types import SimpleNamespace
    from decimal import Decimal

    items = []
    for payload in snapshot.get("items", []):
        product = SimpleNamespace(
            name=payload.get("resolved_name") or payload.get("name") or "Unnamed product",
            images=[],
            brand=None,
            package_size=None,
            badge_text=None,
            category_id=None,
        )
        market_product = SimpleNamespace(
            display_name_override=None,
            private_brand_text=None,
            private_package_size=None,
            badge_text=None,
            currency=payload.get("currency") or snapshot.get("currency") or "EUR",
            image_storage_key=payload.get("image_key"),
            image_url=payload.get("image_url"),
            category_override_id=None,
        )
        item = SimpleNamespace(
            display_name=payload.get("name"),
            incoming_name=payload.get("name") or product.name,
            product=product,
            market_product=market_product,
            _market_product=market_product,
            quantity_label=None,
            unit_label=None,
            currency=payload.get("currency") or snapshot.get("currency") or "EUR",
            old_price=Decimal(str(payload["old_price"])) if payload.get("old_price") is not None else None,
            price=Decimal(str(payload["price"])) if payload.get("price") is not None else None,
            sort_order=payload.get("sort_order", 0),
            created_at=None,
            id=payload.get("id") or payload.get("sort_order", 0),
            match_status="matched",
        )
        items.append(item)
    campaign = SimpleNamespace(
        title=snapshot.get("title") or "Campaign",
        language=snapshot.get("language") or "tr",
        market=SimpleNamespace(name=snapshot.get("market_name") or "LeafletPilot", promo_profile_json={}),
        items=items,
    )
    template = SimpleNamespace(
        name=snapshot.get("template_name") or "Frozen template",
        slug=snapshot.get("template_slug") or "compact-weekly",
        config_json=snapshot.get("template_config") or {},
    )
    from app.services.preview_renderer import render_campaign_preview_html

    return render_campaign_preview_html(campaign, template, generated_at=generated_at)
