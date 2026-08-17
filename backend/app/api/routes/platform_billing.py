"""Platform-admin visibility into the Stripe Price ↔ LeafletPilot plan mapping.

Read-only: PLAN_REGISTRY stays code-defined (see plans.py); this route only
reports whether each sellable plan's configured Stripe Price lookup key
resolves to a single, active, correctly-priced Stripe Price.
"""

from __future__ import annotations

import re
from datetime import timedelta
from uuid import UUID

import stripe
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_catalog_session, get_current_platform_admin
from app.core.config import settings
from app.models import Market, PlatformAdmin
from app.models.base import utc_now
from app.models.billing import MARKET_SUBSCRIPTION_STATUSES, STRIPE_WEBHOOK_EVENT_STATUSES, MarketSubscription, StripeWebhookEvent
from app.models.market import MARKET_SUBSCRIPTION_PLAN_CODES
from app.services.billing.plans import SELLABLE_PLAN_CODES, resolve_stripe_lookup_key
from app.services.billing.service import _environment_tag, _field, _portal_readiness_status
from app.services.plans import get_plan

router = APIRouter(prefix="/platform/billing", tags=["platform-billing"])

# Redacts anything shaped like a Stripe secret/restricted/webhook key before an
# error string (already app-generated, but defense in depth) is ever returned
# to the Platform Admin UI — see PART K in the hardening task.
_STRIPE_SECRET_PATTERN = re.compile(r"(sk_(?:test|live)_|rk_(?:test|live)_|whsec_)[A-Za-z0-9]+")

# A "received" webhook row older than this has neither progressed to a
# terminal status nor been retried by Stripe — worth flagging as stuck.
_STUCK_RECEIVED_AFTER = timedelta(minutes=30)


def _sanitize_error(text: str | None, *, limit: int = 300) -> str | None:
    if not text:
        return None
    redacted = _STRIPE_SECRET_PATTERN.sub(lambda m: f"{m.group(1)}[redacted]", text)
    return redacted[:limit]


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


async def _webhook_counts(session: AsyncSession) -> dict:
    rows = (await session.execute(select(StripeWebhookEvent.status, func.count()).group_by(StripeWebhookEvent.status))).all()
    counts = {status: 0 for status in STRIPE_WEBHOOK_EVENT_STATUSES}
    for status, count in rows:
        counts[status] = count

    last_processed_at = await session.scalar(
        select(func.max(StripeWebhookEvent.processed_at)).where(StripeWebhookEvent.status == "processed")
    )
    latest_failure = await session.scalar(
        select(StripeWebhookEvent).where(StripeWebhookEvent.status == "failed").order_by(StripeWebhookEvent.created_at.desc()).limit(1)
    )
    stuck_received = await session.scalar(
        select(func.count())
        .select_from(StripeWebhookEvent)
        .where(StripeWebhookEvent.status == "received", StripeWebhookEvent.created_at < utc_now() - _STUCK_RECEIVED_AFTER)
    )
    failed_invoice_count = await session.scalar(
        select(func.count())
        .select_from(StripeWebhookEvent)
        .where(StripeWebhookEvent.status == "failed", StripeWebhookEvent.event_type.like("invoice.%"))
    )
    return {
        "by_status": counts,
        "last_processed_at": last_processed_at,
        "stuck_received_count": stuck_received or 0,
        "failed_invoice_count": failed_invoice_count or 0,
        "latest_failure_at": latest_failure.created_at if latest_failure else None,
        "latest_failure_event_type": latest_failure.event_type if latest_failure else None,
        "latest_failure_error": _sanitize_error(latest_failure.error) if latest_failure else None,
    }


async def _subscription_counts(session: AsyncSession) -> dict:
    rows = (await session.execute(select(MarketSubscription.status, func.count()).group_by(MarketSubscription.status))).all()
    counts = {status: 0 for status in MARKET_SUBSCRIPTION_STATUSES}
    for status, count in rows:
        counts[status] = count
    pending_change_count = await session.scalar(
        select(func.count()).select_from(MarketSubscription).where(MarketSubscription.pending_change_reason.is_not(None))
    )
    return {"by_status": counts, "pending_change_count": pending_change_count or 0}


