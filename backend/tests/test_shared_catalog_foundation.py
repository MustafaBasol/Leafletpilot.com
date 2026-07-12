from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models import Market, MarketProduct, Product, ProductImage
from app.services.catalog import resolve_effective_product, update_product
from app.services.entitlements import has_capacity, resolve_capabilities, resolve_plan_code
from app.schemas.product import ProductUpdate


def test_effective_product_uses_market_name_image_and_category_overrides() -> None:
    product = Product(
        id=uuid4(),
        name="Global Milk",
        category_id=uuid4(),
        images=[
            ProductImage(
                storage_key="global/milk.png",
                quality_status="excellent",
                is_primary=True,
            )
        ],
    )
    market_product = MarketProduct(
        market_id=uuid4(),
        product_id=product.id,
        display_name_override="Local Milk",
        category_override_id=uuid4(),
        image_storage_key="markets/local-milk.png",
    )

    effective = resolve_effective_product(product, market_product)

    assert effective.name == "Local Milk"
    assert effective.image_storage_key == "markets/local-milk.png"
    assert effective.category_id == market_product.category_override_id


def test_effective_product_falls_back_to_approved_global_image_and_uncategorized() -> None:
    product = Product(
        id=uuid4(),
        name="Global Beans",
        images=[ProductImage(storage_key="global/beans.png", quality_status="good", is_primary=True)],
    )

    effective = resolve_effective_product(product, None)

    assert effective.name == "Global Beans"
    assert effective.image_storage_key == "global/beans.png"
    assert effective.category_id is None


def test_effective_product_uses_placeholder_when_no_image_exists() -> None:
    effective = resolve_effective_product(Product(id=uuid4(), name="No Image"), None)

    assert effective.image_storage_key is None
    assert effective.image_url is None


def test_unassigned_market_uses_safe_starter_defaults() -> None:
    capabilities = resolve_capabilities(Market(id=uuid4(), name="Test", slug="test"))

    assert resolve_plan_code(Market(id=uuid4(), name="Test", slug="test")) == "unassigned"
    assert capabilities.global_catalog_access is True
    assert capabilities.private_products_limit == 0
    assert capabilities.product_image_override is False
    assert capabilities.custom_template is False


def test_plan_capacity_supports_limited_and_unlimited_plans() -> None:
    assert has_capacity(24, 25)
    assert not has_capacity(25, 25)
    assert has_capacity(10000, None)


@pytest.mark.asyncio
async def test_market_cannot_update_global_product(monkeypatch) -> None:
    global_product = Product(id=uuid4(), name="Platform Product", is_global=True, market_id=None)

    async def fake_get_product(*args, **kwargs):
        return global_product

    monkeypatch.setattr("app.services.catalog.get_product", fake_get_product)

    with pytest.raises(HTTPException) as error:
        await update_product(object(), global_product.id, ProductUpdate(name="Changed"), uuid4())

    assert error.value.status_code == 403


def test_market_product_keeps_market_money_separate_from_canonical_product() -> None:
    product = Product(id=uuid4(), name="Global Oil", regular_price=Decimal("10.00"), is_global=True)
    market_product = MarketProduct(
        market_id=uuid4(),
        product_id=product.id,
        regular_price=Decimal("12.50"),
        promo_price=Decimal("11.00"),
    )

    assert product.regular_price == Decimal("10.00")
    assert market_product.regular_price == Decimal("12.50")
    assert market_product.promo_price == Decimal("11.00")
