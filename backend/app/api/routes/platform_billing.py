"""Platform-admin visibility into the Stripe Price ↔ LeafletPilot plan mapping.

Read-only: PLAN_REGISTRY stays code-defined (see plans.py); this route only
reports whether each sellable plan's configured Stripe Price lookup key
resolves to a single, active, correctly-priced Stripe Price.
"""

from __future__ import annotations

import stripe
from fastapi import APIRouter, Depends

from app.api.deps import get_current_platform_admin
from app.core.config import settings
from app.models import PlatformAdmin
from app.services.billing.plans import SELLABLE_PLAN_CODES, resolve_stripe_lookup_key
from app.services.billing.service import _field
from app.services.plans import get_plan

router = APIRouter(prefix="/platform/billing", tags=["platform-billing"])


@router.get("/plans")
async def plan_mapping_health(_: PlatformAdmin = Depends(get_current_platform_admin)) -> dict:
    if not settings.stripe_enabled:
        return {
            "stripe_enabled": False,
            "plans": [
                {
                    "plan_code": plan_code,
                    "lookup_key": resolve_stripe_lookup_key(plan_code),
                    "health": "stripe_disabled",
                }
                for plan_code in SELLABLE_PLAN_CODES
            ],
        }

    stripe.api_key = settings.stripe_secret_key
    plans = []
    for plan_code in SELLABLE_PLAN_CODES:
        plan_definition = get_plan(plan_code)
        lookup_key = resolve_stripe_lookup_key(plan_code)
        try:
            result = await stripe.Price.list_async(lookup_keys=[lookup_key], limit=10)
        except stripe.error.StripeError as exc:
            plans.append(
                {
                    "plan_code": plan_code,
                    "lookup_key": lookup_key,
                    "health": "stripe_error",
                    "detail": str(exc)[:300],
                }
            )
            continue

        active_prices = [price for price in result.data if _field(price, "active")]
        health = "ok"
        detail = None
        price = active_prices[0] if active_prices else None
        if not result.data:
            health = "missing"
            detail = f"No Stripe Price found for lookup key '{lookup_key}'."
        elif not active_prices:
            health = "inactive"
            detail = f"Stripe Price for '{lookup_key}' exists but is not active."
        elif len(active_prices) > 1:
            health = "duplicate"
            detail = f"{len(active_prices)} active Stripe Prices share lookup key '{lookup_key}'."
        elif (_field(price, "currency", "") or "").upper() != plan_definition.currency.upper():
            health = "currency_mismatch"
            detail = f"Stripe Price currency {_field(price, 'currency')} != {plan_definition.currency}."
        elif plan_definition.monthly_price is not None and _field(price, "unit_amount") != round(plan_definition.monthly_price * 100):
            health = "amount_mismatch"
            detail = f"Stripe Price amount {_field(price, 'unit_amount')} != {round(plan_definition.monthly_price * 100)}."

        plans.append(
            {
                "plan_code": plan_code,
                "lookup_key": lookup_key,
                "health": health,
                "detail": detail,
                "stripe_price_id": _field(price, "id") if price else None,
                "unit_amount": _field(price, "unit_amount") if price else None,
                "currency": _field(price, "currency") if price else None,
            }
        )
    return {"stripe_enabled": True, "plans": plans}
