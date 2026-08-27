from copy import deepcopy
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models import Campaign
from app.services import campaign as campaign_service
from app.services.campaign_intelligence import (
    CampaignIntelligenceEngine,
    calculate_promotion,
)
from app.services.preview_renderer import _apply_campaign_intelligence


@pytest.mark.parametrize(
    ("price", "old_price", "discount", "saving", "warning"),
    [
        ("8", "10", Decimal("20.0"), Decimal("2.00"), None),
        ("10", "10", Decimal("0.0"), Decimal("0.00"), None),
        ("12", "10", Decimal("0.0"), Decimal("0.00"), "sale price is above original price"),
        (None, "10", None, None, "invalid or incomplete price data"),
        ("bad", "10", None, None, "invalid or incomplete price data"),
        ("0", "-2", None, None, "invalid or incomplete price data"),
    ],
)
def test_promotion_math_is_safe(price, old_price, discount, saving, warning) -> None:
    result = calculate_promotion({"price": price, "old_price": old_price})

    assert result["discountPercent"] == discount
    assert result["absoluteSaving"] == saving
    assert result["warning"] == warning
    if not discount:
        assert result["recommendedBadge"] is None


def _item(
    index: int,
    *,
    price: str = "7",
    old_price: str = "10",
    image: bool = True,
    category: str | None = "pantry",
    is_hero: bool = False,
    name: str | None = None,
) -> dict:
    return {
        "id": f"product-{index}",
        "name": name or f"Product {index}",
        "price": price,
        "old_price": old_price,
        "image_key": f"products/{index}.png" if image else None,
        "category": category,
        "is_hero": is_hero,
        "currency": "EUR",
        "sort_order": index,
    }


def _analyze(items: list[dict]) -> dict:
    return CampaignIntelligenceEngine().analyze("campaign-25", items)


def test_high_discount_image_is_strong_hero_candidate() -> None:
    result = _analyze([_item(1, price="4"), _item(2, price="8")])

    assert result["products"][0]["productId"] == "product-1"
    assert result["products"][0]["role"] == "hero"
    assert "60.0% discount" in result["products"][0]["reasons"]


def test_manual_hero_wins_even_with_weaker_commercial_score() -> None:
    result = _analyze([_item(1, price="3"), _item(2, price="9", is_hero=True)])

    assert result["products"][0]["productId"] == "product-2"
    assert result["products"][0]["priorityScore"] == 100
    assert "manual hero selection" in result["products"][0]["reasons"]


def test_viable_image_can_beat_slightly_stronger_missing_image() -> None:
    result = _analyze([_item(1, price="3", image=False), _item(2, price="4", image=True)])

    assert result["products"][0]["productId"] == "product-2"
    assert result["products"][0]["role"] == "hero"


@pytest.mark.parametrize("count", [1, 4, 9, 16, 30])
def test_hero_count_is_bounded(count: int) -> None:
    result = _analyze([_item(index) for index in range(count)])

    assert sum(product["role"] == "hero" for product in result["products"]) <= 1


def test_strategy_covers_few_many_image_rich_and_image_poor_campaigns() -> None:
    few = _analyze([_item(index) for index in range(3)])
    many = _analyze([_item(index) for index in range(12)])
    image_poor = _analyze([_item(index, image=False) for index in range(4)])

    assert few["strategy"]["composition"] == "hero_plus_grid"
    assert many["strategy"]["composition"] == "dense_value_grid"
    assert image_poor["strategy"]["campaignType"] == "price_led"


def test_grouping_uses_generic_categories_and_safe_fallbacks() -> None:
    mixed = _analyze([_item(1, category="fresh"), _item(2, category="drinks")])
    missing = _analyze([_item(1, category=None, price="4"), _item(2, category=None, price="9")])
    one = _analyze([_item(1, category="pantry"), _item(2, category="pantry")])

    assert {group["key"] for group in mixed["groups"]} == {"fresh", "drinks"}
    assert {group["key"] for group in missing["groups"]} <= {"value", "other_offers"}
    assert one["groups"] == [{"key": "pantry", "productCount": 2, "reason": "source category"}]


def test_empty_campaign_and_explainability_are_safe() -> None:
    empty = _analyze([])
    result = _analyze([_item(1, price="8", image=False)])

    assert empty["products"] == []
    assert empty["warnings"] == ["Campaign has no products to analyze."]
    assert "20.0% discount" in result["products"][0]["reasons"]
    assert "product image missing" in result["products"][0]["reasons"]


