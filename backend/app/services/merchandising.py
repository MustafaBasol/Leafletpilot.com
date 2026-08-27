"""Deterministic retail merchandising decisions for the shared flyer renderer.

The planner deliberately returns data, never HTML. Scores are integer points:

* usable image: +20 (missing image: -15)
* valid current price: +5 (missing price: -10)
* discount percentage: 0..40 (linear up to a 60% discount)
* absolute saving: 0..20 (one point per currency unit)
* supplied promotion badge: +5
* explicit campaign hero: +1000 (manual intent always wins)

Category and brand diversity are applied as transparent selection penalties, not
hidden score mutations: -18 for an already represented category and -8 for an
already represented brand. Stable sort order, original input position and id are
the final tie-breakers.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict, deque
from decimal import Decimal, InvalidOperation
from typing import Any

ROLE_COUNTS = {
    4: (1, 1, 1, 1),
    9: (1, 3, 3, 2),
    16: (1, 4, 7, 4),
}

STRATEGIES = {
    4: ("hero-left", "hero-right"),
    9: ("hero-top-left", "hero-top-right"),
    16: ("hero-corner-left", "hero-corner-right"),
}


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value)) if value not in (None, "") else None
    except (InvalidOperation, ValueError):
        return None


def _identity(item: dict[str, Any], index: int) -> tuple[int, int, str]:
    try:
        order = int(item.get("sort_order", index))
    except (TypeError, ValueError):
        order = index
    return order, index, str(item.get("id") or f"item-{index:04d}")


def score_product(item: dict[str, Any], index: int = 0) -> dict[str, Any]:
    """Return the auditable commercial score and its component breakdown."""
    current = _decimal(item.get("price") or item.get("promo_price"))
    original = _decimal(item.get("old_price"))
    saving = (
        original - current
        if current is not None and original is not None and original > current
        else Decimal(0)
    )
    discount = (saving / original * 100) if saving and original and original > 0 else Decimal(0)
    factors = {
        "image": 20 if item.get("image_key") else -15,
        "price": 5 if current is not None and current >= 0 else -10,
        "discount_percentage": min(40, max(0, int(discount * Decimal(2) / Decimal(3)))),
        "absolute_saving": min(20, max(0, int(saving))),
        "badge": 5 if item.get("badge") else 0,
        "manual_hero": 1000 if item.get("is_hero") else 0,
    }
    return {
        "item": item,
        "score": sum(factors.values()),
        "factors": factors,
        "discount_percentage": str(discount.quantize(Decimal("0.01"))),
        "absolute_saving": str(saving.quantize(Decimal("0.01"))),
        "identity": _identity(item, index),
    }


def score_products(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [score_product(item, index) for index, item in enumerate(items)]


def _metadata(value: Any) -> str | None:
    text = str(value or "").strip().casefold()
    return text or None


def _diverse_rank(scored: list[dict[str, Any]]) -> list[dict[str, Any]]:
    remaining = list(scored)
    selected: list[dict[str, Any]] = []
    category_counts: defaultdict[str, int] = defaultdict(int)
    brand_counts: defaultdict[str, int] = defaultdict(int)
    while remaining:

        def selection_key(entry: dict[str, Any]) -> tuple[int, int, int, str]:
            item = entry["item"]
            category = _metadata(item.get("category"))
            brand = _metadata(item.get("brand"))
            penalty = (18 * category_counts[category] if category else 0) + (
                8 * brand_counts[brand] if brand else 0
            )
            order, index, stable_id = entry["identity"]
            return (-(entry["score"] - penalty), order, index, stable_id)

        winner = min(remaining, key=selection_key)
        remaining.remove(winner)
        selected.append(winner)
        category = _metadata(winner["item"].get("category"))
        brand = _metadata(winner["item"].get("brand"))
        if category:
            category_counts[category] += 1
        if brand:
            brand_counts[brand] += 1
    return selected


def classify_products(scored: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rank with diversity and assign restrained role counts for 4/9/16."""
    count = len(scored)
    ranked = _diverse_rank(scored)
    explicit_hero = next((entry for entry in ranked if entry["item"].get("is_hero")), None)
    visual_hero = next((entry for entry in ranked if entry["item"].get("image_key")), None)
    hero_candidate = explicit_hero or visual_hero
    if hero_candidate is not None and ranked[0] is not hero_candidate:
        ranked.remove(hero_candidate)
        ranked.insert(0, hero_candidate)

    if count in ROLE_COUNTS:
        role_counts = ROLE_COUNTS[count]
    else:
        hero = 1 if count else 0
        featured = min(max(count // 4, 0), 4)
        support = min(count // 4, max(0, count - hero - featured))
        role_counts = (hero, featured, count - hero - featured - support, support)
    roles = (
        ["hero"] * role_counts[0]
        + ["featured"] * role_counts[1]
        + ["standard"] * role_counts[2]
        + ["support"] * role_counts[3]
    )
    return [{**entry, "role": roles[index]} for index, entry in enumerate(ranked)]


def group_products(classified: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Interleave category groups while keeping the hero first and roles stable."""
    result: list[dict[str, Any]] = []
    for role in ("hero", "featured", "standard", "support"):
        entries = [entry for entry in classified if entry["role"] == role]
        groups: dict[str, deque[dict[str, Any]]] = {}
        order: list[str] = []
        for index, entry in enumerate(entries):
            key = _metadata(entry["item"].get("category")) or f"__missing_{index}"
            if key not in groups:
                groups[key] = deque()
                order.append(key)
            groups[key].append(entry)
        while any(groups[key] for key in order):
            for key in order:
                if groups[key]:
                    result.append(
                        {
                            **groups[key].popleft(),
                            "group_key": None if key.startswith("__missing_") else key,
                        }
                    )
    return result


def choose_composition_strategy(campaign_key: str, items: list[dict[str, Any]]) -> str:
    choices = STRATEGIES.get(len(items), ("balanced-grid",))
    material = "|".join(
        [
            str(campaign_key or "campaign"),
            *(str(item.get("id") or index) for index, item in enumerate(items)),
        ]
    )
    return choices[int(hashlib.sha256(material.encode("utf-8")).hexdigest()[:8], 16) % len(choices)]


def _treatments(role: str, index: int) -> tuple[str, str]:
    if role == "hero":
        return "promo-panel", "hero"
    if role == "featured":
        return (("compact-ticket", "surface-accent")[index % 2], ("large", "medium")[index % 2])
    if role == "standard":
        return (("surface-accent", "title-strip")[index % 2], ("medium", "small")[index % 2])
    return (("compact-ticket", "title-strip")[index % 2], "compact")


def create_composition_plan(
    items: list[dict[str, Any]], *, campaign_key: str = ""
) -> dict[str, Any]:
    """Assign visual merchandising treatments without changing item position.

    Callers pass the authoritative CampaignItem.sort_order sequence. Ranking
    still chooses roles and treatments, but its result is mapped back to that
    supplied sequence so a hero or high-scoring product never becomes an
    implicit move command.
    """
    classified = group_products(classify_products(score_products(items)))
    by_identity = {entry["identity"]: entry for entry in classified}
    products = []
    for index, item in enumerate(items):
        identity = _identity(item, index)
        entry = by_identity[identity]
        price_treatment, image_treatment = _treatments(entry["role"], index)
        products.append(
            {
                "product_id": str(item.get("id") or identity[2]),
                "role": entry["role"],
                "emphasis_score": entry["score"],
                "score_factors": entry["factors"],
                "discount_percentage": entry["discount_percentage"],
                "absolute_saving": entry["absolute_saving"],
                "price_treatment": price_treatment,
                "image_treatment": image_treatment,
                "group_key": entry["group_key"],
                "position_hint": index,
                "item": item,
            }
        )
    return {
        "strategy": choose_composition_strategy(campaign_key, items),
        "products": products,
    }
