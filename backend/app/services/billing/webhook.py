"""Stripe webhook signature verification and idempotent event dispatch."""

from __future__ import annotations

from datetime import UTC, datetime

import stripe
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select

from app.core.config import settings
from app.models.base import utc_now
from app.models.billing import MarketSubscription, StripeWebhookEvent
from app.services.billing.errors import PermanentSyncError, WebhookSignatureError
from app.services.billing.service import apply_checkout_completed, apply_invoice_event, sync_subscription_from_stripe_object

SUBSCRIPTION_EVENT_TYPES = {
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "customer.subscription.pending_update_applied",
    "customer.subscription.pending_update_expired",
}
INVOICE_EVENT_KINDS = {
    "invoice.paid": "paid",
    "invoice.payment_failed": "payment_failed",
    "invoice.payment_action_required": "payment_action_required",
}

# Terminal outcomes — a duplicate delivery of an event already in one of
# these states is a safe no-op (200, nothing re-applied). "received" is the
# only non-terminal status: it covers a brand-new event, one whose previous
# processing attempt crashed mid-flight, or one that failed transiently and
# was explicitly reset so a Stripe retry can reclaim it (see process_event).
TERMINAL_WEBHOOK_STATUSES = {"processed", "ignored", "ignored_stale", "failed"}


def construct_event(payload: bytes, sig_header: str | None) -> "stripe.Event":
    if not sig_header:
        raise WebhookSignatureError("Missing Stripe-Signature header.")
    try:
        return stripe.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)
    except (stripe.error.SignatureVerificationError, ValueError) as exc:
        raise WebhookSignatureError("Invalid Stripe webhook signature.") from exc


async def _claim_event_row(session: AsyncSession, event: "stripe.Event") -> StripeWebhookEvent | None:
    """Ensures a row exists for this Stripe event, then locks it (``SELECT
    ... FOR UPDATE``) for the remainder of processing.

    Returns ``None`` when the event is a duplicate delivery that's already
    terminal — a safe no-op. Otherwise returns the row, locked: a genuinely
    concurrent duplicate delivery blocks on the same ``FOR UPDATE`` until this
    transaction commits or rolls back, so at most one delivery is ever
    actively processing a given event at a time (required semantic: exactly
    one active processor). If this process crashes before committing or
    rolling back, Postgres releases the row lock with the dropped connection,
    so a later Stripe retry can still reclaim a row stuck at "received" —
    unlike a plain unique-constraint check, which would have permanently
    treated that retry as an already-handled duplicate.
    """
    stripe_event_id = event["id"]
    webhook_row = StripeWebhookEvent(
        stripe_event_id=stripe_event_id,
        event_type=event["type"],
        livemode=bool(event.get("livemode")),
        status="received",
    )
    session.add(webhook_row)
    try:
        await session.flush()
        await session.commit()
    except IntegrityError:
        # Row already exists — either a duplicate of an already-terminal
        # event, or one waiting to be (re)claimed below.
        await session.rollback()

    webhook_row = await session.scalar(
        select(StripeWebhookEvent).where(StripeWebhookEvent.stripe_event_id == stripe_event_id).with_for_update()
    )
    if webhook_row.status in TERMINAL_WEBHOOK_STATUSES:
        await session.commit()  # release the lock; nothing to do
        return None
    return webhook_row


async def process_event(session: AsyncSession, event: "stripe.Event") -> None:
    webhook_row = await _claim_event_row(session, event)
    if webhook_row is None:
        return

    webhook_row_id = webhook_row.id
    event_created_at = datetime.fromtimestamp(event["created"], tz=UTC)
    try:
        result = await _dispatch(session, event, event_created_at=event_created_at)
        if result is None:
            webhook_row.status = "ignored"
        else:
            row, applied = result
            webhook_row.subscription_id = row.id
            webhook_row.market_id = row.market_id
            webhook_row.status = "processed" if applied else "ignored_stale"
            if applied:
                webhook_row.processed_at = utc_now()
        webhook_row.error = None
        await session.commit()
    except PermanentSyncError as exc:
        await session.rollback()
        webhook_row = await session.get(StripeWebhookEvent, webhook_row_id)
        webhook_row.status = "failed"
        webhook_row.error = str(exc)[:1000]
        if exc.market_id is not None:
            webhook_row.market_id = exc.market_id
            subscription_row = await session.scalar(
                select(MarketSubscription).where(MarketSubscription.market_id == exc.market_id)
            )
            if subscription_row is None:
                # First-ever sync for this market failed permanently — persist a
                # placeholder row so the failure is visible in Platform Admin
                # instead of silently vanishing with the rolled-back transaction.
                subscription_row = MarketSubscription(
                    market_id=exc.market_id, plan_code="unassigned", status="incomplete"
                )
                session.add(subscription_row)
                await session.flush()
            subscription_row.sync_error = str(exc)[:1000]
            webhook_row.subscription_id = subscription_row.id
        await session.commit()
    except Exception as exc:
        # Transient failure (Stripe API hiccup, DB blip, ...) — not a
        # permanent mapping problem. Reset to "received" (rather than a
        # terminal status) so a later Stripe retry of the same event id can
        # reclaim and reprocess it instead of hitting the terminal-duplicate
        # no-op path. Re-raise so the route surfaces a failure response and
        # Stripe actually schedules that retry.
        await session.rollback()
        webhook_row = await session.get(StripeWebhookEvent, webhook_row_id)
        webhook_row.status = "received"
        webhook_row.error = f"{type(exc).__name__}: {exc}"[:1000]
        await session.commit()
        raise


async def _dispatch(session: AsyncSession, event: "stripe.Event", *, event_created_at: datetime):
    event_type = event["type"]
    stripe_object = event["data"]["object"]

    if event_type in SUBSCRIPTION_EVENT_TYPES:
        return await sync_subscription_from_stripe_object(session, stripe_object, event_created_at=event_created_at)
    if event_type == "checkout.session.completed":
        return await apply_checkout_completed(session, stripe_object, event_created_at=event_created_at)
    if event_type in INVOICE_EVENT_KINDS:
        return await apply_invoice_event(
            session, stripe_object, event_created_at=event_created_at, kind=INVOICE_EVENT_KINDS[event_type]
        )
    return None
