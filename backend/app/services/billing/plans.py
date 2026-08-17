"""Maps LeafletPilot's canonical, sellable plan codes to Stripe Price lookup keys.

Deliberately separate from ``app/services/plans.py`` (``PLAN_REGISTRY``), which
stays the single source of truth for pricing/limits/entitlements. This module
only adds the Stripe-side pointer for the plans that are actually sellable
through Checkout.
"""

from __future__ import annotations

from app.core.config import settings

SELLABLE_PLAN_CODES: tuple[str, ...] = ("starter", "standard", "pro")


def _lookup_keys() -> dict[str, str]:
    return {
        "starter": settings.stripe_price_lookup_key_starter,
        "standard": settings.stripe_price_lookup_key_standard,
        "pro": settings.stripe_price_lookup_key_pro,
    }


def resolve_stripe_lookup_key(plan_code: str) -> str:
    lookup_keys = _lookup_keys()
    if plan_code not in lookup_keys:
        raise ValueError(f"Plan '{plan_code}' is not sellable through Stripe Checkout.")
    return lookup_keys[plan_code]


def plan_code_for_lookup_key(lookup_key: str | None) -> str | None:
    if not lookup_key:
        return None
    for plan_code, mapped_key in _lookup_keys().items():
        if mapped_key == lookup_key:
            return plan_code
    return None


def is_sellable_plan_code(plan_code: str) -> bool:
    return plan_code in SELLABLE_PLAN_CODES
