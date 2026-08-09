"""Offline, deterministic campaign intelligence for retail composition planning."""

from __future__ import annotations

from collections import Counter
from decimal import Decimal, InvalidOperation
from typing import Any

ENGINE_VERSION = "campaign-intelligence-v1"


def _decimal(value: Any) -> Decimal | None:
    try:
        number = Decimal(str(value)) if value not in (None, "") else None
    except (InvalidOperation, TypeError, ValueError):
        return None
    return number if number is not None and number.is_finite() and number > 0 else None


def calculate_promotion(item: dict[str, Any]) -> dict[str, Any]:
    """Return safe promotion facts; invalid or unsupported offers are never inferred."""
    current = _decimal(item.get("price") or item.get("promo_price"))
    original = _decimal(item.get("old_price"))
    warning = None
    if current is None or original is None:
        if item.get("price") not in (None, "") or item.get("old_price") not in (None, ""):
            warning = "invalid or incomplete price data"
        return {
            "currentPrice": str(current) if current is not None else None,
            "originalPrice": str(original) if original is not None else None,
            "discountPercent": None,
            "absoluteSaving": None,
            "promotionStrength": 0.0,
            "recommendedBadge": "special" if item.get("badge") else None,
            "warning": warning,
        }
    if current >= original:
        if current > original:
            warning = "sale price is above original price"
        return {
            "currentPrice": str(current),
            "originalPrice": str(original),
            "discountPercent": Decimal("0.0"),
            "absoluteSaving": Decimal("0.00"),
            "promotionStrength": 0.0,
            "recommendedBadge": "special" if item.get("badge") else None,
            "warning": warning,
        }
    saving = original - current
    percent = (saving / original * 100).quantize(Decimal("0.1"))
    strength = round(min(1.0, float(percent) / 50.0), 2)
    badge = "save_percent" if percent >= 10 else "save_amount"
    return {
        "currentPrice": str(current),
        "originalPrice": str(original),
        "discountPercent": percent,
        "absoluteSaving": saving.quantize(Decimal("0.01")),
        "promotionStrength": strength,
        "recommendedBadge": badge,
        "warning": None,
    }


def _group_key(item: dict[str, Any], promotion: dict[str, Any]) -> str:
    category = str(item.get("category") or "").strip()
    if category:
        return category
    if promotion["promotionStrength"] >= 0.4:
        return "value"
    return "other_offers"


def _score(item: dict[str, Any], promotion: dict[str, Any]) -> tuple[int, list[str]]:
    reasons: list[str] = []
    score = 0
    percent = promotion["discountPercent"]
    if percent and percent > 0:
        promo_points = min(45, round(float(percent) * 0.9))
        score += promo_points
        reasons.append(f"{percent}% discount")
    saving = promotion["absoluteSaving"]
    if saving and saving > 0:
        score += min(15, int(saving))
        reasons.append(f"{saving} absolute saving")
    if item.get("image_key"):
        score += 20
        reasons.append("usable product image")
    else:
        reasons.append("product image missing")
    name = str(item.get("name") or item.get("resolved_name") or "").strip()
    if name and len(name) <= 60:
        score += 10
        reasons.append("readable product name")
    elif name:
        score += 4
        reasons.append("long product name")
    else:
        reasons.append("product name missing")
    if promotion["currentPrice"] is not None:
        score += 10
        reasons.append("valid current price")
    if item.get("badge"):
        score += 5
        reasons.append("existing campaign badge retained")
    if item.get("is_hero"):
        score = 100
        reasons.insert(0, "manual hero selection")
    return min(100, score), reasons