async def _plan_distribution(session: AsyncSession) -> dict:
    rows = (await session.execute(select(Market.subscription_plan, func.count()).group_by(Market.subscription_plan))).all()
    distribution = {code: 0 for code in MARKET_SUBSCRIPTION_PLAN_CODES}
    for code, count in rows:
        distribution[code] = distribution.get(code, 0) + count
    return distribution


async def _attention_markets(session: AsyncSession, *, limit: int = 20) -> list[dict]:
    """Local-only signals a market may need Platform Admin attention — no
    per-market Stripe API calls (see PART F: "do not make expensive Stripe
    API calls for every market on page load")."""
    attention: dict[UUID, dict] = {}

    sync_error_rows = (
        await session.execute(
            select(Market.id, Market.name, Market.subscription_plan, MarketSubscription.status, MarketSubscription.sync_error)
            .join(MarketSubscription, MarketSubscription.market_id == Market.id)
            .where(MarketSubscription.sync_error.is_not(None))
        )
    ).all()
    for market_id, name, plan_code, status, sync_error in sync_error_rows:
        attention[market_id] = {
            "market_id": str(market_id),
            "market_name": name,
            "plan_code": plan_code,
            "status": status,
            "issue": _sanitize_error(sync_error) or "Senkronizasyon hatası",
        }

    if len(attention) < limit:
        failed_webhook_rows = (
            await session.execute(
                select(StripeWebhookEvent.market_id, StripeWebhookEvent.event_type, StripeWebhookEvent.error)
                .where(StripeWebhookEvent.status == "failed", StripeWebhookEvent.market_id.is_not(None))
                .order_by(StripeWebhookEvent.created_at.desc())
            )
        ).all()
        for market_id, event_type, error in failed_webhook_rows:
            if market_id in attention or len(attention) >= limit:
                continue
            market = await session.get(Market, market_id)
            if market is None:
                continue
            attention[market_id] = {
                "market_id": str(market_id),
                "market_name": market.name,
                "plan_code": market.subscription_plan,
                "status": None,
                "issue": f"{event_type}: {_sanitize_error(error) or 'webhook işleme hatası'}",
            }

    return list(attention.values())[:limit]


async def _recent_failures(session: AsyncSession, *, limit: int = 10) -> list[dict]:
    rows = (
        await session.execute(
            select(StripeWebhookEvent).where(StripeWebhookEvent.status == "failed").order_by(StripeWebhookEvent.created_at.desc()).limit(limit)
        )
    ).scalars().all()
    market_ids = {row.market_id for row in rows if row.market_id}
    names_by_id: dict[UUID, str] = {}
    if market_ids:
        market_rows = (await session.execute(select(Market.id, Market.name).where(Market.id.in_(market_ids)))).all()
        names_by_id = dict(market_rows)
    return [
        {
            "occurred_at": row.created_at,
            "event_type": row.event_type,
            "market_id": str(row.market_id) if row.market_id else None,
            "market_name": names_by_id.get(row.market_id),
            "status": row.status,
            "error": _sanitize_error(row.error),
        }
        for row in rows
    ]


@router.get("/health")
async def billing_health(
    _: PlatformAdmin = Depends(get_current_platform_admin),
    session: AsyncSession = Depends(get_catalog_session),
) -> dict:
    """Compact operational status for Platform Admin — never returns Stripe
    secret/webhook keys, only derived counts and sanitized error summaries.
    See PART F/G of the billing-hardening task for the full field contract.
    """
    environment = _environment_tag() if settings.stripe_enabled else "not_configured"
    webhook_counts, subscription_counts, plan_distribution, attention_markets, recent_failures = (
        await _webhook_counts(session),
        await _subscription_counts(session),
        await _plan_distribution(session),
        await _attention_markets(session),
        await _recent_failures(session),
    )
    return {
        "environment": environment,
        "stripe_enabled": settings.stripe_enabled,
        "automatic_tax_enabled": settings.stripe_automatic_tax_enabled,
        "managed_payments_disabled": True,
        "portal_status": _portal_readiness_status(),
        "webhook_counts": webhook_counts,
        "subscription_counts": subscription_counts,
        "plan_distribution": plan_distribution,
        "attention_markets": attention_markets,
        "recent_failures": recent_failures,
    }
