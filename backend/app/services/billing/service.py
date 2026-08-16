"""Stripe-facing billing service.

Every ``stripe.*`` call in the backend lives in this package (mirrors how
``app/integrations/telegram/client.py`` centralizes Telegram API calls).

Core rule (see the implementation plan): mutation functions here
(``create_checkout_session``, ``change_plan``, ``cancel_subscription``,
``resume_subscription``, ``create_portal_session``) only call Stripe and
return its response — they never write ``MarketSubscription`` or
``Market.subscription_plan``. The only functions that write that state are
``sync_subscription_from_stripe_object`` / ``apply_invoice_event`` /
``apply_checkout_completed``, which are called exclusively from webhook
processing (``webhook.py``) and the Platform Admin resync route.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import stripe
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Market
from app.models.base import utc_now
from app.models.billing import MarketSubscription
from app.services.billing.errors import BillingError, PermanentSyncError
from app.services.billing.plans import (
    is_sellable_plan_code,
    plan_code_for_lookup_key,
    resolve_stripe_lookup_key,
)
from app.services.plans import plan_rank

FULL_ENTITLEMENT_STATUSES = {"active", "trialing"}
DOWNGRADE_TO_UNASSIGNED_STATUSES = {"unpaid", "canceled", "incomplete_expired"}

_PORTAL_CONFIGURATION_CACHE: str | None = None
_PRICE_CACHE: dict[str, "stripe.Price"] = {}


def _require_enabled() -> None:
    if not settings.stripe_enabled:
        raise BillingError("Stripe billing is not enabled.", status_code=503)
    stripe.api_key = settings.stripe_secret_key


def _environment_tag() -> str:
    key = settings.stripe_secret_key.strip()
    return "live" if key.startswith(("sk_live_", "rk_live_")) else "sandbox"


def _as_id(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return value.get("id")
    return value


def _to_datetime(value) -> datetime | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value, tz=UTC)


async def _resolve_price(plan_code: str) -> "stripe.Price":
    if plan_code in _PRICE_CACHE:
        return _PRICE_CACHE[plan_code]
    lookup_key = resolve_stripe_lookup_key(plan_code)
    result = await stripe.Price.list_async(lookup_keys=[lookup_key], active=True, limit=1)
    if not result.data:
        raise BillingError(f"No active Stripe Price found for lookup key '{lookup_key}'.", status_code=503)
    price = result.data[0]
    _PRICE_CACHE[plan_code] = price
    return price


def _plan_code_for_price(price: dict) -> str | None:
    plan_code = plan_code_for_lookup_key(price.get("lookup_key"))
    if plan_code:
        return plan_code
    # Defensive fallback for a price without a lookup_key attached: match by id
    # against whichever price we've already resolved for each plan this run.
    for code, cached_price in _PRICE_CACHE.items():
        if cached_price.id == price.get("id"):
            return code
    return None


async def _get_subscription_row(session: AsyncSession, market_id: UUID) -> MarketSubscription | None:
    return await session.scalar(select(MarketSubscription).where(MarketSubscription.market_id == market_id))


async def _require_subscription_row(session: AsyncSession, market_id: UUID) -> MarketSubscription:
    row = await _get_subscription_row(session, market_id)
    if row is None or not row.stripe_subscription_id:
        raise BillingError("Bu market için aktif bir Stripe aboneliği bulunamadı.", status_code=404)
    return row


# ---------------------------------------------------------------------------
# Mutation endpoints — Stripe calls only, no local writes (core rule).
# ---------------------------------------------------------------------------


async def create_checkout_session(session: AsyncSession, market: Market, plan_code: str) -> dict:
    _require_enabled()
    if not is_sellable_plan_code(plan_code):
        raise BillingError("Geçersiz plan. Yalnızca starter, standard veya pro seçilebilir.")
    price = await _resolve_price(plan_code)
    existing = await _get_subscription_row(session, market.id)

    checkout_kwargs: dict = {
        "mode": "subscription",
        "line_items": [{"price": price.id, "quantity": 1}],
        "success_url": settings.stripe_checkout_success_url_resolved,
        "cancel_url": settings.stripe_checkout_cancel_url_resolved,
        "client_reference_id": str(market.id),
        "metadata": {"application": "leafletpilot", "market_id": str(market.id), "plan_code": plan_code},
        "subscription_data": {
            "metadata": {
                "application": "leafletpilot",
                "market_id": str(market.id),
                "plan_code": plan_code,
                "environment": _environment_tag(),
            },
        },
    }
    if existing and existing.stripe_customer_id:
        checkout_kwargs["customer"] = existing.stripe_customer_id
    else:
        checkout_kwargs["customer_creation"] = "always"
        if market.contact_email:
            checkout_kwargs["customer_email"] = market.contact_email

    checkout_session = await stripe.checkout.Session.create_async(**checkout_kwargs)
    return {"checkout_url": checkout_session.url, "checkout_session_id": checkout_session.id}


async def _get_or_create_portal_configuration() -> str:
    global _PORTAL_CONFIGURATION_CACHE
    if _PORTAL_CONFIGURATION_CACHE:
        return _PORTAL_CONFIGURATION_CACHE
    existing = await stripe.billing_portal.Configuration.list_async(limit=100)
    for configuration in existing.data:
        if (configuration.get("metadata") or {}).get("application") == "leafletpilot":
            _PORTAL_CONFIGURATION_CACHE = configuration.id
            return configuration.id
    created = await stripe.billing_portal.Configuration.create_async(
        metadata={"application": "leafletpilot"},
        features={
            "payment_method_update": {"enabled": True},
            "invoice_history": {"enabled": True},
            "customer_update": {"enabled": True, "allowed_updates": ["address", "phone"]},
            "subscription_update": {"enabled": False},
            "subscription_cancel": {"enabled": False},
        },
    )
    _PORTAL_CONFIGURATION_CACHE = created.id
    return created.id


async def create_portal_session(session: AsyncSession, market: Market) -> dict:
    _require_enabled()
    row = await _require_subscription_row(session, market.id)
    if not row.stripe_customer_id:
        raise BillingError("Bu market için Stripe müşteri kaydı bulunamadı.", status_code=404)
    configuration_id = await _get_or_create_portal_configuration()
    portal_session = await stripe.billing_portal.Session.create_async(
        customer=row.stripe_customer_id,
        return_url=settings.stripe_portal_return_url_resolved,
        configuration=configuration_id,
    )
    return {"portal_url": portal_session.url}


async def change_plan(session: AsyncSession, market: Market, plan_code: str) -> dict:
    _require_enabled()
    if not is_sellable_plan_code(plan_code):
        raise BillingError("Geçersiz plan. Yalnızca starter, standard veya pro seçilebilir.")
    row = await _require_subscription_row(session, market.id)
    if plan_code == row.plan_code:
        raise BillingError("Market zaten bu planda.", status_code=409)
    if row.cancel_at_period_end:
        raise BillingError(
            "İptal talebi beklerken plan değişikliği yapılamaz; önce aboneliği devam ettirin.",
            status_code=409,
        )

    stripe_subscription = await stripe.Subscription.retrieve_async(row.stripe_subscription_id)
    if stripe_subscription.get("schedule"):
        await stripe.SubscriptionSchedule.release_async(stripe_subscription["schedule"])
        stripe_subscription = await stripe.Subscription.retrieve_async(row.stripe_subscription_id)

    price = await _resolve_price(plan_code)
    item_id = stripe_subscription["items"]["data"][0]["id"]

    if plan_rank(plan_code) > plan_rank(row.plan_code):
        updated = await stripe.Subscription.modify_async(
            row.stripe_subscription_id,
            items=[{"id": item_id, "price": price.id}],
            proration_behavior="always_invoice",
            payment_behavior="pending_if_incomplete",
        )
        pending_update = updated.get("pending_update")
        if pending_update:
            return {
                "status": "pending_payment",
                "expires_at": _to_datetime(pending_update.get("expires_at")),
            }
        return {"status": "applied"}

    schedule = await stripe.SubscriptionSchedule.create_async(from_subscription=row.stripe_subscription_id)
    current_phase = schedule["phases"][0]
    await stripe.SubscriptionSchedule.modify_async(
        schedule.id,
        phases=[
            {
                "items": [
                    {"price": _as_id(item.get("price")), "quantity": item.get("quantity", 1)}
                    for item in current_phase["items"]
                ],
                "start_date": current_phase["start_date"],
                "end_date": current_phase["end_date"],
            },
            {"items": [{"price": price.id, "quantity": 1}]},
        ],
    )
    return {"status": "scheduled", "effective_at": _to_datetime(current_phase["end_date"])}


async def cancel_subscription(session: AsyncSession, market: Market) -> dict:
    _require_enabled()
    row = await _require_subscription_row(session, market.id)
    if row.stripe_schedule_id:
        await stripe.SubscriptionSchedule.release_async(row.stripe_schedule_id)
    await stripe.Subscription.modify_async(row.stripe_subscription_id, cancel_at_period_end=True)
    return {"status": "cancel_scheduled"}


async def resume_subscription(session: AsyncSession, market: Market) -> dict:
    _require_enabled()
    row = await _require_subscription_row(session, market.id)
    await stripe.Subscription.modify_async(row.stripe_subscription_id, cancel_at_period_end=False)
    return {"status": "resumed"}


async def list_invoices(session: AsyncSession, market: Market, *, limit: int = 20, starting_after: str | None = None) -> dict:
    _require_enabled()
    row = await _get_subscription_row(session, market.id)
    if row is None or not row.stripe_customer_id:
        return {"items": [], "has_more": False}
    kwargs: dict = {"customer": row.stripe_customer_id, "limit": limit}
    if starting_after:
        kwargs["starting_after"] = starting_after
    invoices = await stripe.Invoice.list_async(**kwargs)
    items = [_normalize_invoice(invoice) for invoice in invoices.data]
    return {"items": items, "has_more": invoices.has_more}


def _normalize_invoice(invoice: dict) -> dict:
    status = invoice.get("status")
    attempted = bool(invoice.get("attempted"))
    return {
        "invoice_id": invoice.get("id"),
        "number": invoice.get("number"),
        "created_at": _to_datetime(invoice.get("created")),
        "period_start": _to_datetime(invoice.get("period_start")),
        "period_end": _to_datetime(invoice.get("period_end")),
        "subtotal": invoice.get("subtotal"),
        "total": invoice.get("total"),
        "amount_paid": invoice.get("amount_paid"),
        "amount_due": invoice.get("amount_due"),
        "currency": invoice.get("currency"),
        "status": status,
        "payment_failed": status == "open" and attempted and not invoice.get("paid"),
        "paid_at": _to_datetime((invoice.get("status_transitions") or {}).get("paid_at")),
        "hosted_invoice_url": invoice.get("hosted_invoice_url"),
        "invoice_pdf": invoice.get("invoice_pdf"),
    }


# ---------------------------------------------------------------------------
# Authoritative state writers — webhook processing and Platform Admin resync
# only. See the core rule at the top of this module.
# ---------------------------------------------------------------------------


def _resolve_market_id_from_metadata(stripe_object: dict) -> UUID | None:
    metadata = stripe_object.get("metadata") or {}
    raw = metadata.get("market_id")
    if not raw:
        return None
    try:
        return UUID(raw)
    except ValueError:
        return None


def _apply_entitlement(market: Market, row: MarketSubscription) -> bool:
    """Applies the fallback policy for the current status bucket. Returns
    True if ``market.subscription_plan`` changed."""
    previous = market.subscription_plan
    if row.status in FULL_ENTITLEMENT_STATUSES:
        market.subscription_plan = row.plan_code
    elif row.status in DOWNGRADE_TO_UNASSIGNED_STATUSES:
        row.plan_code = "unassigned"
        market.subscription_plan = "unassigned"
    # Grace statuses (past_due, incomplete, paused): leave the plan as-is.
    return market.subscription_plan != previous


async def _plan_code_for_price_id(price_id: str | None) -> str | None:
    if not price_id:
        return None
    for code, cached_price in _PRICE_CACHE.items():
        if cached_price.id == price_id:
            return code
    price = await stripe.Price.retrieve_async(price_id)
    return plan_code_for_lookup_key(price.get("lookup_key"))


async def _sync_pending_state(row: MarketSubscription, stripe_subscription: dict) -> None:
    pending_update = stripe_subscription.get("pending_update")
    if pending_update:
        pending_items = pending_update.get("subscription_items") or []
        pending_price = pending_items[0].get("price") if pending_items else None
        row.pending_plan_code = _plan_code_for_price(pending_price) if isinstance(pending_price, dict) else None
        row.pending_change_reason = "upgrade_pending_payment"
        row.pending_change_at = _to_datetime(pending_update.get("expires_at"))
        return

    schedule_id = _as_id(stripe_subscription.get("schedule"))
    if schedule_id:
        # A Subscription Schedule governs this subscription — our downgrade
        # mechanism (see change_plan). The subscription payload doesn't carry
        # the schedule's future phase, so fetch it to know which plan we're
        # heading to; the transition date is simply this subscription's
        # current period end (phase 1's end_date, set to match at creation).
        schedule = await stripe.SubscriptionSchedule.retrieve_async(schedule_id)
        phases = schedule.get("phases") or []
        target_plan_code = None
        if phases:
            last_phase_items = phases[-1].get("items") or []
            if last_phase_items:
                target_plan_code = await _plan_code_for_price_id(_as_id(last_phase_items[0].get("price")))
        row.pending_plan_code = target_plan_code
        row.pending_change_reason = "downgrade"
        row.pending_change_at = _to_datetime(stripe_subscription.get("current_period_end"))
        return

    row.pending_plan_code = None
    row.pending_change_reason = None
    row.pending_change_at = None


async def sync_subscription_from_stripe_object(
    session: AsyncSession,
    stripe_subscription: dict,
    *,
    event_created_at: datetime,
    market_id_hint: UUID | None = None,
) -> tuple[MarketSubscription, bool]:
    """Normalizes a Stripe Subscription object into ``MarketSubscription`` +
    ``Market.subscription_plan``. Returns ``(row, applied)`` — ``applied`` is
    False when the event was stale (out-of-order) and nothing was written.
    """
    market_id = market_id_hint or _resolve_market_id_from_metadata(stripe_subscription)
    if market_id is None:
        existing_by_sub = await session.scalar(
            select(MarketSubscription).where(
                MarketSubscription.stripe_subscription_id == stripe_subscription.get("id")
            )
        )
        market_id = existing_by_sub.market_id if existing_by_sub else None
    if market_id is None:
        raise PermanentSyncError("Could not resolve a LeafletPilot market for this Stripe subscription.")

    row = await _get_subscription_row(session, market_id)
    if row is None:
        row = MarketSubscription(market_id=market_id, plan_code="unassigned", status=stripe_subscription["status"])
        session.add(row)
        await session.flush()

    if row.last_stripe_event_at is not None and event_created_at <= row.last_stripe_event_at:
        return row, False

    items = stripe_subscription.get("items", {}).get("data") or []
    if not items:
        raise PermanentSyncError("Stripe subscription payload has no items.", market_id=market_id)
    price = items[0]["price"]
    plan_code = _plan_code_for_price(price)
    if plan_code is None:
        message = f"Unmapped Stripe price id={price.get('id')} lookup_key={price.get('lookup_key')}."
        raise PermanentSyncError(message, market_id=market_id)

    row.plan_code = plan_code
    row.status = stripe_subscription["status"]
    row.stripe_customer_id = _as_id(stripe_subscription.get("customer"))
    row.stripe_subscription_id = stripe_subscription.get("id")
    row.stripe_price_id = price.get("id")
    row.stripe_schedule_id = _as_id(stripe_subscription.get("schedule"))
    row.currency = price.get("currency")
    row.unit_amount = price.get("unit_amount")
    row.interval = (price.get("recurring") or {}).get("interval")
    row.current_period_start = _to_datetime(stripe_subscription.get("current_period_start"))
    row.current_period_end = _to_datetime(stripe_subscription.get("current_period_end"))
    if row.subscription_started_at is None:
        row.subscription_started_at = _to_datetime(stripe_subscription.get("start_date")) or utc_now()
    row.cancel_at_period_end = bool(stripe_subscription.get("cancel_at_period_end"))
    row.canceled_at = _to_datetime(stripe_subscription.get("canceled_at"))
    row.ended_at = _to_datetime(stripe_subscription.get("ended_at"))
    row.trial_start = _to_datetime(stripe_subscription.get("trial_start"))
    row.trial_end = _to_datetime(stripe_subscription.get("trial_end"))
    row.latest_invoice_id = _as_id(stripe_subscription.get("latest_invoice"))

    await _sync_pending_state(row, stripe_subscription)
    if row.pending_change_reason == "downgrade" and row.pending_plan_code == row.plan_code:
        # The schedule's final (open-ended) phase has taken effect — Stripe
        # doesn't detach the schedule for an open-ended last phase, so this
        # price-match is the actual signal the transition completed.
        row.pending_plan_code = None
        row.pending_change_reason = None
        row.pending_change_at = None

    market = await session.get(Market, market_id)
    if market is None:
        raise PermanentSyncError(
            f"Market {market_id} referenced by Stripe subscription no longer exists.", market_id=market_id
        )
    _apply_entitlement(market, row)

    row.last_stripe_event_at = event_created_at
    row.last_synced_at = utc_now()
    row.sync_error = None
    return row, True


async def apply_checkout_completed(
    session: AsyncSession,
    checkout_session_obj: dict,
    *,
    event_created_at: datetime,
) -> tuple[MarketSubscription, bool] | None:
    subscription_id = _as_id(checkout_session_obj.get("subscription"))
    if not subscription_id:
        return None
    market_id = _resolve_market_id_from_metadata(checkout_session_obj)
    stripe_subscription = await stripe.Subscription.retrieve_async(subscription_id)
    return await sync_subscription_from_stripe_object(
        session, stripe_subscription, event_created_at=event_created_at, market_id_hint=market_id
    )


async def apply_invoice_event(
    session: AsyncSession,
    invoice: dict,
    *,
    event_created_at: datetime,
    kind: str,
) -> tuple[MarketSubscription, bool]:
    subscription_id = _as_id(invoice.get("subscription"))
    if not subscription_id:
        raise PermanentSyncError("Invoice event has no associated subscription.")
    row = await session.scalar(
        select(MarketSubscription).where(MarketSubscription.stripe_subscription_id == subscription_id)
    )
    if row is None:
        raise PermanentSyncError(f"No local subscription found for Stripe subscription {subscription_id}.")
    if row.last_stripe_event_at is not None and event_created_at <= row.last_stripe_event_at:
        return row, False

    status_map = {"paid": "paid", "payment_failed": "payment_failed", "payment_action_required": "requires_action"}
    row.last_payment_status = status_map[kind]
    if kind == "paid":
        row.last_payment_at = _to_datetime((invoice.get("status_transitions") or {}).get("paid_at")) or utc_now()
    row.latest_invoice_id = invoice.get("id")
    row.last_stripe_event_at = event_created_at
    row.last_synced_at = utc_now()
    row.sync_error = None
    return row, True


async def resync_from_stripe(session: AsyncSession, market: Market) -> MarketSubscription:
    """Platform Admin authoritative resync — a fresh live fetch is always at
    least as new as anything a webhook could have applied, so it uses the
    current time as the ordering marker and always applies."""
    _require_enabled()
    market_id = market.id
    row = await _require_subscription_row(session, market_id)
    try:
        stripe_subscription = await stripe.Subscription.retrieve_async(row.stripe_subscription_id)
        resynced_row, _applied = await sync_subscription_from_stripe_object(
            session, stripe_subscription, event_created_at=utc_now(), market_id_hint=market_id
        )
        await session.commit()
        await session.refresh(resynced_row)
        return resynced_row
    except PermanentSyncError as exc:
        # The rollback expires every object in the session (including `row`
        # and `market`), so re-fetch by the plain id captured above.
        await session.rollback()
        row = await _require_subscription_row(session, market_id)
        row.sync_error = str(exc)[:1000]
        await session.commit()
        raise BillingError(str(exc), status_code=502) from exc