def _strategy(products: list[dict[str, Any]]) -> dict[str, str]:
    count = len(products)
    image_ratio = sum(bool(product["_item"].get("image_key")) for product in products) / count if count else 0
    category_count = len({product["groupKey"] for product in products})
    discount_count = sum(bool(product["discountPercent"] and product["discountPercent"] > 0) for product in products)
    if count >= 10:
        composition, density = "dense_value_grid", "dense"
    elif count and products[0]["priorityScore"] >= 55 and image_ratio >= 0.5:
        composition, density = "hero_plus_grid", "balanced"
    else:
        composition, density = "balanced_grid", "balanced" if count <= 9 else "dense"
    if image_ratio < 0.4:
        campaign_type, objective = "price_led", "maximize_value_perception"
    elif discount_count >= max(1, count // 2):
        campaign_type, objective = "discount_led", "maximize_value_perception"
    else:
        campaign_type, objective = "image_led", "balance_product_discovery"
    return {
        "campaignType": campaign_type,
        "density": density,
        "composition": composition,
        "primaryObjective": objective,
        "categoryMode": "mixed" if category_count > 1 else "single",
    }


class DeterministicPlanner:
    """Build a typed-compatible, reproducible recommendation plan from render data."""

    engine_version = ENGINE_VERSION

    def analyze(self, campaign_id: str, items: list[dict[str, Any]]) -> dict[str, Any]:
        warnings: list[str] = []
        candidates: list[dict[str, Any]] = []
        for index, item in enumerate(items):
            promotion = calculate_promotion(item)
            score, reasons = _score(item, promotion)
            if promotion["warning"]:
                warnings.append(f"{item.get('id') or index}: {promotion['warning']}")
            candidates.append(
                {
                    "productId": str(item.get("id") or f"item-{index}"),
                    "role": "standard",
                    "priorityScore": score,
                    "promotionStrength": promotion["promotionStrength"],
                    "discountPercent": promotion["discountPercent"],
                    "absoluteSaving": promotion["absoluteSaving"],
                    "recommendedSize": "md",
                    "recommendedBadge": promotion["recommendedBadge"],
                    "groupKey": _group_key(item, promotion),
                    "reasons": reasons,
                    "sourceOrder": index,
                    "manualHero": bool(item.get("is_hero")),
                    "_item": item,
                }
            )

        candidates.sort(
            key=lambda product: (
                not product["manualHero"],
                -product["priorityScore"],
                product["sourceOrder"],
                product["productId"],
            )
        )
        if candidates:
            top = candidates[0]
            viable = next((p for p in candidates if p["_item"].get("image_key")), None)
            manual = next((p for p in candidates if p["manualHero"]), None)
            visual_is_competitive = viable is not None and viable["priorityScore"] >= top["priorityScore"] - 15
            hero = manual or (viable if visual_is_competitive else top)
            candidates.remove(hero)
            candidates.insert(0, hero)
            hero["role"] = "hero"
            hero["recommendedSize"] = "xl"
            hero["reasons"].append("best viable hero candidate" if not manual else "manual choice overrides recommendations")
        featured_limit = min(3, max(0, len(candidates) // 4))
        for product in candidates[1 : 1 + featured_limit]:
            product["role"] = "featured"
            product["recommendedSize"] = "lg"
        strategy = _strategy(candidates)
        groups = []
        for key, count in Counter(product["groupKey"] for product in candidates).items():
            groups.append({"key": key, "productCount": count, "reason": "source category" if key not in {"value", "other_offers"} else "safe fallback grouping"})
        if not candidates:
            warnings.append("Campaign has no products to analyze.")
        elif sum(bool(p["_item"].get("image_key")) for p in candidates) == 0:
            warnings.append("No usable product images; price-led composition recommended.")
        products = [{key: value for key, value in product.items() if key != "_item"} for product in candidates]
        return {
            "campaignId": str(campaign_id),
            "engineVersion": self.engine_version,
            "strategy": strategy,
            "products": products,
            "groups": groups,
            "messages": ["Recommendations are deterministic and use only campaign data."],
            "warnings": warnings,
        }


class CampaignIntelligenceEngine:
    """Stable facade that can host a future opt-in enhancer without provider coupling."""

    def __init__(self, planner: DeterministicPlanner | None = None) -> None:
        self.planner = planner or DeterministicPlanner()

    def analyze(self, campaign_id: str, items: list[dict[str, Any]]) -> dict[str, Any]:
        return self.planner.analyze(campaign_id, items)
