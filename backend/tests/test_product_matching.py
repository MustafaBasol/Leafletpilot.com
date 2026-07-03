from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.core.config import settings
from app.core.database import Base
from app.models import Campaign, CampaignItem, Market, Product, ProductAlias
from app.services.product_matching import (
    find_product_suggestions_for_text,
    generate_suggestions_for_campaign,
    generate_suggestions_for_campaign_item,
    normalize_barcode,
    normalize_product_text,
    rank_product_suggestions,
)


def _product(
    name: str,
    *,
    barcode: str | None = None,
    aliases: list[str] | None = None,
    market_id=None,
    is_global: bool = False,
    is_active: bool = True,
) -> Product:
    product = Product(
        id=uuid4(),
        name=name,
        barcode=barcode,
        market_id=market_id,
        is_global=is_global,
        is_active=is_active,
    )
    product.aliases = [
        ProductAlias(id=uuid4(), alias=alias, normalized_alias=normalize_product_text(alias))
        for alias in aliases or []
    ]
    return product


def test_normalize_product_text_handles_turkish_punctuation_whitespace_and_units() -> None:
    assert normalize_product_text("  ŞEKER--1 Kilogram!! ") == "seker 1kg"
    assert normalize_product_text("Süt, 1 litre") == "sut 1l"
    assert normalize_product_text("ÇİKOLATA\t100 gr.") == "cikolata 100g"
    assert normalize_barcode(" 869-123 45 ") == "86912345"
    assert normalize_barcode("abc") is None


def test_scoring_exact_alias_fuzzy_and_barcode_priority() -> None:
    cola = _product("Coca Cola 2L", barcode="8690001", aliases=["Kola 2 LT"])
    cola_zero = _product("Coca Cola Zero 2L", barcode="8690002")
    products = [cola_zero, cola]

    barcode = rank_product_suggestions(products, "Kola 2L", barcode="8690001")
    assert barcode[0].product.id == cola.id
    assert barcode[0].score == Decimal("100.00")
    assert barcode[0].reason == "barcode"

    exact = rank_product_suggestions(products, "coca cola 2 litre")
    assert exact[0].product.id == cola.id
    assert exact[0].score == Decimal("98.00")
    assert exact[0].reason == "exact"

    alias = rank_product_suggestions(products, "kola 2 l")
    assert alias[0].product.id == cola.id
    assert alias[0].score == Decimal("96.00")
    assert alias[0].reason == "alias"

    fuzzy = rank_product_suggestions(products, "coca cola zer 2l")
    assert fuzzy[0].product.id == cola_zero.id
    assert fuzzy[0].reason == "fuzzy"
    assert fuzzy[0].score < Decimal("98.00")


def test_duplicate_products_are_returned_once_and_ranked_by_score() -> None:
    product = _product("Whole Milk 1L", aliases=["Milk 1L", "Whole Milk"])
    other = _product("Whole Milk 2L")

    suggestions = rank_product_suggestions([other, product], "milk 1 litre")

    assert [suggestion.product.id for suggestion in suggestions].count(product.id) == 1
    assert suggestions[0].product.id == product.id
    assert suggestions[0].score >= suggestions[-1].score


@pytest.mark.asyncio
async def test_product_matching_integration_runs_when_test_database_url_is_configured() -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed product matching tests skipped.")

    engine = create_async_engine(settings.test_database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    market_id = uuid4()
    other_market_id = uuid4()
    async with session_factory() as session:
        session.add_all(
            [
                Market(id=market_id, name=f"Matching Market {market_id}", slug=f"mm-{market_id}"),
                Market(id=other_market_id, name=f"Other Market {other_market_id}", slug=f"om-{other_market_id}"),
            ]
        )
        global_product = Product(id=uuid4(), name="Global Sugar 1KG", is_global=True, market_id=None)
        market_product = Product(id=uuid4(), name="Market Milk 1L", market_id=market_id, is_global=False)
        market_product.aliases = [
            ProductAlias(alias="Market Sut 1 LT", normalized_alias=normalize_product_text("Market Sut 1 LT"))
        ]
        other_product = Product(id=uuid4(), name="Other Market Cheese", market_id=other_market_id)
        inactive_product = Product(id=uuid4(), name="Inactive Milk 1L", market_id=market_id, is_active=False)
        barcode_product = Product(id=uuid4(), name="Barcode Cola 2L", barcode="8690001", market_id=market_id)
        campaign = Campaign(id=uuid4(), title="Matching Campaign", market_id=market_id)
        exact_item = CampaignItem(
            id=uuid4(),
            campaign_id=campaign.id,
            market_id=market_id,
            raw_line="Market Milk 1L",
            incoming_name="Market Milk 1L",
        )
        fuzzy_item = CampaignItem(
            id=uuid4(),
            campaign_id=campaign.id,
            market_id=market_id,
            raw_line="Global Sugr 1KG",
            incoming_name="Global Sugr 1KG",
        )
        barcode_item = CampaignItem(
            id=uuid4(),
            campaign_id=campaign.id,
            market_id=market_id,
            raw_line="Cola",
            incoming_name="Wrong Name",
            parsed_payload={"barcode": "8690001"},
        )
        missing_item = CampaignItem(
            id=uuid4(),
            campaign_id=campaign.id,
            market_id=market_id,
            raw_line="No Such Product",
            incoming_name="No Such Product",
        )
        session.add_all(
            [
                global_product,
                market_product,
                other_product,
                inactive_product,
                barcode_product,
                campaign,
                exact_item,
                fuzzy_item,
                barcode_item,
                missing_item,
            ]
        )
        await session.commit()

        visible = await find_product_suggestions_for_text(session, market_id, "Other Market Cheese")
        assert visible == []

        item, suggestions = await generate_suggestions_for_campaign_item(
            session, market_id, campaign.id, exact_item.id
        )
        assert item.match_status == "matched"
        assert item.product_id == market_product.id
        assert suggestions[0].reason == "exact"

        item, suggestions = await generate_suggestions_for_campaign_item(
            session, market_id, campaign.id, barcode_item.id
        )
        assert item.match_status == "matched"
        assert item.product_id == barcode_product.id
        assert suggestions[0].reason == "barcode"

        item, suggestions = await generate_suggestions_for_campaign_item(
            session, market_id, campaign.id, fuzzy_item.id
        )
        assert item.match_status == "low_confidence"
        assert suggestions[0].reason == "fuzzy"

        item, suggestions = await generate_suggestions_for_campaign_item(
            session, market_id, campaign.id, missing_item.id
        )
        assert item.match_status == "not_found"
        assert suggestions == []

        summary = await generate_suggestions_for_campaign(session, market_id, campaign.id)
        assert summary.items_processed == 4
        assert summary.auto_matched == 2
        assert summary.low_confidence == 1
        assert summary.not_found == 1
        assert summary.suggestions_created >= 3

    await engine.dispose()