def test_applied_plan_preserves_product_order_and_manual_facts() -> None:
    items = [_item(1, price="8"), _item(2, price="4", is_hero=True)]
    items[0]["badge"] = "Store special"
    plan = _analyze(deepcopy(items))

    applied = _apply_campaign_intelligence(items, {"campaign_intelligence": plan})

    assert applied is not None
    ordered, roles, strategy = applied
    assert [item["id"] for item in ordered] == ["product-1", "product-2"]
    assert roles == ["standard", "hero"]
    assert next(item for item in ordered if item["id"] == "product-1")["badge"] == "Store special"
    assert strategy in {"hero_plus_grid", "balanced_grid", "dense_value_grid"}


def test_renderer_ignores_missing_unsupported_and_stale_recommendations() -> None:
    items = [_item(1), _item(2)]
    assert _apply_campaign_intelligence(items, {}) is None
    assert _apply_campaign_intelligence(
        items,
        {"campaign_intelligence": {"engineVersion": "future", "products": []}},
    ) is None

    plan = _analyze([_item(1)])
    applied = _apply_campaign_intelligence(items, {"campaign_intelligence": plan})

    assert applied is not None
    assert [item["id"] for item in applied[0]] == ["product-1", "product-2"]



@pytest.mark.asyncio
async def test_invalid_campaign_lookup_is_market_scoped() -> None:
    class SessionDouble:
        async def scalar(self, statement):
            rendered = str(statement)
            assert "campaigns.id =" in rendered
            assert "campaigns.market_id =" in rendered

    with pytest.raises(HTTPException) as exc_info:
        await campaign_service.get_campaign(SessionDouble(), uuid4(), uuid4())

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_empty_campaign_analysis_is_persisted_without_content_mutation(monkeypatch) -> None:
    market_id = uuid4()
    campaign = Campaign(id=uuid4(), market_id=market_id, title="Empty")
    persisted = []

    async def fake_get_campaign(session, campaign_id, scoped_market_id):
        assert campaign_id == campaign.id
        assert scoped_market_id == market_id
        return campaign

    async def fake_persist(session, instance, *, commit=True):
        persisted.append(instance)
        return instance

    def fake_live_payload(campaign_value, template, *, include_applied_intelligence=True):
        assert campaign_value is campaign
        assert include_applied_intelligence is False
        return {"items": []}

    monkeypatch.setattr(campaign_service, "get_campaign", fake_get_campaign)
    monkeypatch.setattr(campaign_service, "_persist", fake_persist)
    monkeypatch.setattr("app.services.preview_renderer._live_payload", fake_live_payload)

    envelope = await campaign_service.analyze_campaign_intelligence(
        object(),
        campaign.id,
        market_id,
    )

    assert envelope.result.products == []
    assert envelope.result.warnings == ["Campaign has no products to analyze."]
    assert persisted == [campaign]
    assert campaign.builder_config_json is None


@pytest.mark.asyncio
async def test_apply_requires_a_saved_analysis(monkeypatch) -> None:
    campaign = Campaign(id=uuid4(), market_id=uuid4(), title="Not analyzed")

    async def fake_get_campaign(session, campaign_id, market_id, *, for_update=False):
        assert for_update is True
        return campaign

    monkeypatch.setattr(campaign_service, "get_campaign", fake_get_campaign)

    with pytest.raises(HTTPException) as exc_info:
        await campaign_service.apply_campaign_intelligence(
            object(),
            campaign.id,
            campaign.market_id,
        )

    assert exc_info.value.status_code == 409



def test_manual_edit_invalidation_retains_analysis_but_clears_applied_plan() -> None:
    campaign = Campaign(id=uuid4(), market_id=uuid4(), title="Manual override")
    saved_analysis = _analyze([_item(1)])
    campaign.intelligence_json = saved_analysis
    campaign.builder_config_json = {
        "smart_composition": True,
        "campaign_intelligence": saved_analysis,
        "headline": "Saved choice",
    }

    campaign_service._clear_applied_intelligence(campaign)

    assert campaign.intelligence_json == saved_analysis
    assert campaign.builder_config_json == {
        "smart_composition": True,
        "headline": "Saved choice",
    }
