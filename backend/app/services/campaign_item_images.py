"""Tenant-safe effective image resolution shared by campaign reads and rendering."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Campaign, CampaignItem, MarketProduct, Product, ProductImage


@dataclass(frozen=True)
class EffectiveCampaignItemImage:
    """A storage-backed image selected using the campaign renderer's priority."""

    storage_key: str | None
    mime_type: str | None
    source: str | None
    refresh_key: str | None


def _visible_product(product: Product | None, market_id: UUID) -> Product | None:
    if product is None:
        return None
    if product.market_id == market_id or (product.is_global and product.market_id is None):
        return product
    return None


def _safe_market_product(
    item: CampaignItem, market_id: UUID, market_product: MarketProduct | None
) -> MarketProduct | None:
    if market_product is None or market_product.market_id != market_id:
        return None
    if item.market_product_id is not None and market_product.id != item.market_product_id:
        return None
    return market_product


def _primary_product_image(product: Product | None) -> ProductImage | None:
    return next(
        (
            image
            for image in (getattr(product, "images", []) or [])
            if image.is_primary and image.quality_status != "missing" and image.storage_key
        ),
        None,
    )


def _refresh_key(source: str, image_id: UUID, changed_at: object | None) -> str:
    return f"{source}:{image_id}:{changed_at or 'current'}"


def resolve_effective_campaign_item_image(
    item: CampaignItem,
    market_id: UUID,
    *,
    market_product: MarketProduct | None = None,
    frozen_item: dict[str, Any] | None = None,
) -> EffectiveCampaignItemImage:
    """Apply the canonical campaign image priority without exposing storage keys.

    Frozen campaigns resolve solely from their render payload so that a later
    catalog edit cannot alter the historical brochure shown in Campaign Detail.
    """
    if frozen_item is not None:
        image_key = frozen_item.get("image_key")
        if image_key:
            return EffectiveCampaignItemImage(
                storage_key=str(image_key),
                mime_type=frozen_item.get("image_mime_type") or "image/png",
                source="frozen_snapshot",
                refresh_key=f"frozen_snapshot:{item.id}",
            )
        return EffectiveCampaignItemImage(None, None, None, None)

    safe_market_product = _safe_market_product(
        item,
        market_id,
        market_product or getattr(item, "_market_product", None) or item.market_product,
    )
    product = _visible_product(item.product, market_id)
    if product is None and safe_market_product is not None:
        product = _visible_product(safe_market_product.product, market_id)
    override = item.image_override
    # Revision image options are scoped to the item product. Keeping the check
    # here makes corrupt or cross-tenant FK values fall back safely as well.
    if (
        override is not None
        and product is not None
        and override.product_id == product.id
        and override.storage_key
    ):
        return EffectiveCampaignItemImage(
            storage_key=override.storage_key,
            mime_type=override.mime_type or "image/png",
            source="campaign_override",
            refresh_key=_refresh_key(
                "campaign_override", override.id, getattr(override, "created_at", None)
            ),
        )
    if safe_market_product is not None and safe_market_product.image_storage_key:
        return EffectiveCampaignItemImage(
            storage_key=safe_market_product.image_storage_key,
            mime_type=safe_market_product.image_mime_type or "image/png",
            source="market_product",
            refresh_key=_refresh_key(
                "market_product",
                safe_market_product.id,
                getattr(safe_market_product, "updated_at", None),
            ),
        )
    image = _primary_product_image(product)
    if image is not None:
        return EffectiveCampaignItemImage(
            storage_key=image.storage_key,
            mime_type=image.mime_type or "image/png",
            source="product",
            refresh_key=_refresh_key("product", image.id, getattr(image, "created_at", None)),
        )
    return EffectiveCampaignItemImage(None, None, None, None)


def _snapshot_items(campaign: Campaign) -> dict[str, dict[str, Any]]:
    payload = campaign.snapshot_json or {}
    return {
        str(item.get("id")): item
        for item in payload.get("items", [])
        if isinstance(item, dict) and item.get("id")
    }


async def enrich_campaign_detail_images(session: AsyncSession, campaign: Campaign) -> None:
    """Attach derived image fields to campaign items using one scoped batch lookup."""
    snapshot_items = _snapshot_items(campaign) if campaign.snapshot_json else {}
    fallback_product_ids = {
        item.product_id
        for item in campaign.items
        if item.product_id
        and _safe_market_product(item, campaign.market_id, item.market_product) is None
    }
    fallback_by_product: dict[UUID, MarketProduct] = {}
    if fallback_product_ids and not snapshot_items:
        rows = await session.scalars(
            select(MarketProduct)
            .options(selectinload(MarketProduct.product).selectinload(Product.images))
            .where(
                MarketProduct.market_id == campaign.market_id,
                MarketProduct.product_id.in_(fallback_product_ids),
            )
        )
        fallback_by_product = {row.product_id: row for row in rows if row.product_id}

    for item in campaign.items:
        image = resolve_effective_campaign_item_image(
            item,
            campaign.market_id,
            market_product=fallback_by_product.get(item.product_id) or item.market_product,
            frozen_item=snapshot_items.get(str(item.id)) if snapshot_items else None,
        )
        item.effective_image_source = image.source
        item.effective_image_refresh_key = image.refresh_key
        item.effective_image_url = (
            f"/api/campaigns/{campaign.id}/items/{item.id}/image/content"
            if image.storage_key
            else None
        )


async def get_campaign_item_effective_image(
    session: AsyncSession, campaign_id: UUID, item_id: UUID, market_id: UUID
) -> EffectiveCampaignItemImage | None:
    """Resolve one protected content request without trusting client image IDs."""
    campaign = await session.scalar(
        select(Campaign)
        .options(selectinload(Campaign.items))
        .where(Campaign.id == campaign_id, Campaign.market_id == market_id)
    )
    if campaign is None:
        return None
    item = next((candidate for candidate in campaign.items if candidate.id == item_id), None)
    if item is None:
        return None
    frozen_item = _snapshot_items(campaign).get(str(item.id)) if campaign.snapshot_json else None
    if frozen_item is not None:
        return resolve_effective_campaign_item_image(item, market_id, frozen_item=frozen_item)

    item = await session.scalar(
        select(CampaignItem)
        .options(
            selectinload(CampaignItem.product).selectinload(Product.images),
            selectinload(CampaignItem.market_product)
            .selectinload(MarketProduct.product)
            .selectinload(Product.images),
            selectinload(CampaignItem.image_override),
        )
        .where(
            CampaignItem.id == item_id,
            CampaignItem.campaign_id == campaign_id,
            CampaignItem.market_id == market_id,
        )
    )
    if item is None:
        return None
    return resolve_effective_campaign_item_image(item, market_id)
