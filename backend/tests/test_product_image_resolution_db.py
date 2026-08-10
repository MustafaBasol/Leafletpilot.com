from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

import app.models  # noqa: F401
from app.core.config import settings
from app.core.database import Base
from app.models import (
    Brand,
    Campaign,
    CampaignItem,
    Market,
    MarketProduct,
    Product,
    ProductAlias,
    ProductImage,
)
from app.services.product_identity import normalize_product_text
from app.services.product_image_resolution import resolve_campaign_product_images


@pytest.mark.asyncio
async def test_database_resolver_handles_representative_aliases_and_tenant_isolation() -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed resolution test skipped.")

    engine = create_async_engine(settings.test_database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    market_id = uuid4()
    other_market_id = uuid4()
    campaign_id = uuid4()
    original_facts = (
        ("Coca Cola 1L", Decimal("29.90")),
        ("Eti Burçak", Decimal("44.90")),
        ("Sütaş Yoğurt", Decimal("74.90")),
    )
    async with session_factory() as session:
        session.add_all(
            [
                Market(id=market_id, name="Resolution Market", slug=f"resolution-{market_id}"),
                Market(id=other_market_id, name="Other Market", slug=f"other-{other_market_id}"),
            ]
        )
        brands = {
            name: Brand(
                id=uuid4(),
                name=name,
                slug=f"{name.lower().replace(' ', '-')}-{uuid4().hex}",
                is_global=True,
                market_id=None,
            )
            for name in ("Coca Cola", "Eti", "Sütaş")
        }
        products = [
            _global_product(
                "Coca Cola Original 1L",
                brands["Coca Cola"],
                "global/catalog/coca.png",
                alias="Coca Cola 1L",
            ),
            _global_product(
                "Eti Burçak Klasik",
                brands["Eti"],
                "global/catalog/burcak.png",
                alias="Eti Burçak",
            ),
            _global_product(
                "Sütaş Yoğurt",
                brands["Sütaş"],
                "global/catalog/yogurt.png",
            ),
            Product(
                id=uuid4(),
                name="Coca Cola 1L",
                market_id=other_market_id,
                is_global=False,
                images=[_image("other-market/wrong.png")],
            ),
        ]
        campaign = Campaign(id=campaign_id, market_id=market_id, title="Resolution Acceptance")
        campaign.items = [
            CampaignItem(
                id=uuid4(),
                market_id=market_id,
                raw_line=f"{name} - {price}",
                incoming_name=name,
                price=price,
                sort_order=index,
            )
            for index, (name, price) in enumerate(original_facts)
        ]
        session.add_all([*brands.values(), *products, campaign])
        await session.commit()

        summary = await resolve_campaign_product_images(session, market_id, campaign_id)
        refreshed = await session.scalar(
            select(Campaign)
            .options(selectinload(Campaign.items))
            .where(Campaign.id == campaign_id, Campaign.market_id == market_id)
        )

        assert summary.resolved_count == 3
        assert summary.unresolved_count == 0
        assert [result.source for result in summary.results] == [
            "exact_alias",
            "exact_alias",
            "exact_catalog_identity",
        ]
        assert all(result.confidence >= Decimal("0.99") for result in summary.results)
        assert all(result.image_storage_key != "other-market/wrong.png" for result in summary.results)
        assert refreshed is not None
        assert tuple((item.incoming_name, item.price) for item in refreshed.items) == original_facts

    await engine.dispose()


@pytest.mark.asyncio
async def test_database_resolver_does_not_leak_market_product_or_historical_images_across_markets() -> None:
    """Phase 29 tenant isolation: a private MarketProduct image and a historical
    campaign-item image both belonging to another market must never resolve a
    same-named product for this market, even though the shared identity
    ("Su 5L") matches on both markets."""
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed resolution test skipped.")

    engine = create_async_engine(settings.test_database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    market_id = uuid4()
    other_market_id = uuid4()
    campaign_id = uuid4()
    other_historical_campaign_id = uuid4()
    async with session_factory() as session:
        session.add_all(
            [
                Market(id=market_id, name="Isolation Market", slug=f"isolation-{market_id}"),
                Market(id=other_market_id, name="Other Market", slug=f"iso-other-{other_market_id}"),
            ]
        )
        # Another market's private catalog entry with a usable image, same identity.
        session.add(
            MarketProduct(
                id=uuid4(),
                market_id=other_market_id,
                product_id=None,
                private_name="Su 5L",
                image_storage_key="other-market/private-water.png",
                image_quality_status="good",
                is_active=True,
            )
        )
        # Another market's historical campaign item, matched with a usable image,
        # same identity, but must not leak as a historical candidate.
        historical_product = Product(
            id=uuid4(),
            name="Su 5L Historical",
            is_global=False,
            market_id=other_market_id,
            images=[_image("other-market/historical-water.png")],
        )
        other_campaign = Campaign(id=other_historical_campaign_id, market_id=other_market_id, title="Other Market Campaign")
        other_campaign.items = [
            CampaignItem(
                id=uuid4(),
                market_id=other_market_id,
                raw_line="Su 5L - 9.90",
                incoming_name="Su 5L",
                price=Decimal("9.90"),
                sort_order=0,
                match_status="matched",
                product_id=historical_product.id,
            )
        ]
        campaign = Campaign(id=campaign_id, market_id=market_id, title="Isolation Acceptance")
        campaign.items = [
            CampaignItem(
                id=uuid4(),
                market_id=market_id,
                raw_line="Su 5L - 8.90",
                incoming_name="Su 5L",
                price=Decimal("8.90"),
                sort_order=0,
            )
        ]
        session.add_all([historical_product, other_campaign, campaign])
        await session.commit()

        summary = await resolve_campaign_product_images(session, market_id, campaign_id)

        assert summary.resolved_count == 0
        assert summary.unresolved_count == 1
        result = summary.results[0]
        assert result.image_storage_key is None
        assert result.image_storage_key != "other-market/private-water.png"
        assert result.image_storage_key != "other-market/historical-water.png"
        assert result.source == "fallback"

    await engine.dispose()


def _global_product(
    name: str,
    brand: Brand,
    storage_key: str,
    *,
    alias: str | None = None,
) -> Product:
    return Product(
        id=uuid4(),
        name=name,
        brand=brand,
        is_global=True,
        market_id=None,
        aliases=(
            [ProductAlias(alias=alias, normalized_alias=normalize_product_text(alias))]
            if alias
            else []
        ),
        images=[_image(storage_key)],
    )


def _image(storage_key: str) -> ProductImage:
    return ProductImage(storage_key=storage_key, is_primary=True, quality_status="good")
