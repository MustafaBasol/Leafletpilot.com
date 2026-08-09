from copy import deepcopy

import pytest

from app.services.merchandising import (
    choose_composition_strategy,
    create_composition_plan,
    score_product,
)


def _items(count: int) -> list[dict]:
    categories = ("produce", "dairy", "bakery", "pantry")
    return [
        {
            "id": f"product-{index:02d}",
            "name": f"Product {index}",
            "brand": f"Brand {index % 5}",
            "category": categories[index % len(categories)],
            "image_key": None if index == count - 1 else f"products/{index}.png",
            "price": str(2 + index),
            "old_price": str(4 + index),
            "badge": "DEAL" if index % 2 == 0 else None,
            "sort_order": index,
        }
        for index in range(count)
    ]


def test_scoring_formula_is_transparent_and_missing_data_is_penalized() -> None:
    strong = score_product({"image_key": "x.png", "price": "5", "old_price": "10", "badge": "50%"})
    missing = score_product({})
    assert strong["factors"] == {
        "image": 20,
        "price": 5,
        "discount_percentage": 33,
        "absolute_saving": 5,
        "badge": 5,
        "manual_hero": 0,
    }
    assert missing["score"] == -25
    assert strong["score"] > missing["score"]


@pytest.mark.parametrize(
    ("count", "roles"),
    [
        (4, {"hero": 1, "featured": 1, "standard": 1, "support": 1}),
        (9, {"hero": 1, "featured": 3, "standard": 3, "support": 2}),
        (16, {"hero": 1, "featured": 4, "standard": 7, "support": 4}),
    ],
)
def test_canonical_plan_role_counts_and_renderer_treatments(
    count: int, roles: dict[str, int]
) -> None:
    plan = create_composition_plan(_items(count), campaign_key="campaign-24")
    assert {
        role: sum(product["role"] == role for product in plan["products"]) for role in roles
    } == roles
    hero = next(product for product in plan["products"] if product["role"] == "hero")
    assert hero["price_treatment"] == "promo-panel"
    assert hero["image_treatment"] == "hero"
    assert plan["products"][-1]["role"] == "support"


def test_manual_hero_wins_and_missing_image_is_not_hero_when_alternatives_exist() -> None:
    items = _items(4)
    items[-1]["is_hero"] = True
    plan = create_composition_plan(items, campaign_key="manual")
    assert plan["products"][0]["product_id"] == items[-1]["id"]
    items[-1]["is_hero"] = False
    plan = create_composition_plan(items, campaign_key="automatic")
    assert plan["products"][0]["product_id"] != items[-1]["id"]


def test_category_diversity_separates_featured_products_when_possible() -> None:
    items = _items(9)
    for index, item in enumerate(items):
        item["category"] = "repeated" if index < 6 else f"distinct-{index}"
        item["old_price"] = "20"
        item["price"] = str(2 + index)
    plan = create_composition_plan(items, campaign_key="diverse")
    prominent = [
        product["group_key"]
        for product in plan["products"]
        if product["role"] in {"hero", "featured"}
    ]
    assert len(set(prominent)) >= 3


def test_missing_categories_and_all_same_category_remain_stable() -> None:
    missing = _items(9)
    for item in missing:
        item.pop("category")
    same = _items(16)
    for item in same:
        item["category"] = "same"
    assert create_composition_plan(missing, campaign_key="missing") == create_composition_plan(
        deepcopy(missing), campaign_key="missing"
    )
    assert len(create_composition_plan(same, campaign_key="same")["products"]) == 16


def test_ties_and_strategy_selection_are_deterministic() -> None:
    items = _items(4)
    for item in items:
        item.update({"price": "5", "old_price": "10", "image_key": "same.png", "badge": None})
    first = create_composition_plan(items, campaign_key="stable-campaign")
    second = create_composition_plan(deepcopy(items), campaign_key="stable-campaign")
    assert first == second
    assert [product["product_id"] for product in first["products"]] == [
        item["id"] for item in items
    ]
    assert choose_composition_strategy("stable-campaign", items) == choose_composition_strategy(
        "stable-campaign", deepcopy(items)
    )


def test_no_discount_identical_prices_and_extreme_discount_do_not_crash() -> None:
    items = _items(9)
    for item in items:
        item["price"] = "999999.99"
        item.pop("old_price")
    items[3].update({"price": "0.01", "old_price": "999999.99"})
    plan = create_composition_plan(items, campaign_key="edge-prices")
    assert plan["products"][0]["product_id"] == items[3]["id"]
    assert plan["products"][0]["emphasis_score"] <= 90


def test_missing_image_never_becomes_automatic_hero_when_visual_candidates_exist() -> None:
    items = _items(4)
    items[-1].update({"price": "0.01", "old_price": "999999.99"})
    plan = create_composition_plan(items, campaign_key="missing-image")
    assert plan["products"][0]["product_id"] != items[-1]["id"]


def test_all_missing_images_still_produce_a_stable_fallback_hero() -> None:
    items = _items(4)
    for item in items:
        item["image_key"] = None
    assert create_composition_plan(items, campaign_key="fallback") == create_composition_plan(
        items, campaign_key="fallback"
    )
    assert create_composition_plan(items, campaign_key="fallback")["products"][0]["role"] == "hero"
