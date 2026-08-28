from copy import deepcopy
from uuid import uuid4

import pytest

from app.models import Campaign, CampaignItem, MarketProduct, Product, ProductImage
from app.services.campaign_item_images import (
    enrich_campaign_detail_images,
    resolve_effective_campaign_item_image,
)


def _product(market_id, *, image_key="products/primary.png"):
    product = Product(id=uuid4(), market_id=market_id, is_global=False, name="Test product")
    product.images = [
        ProductImage(
            id=uuid4(),
            product_id=product.id,
            storage_key=image_key,
            mime_type="image/png",
            is_primary=True,
            quality_status="good",
        )
    ]
    return product


def _item(market_id, product, market_product=None, override=None):
    return CampaignItem(
        id=uuid4(),
        market_id=market_id,
        product_id=product.id,
        market_product_id=market_product.id if market_product else None,
        raw_line=product.name,
        incoming_name=product.name,
        product=product,
        market_product=market_product,
        image_override=override,
    )


def test_campaign_image_priority_prefers_override_then_market_then_product():
    market_id = uuid4()
    product = _product(market_id)
    market_product = MarketProduct(
        id=uuid4(),
        market_id=market_id,
        product_id=product.id,
        product=product,
        image_storage_key="markets/primary.png",
        image_mime_type="image/jpeg",
    )
    override = ProductImage(
        id=uuid4(),
        product_id=product.id,
        storage_key="campaign/override.png",
        mime_type="image/webp",
    )
    item = _item(market_id, product, market_product, override)

    assert (
        resolve_effective_campaign_item_image(item, market_id).storage_key
        == "campaign/override.png"
    )
    item.image_override = None
    assert (
        resolve_effective_campaign_item_image(item, market_id).storage_key == "markets/primary.png"
    )
    market_product.image_storage_key = None
    assert (
        resolve_effective_campaign_item_image(item, market_id).storage_key == "products/primary.png"
    )


def test_campaign_image_resolution_is_safe_when_no_image_or_cross_market_reference():
    market_id = uuid4()
    other_market_id = uuid4()
    product = _product(other_market_id)
    item = _item(
        market_id,
        product,
        MarketProduct(
            id=uuid4(),
            market_id=other_market_id,
            product_id=product.id,
            product=product,
            image_storage_key="other/private.png",
        ),
    )

    image = resolve_effective_campaign_item_image(item, market_id)

    assert image.storage_key is None
    assert image.source is None


@pytest.mark.asyncio
async def test_frozen_campaign_detail_uses_snapshot_without_mutation_or_catalog_queries():
    market_id = uuid4()
    product = _product(market_id, image_key="products/new-primary.png")
    item = _item(market_id, product)
    campaign = Campaign(id=uuid4(), market_id=market_id, title="Frozen")
    campaign.items = [item]
    campaign.snapshot_json = {
        "items": [
            {
                "id": str(item.id),
                "image_key": "frozen/original.png",
                "image_mime_type": "image/jpeg",
            }
        ]
    }
    original_snapshot = deepcopy(campaign.snapshot_json)

    class NoQuerySession:
        async def scalars(self, statement):
            raise AssertionError("frozen detail must not query the current catalog")

    await enrich_campaign_detail_images(NoQuerySession(), campaign)

    assert item.effective_image_source == "frozen_snapshot"
    assert item.effective_image_url.endswith(f"/{item.id}/image/content")
    assert item.effective_image_refresh_key == f"frozen_snapshot:{item.id}"
    assert campaign.snapshot_json == original_snapshot


@pytest.mark.asyncio
async def test_matched_rows_are_enriched_without_per_row_catalog_queries():
    market_id = uuid4()
    campaign = Campaign(id=uuid4(), market_id=market_id, title="Batch")
    campaign.items = []
    for index in range(12):
        product = _product(market_id, image_key=f"products/{index}.png")
        market_product = MarketProduct(
            id=uuid4(), market_id=market_id, product_id=product.id, product=product
        )
        campaign.items.append(_item(market_id, product, market_product))

    class NoQuerySession:
        async def scalars(self, statement):
            raise AssertionError("matched rows must not resolve images one at a time")

    await enrich_campaign_detail_images(NoQuerySession(), campaign)

    assert all(item.effective_image_source == "product" for item in campaign.items)
    assert all(item.effective_image_url for item in campaign.items)
