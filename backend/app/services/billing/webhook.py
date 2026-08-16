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


def construct_event(payload: bytes, sig_header: str | None) -> "stripe.Event":
    if not sig_header:
        raise WebhookSignatureError("Missing Stripe-Signature header.")
    try:
        return stripe.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)
    except (stripe.error.SignatureVerificationError, ValueError) as exc:
        raise WebhookSignatureError("Invalid Stripe webhook signature.") from exc


async def process_event(session: AsyncSession, event: "stripe.Event") -> None:
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
        # DB unique constraint on stripe_event_id caught a duplicate/concurrent
        # delivery of the same event — safe no-op, exactly one delivery ever
        # reaches the processing step below.
        await session.rollback()
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
    except Exception:
        await session.rollback()
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
