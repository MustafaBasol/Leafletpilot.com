from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.market import Market


MARKET_SUBSCRIPTION_STATUSES = (
    "incomplete",
    "incomplete_expired",
    "trialing",
    "active",
    "past_due",
    "canceled",
    "unpaid",
    "paused",
)

STRIPE_WEBHOOK_EVENT_STATUSES = ("received", "processed", "ignored", "ignored_stale", "failed")

PENDING_CHANGE_REASONS = ("downgrade", "upgrade_pending_payment")


class MarketSubscription(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One row per market — the local mirror of that market's Stripe subscription.

    Stripe is authoritative for payment/subscription state; this row (and
    ``Market.subscription_plan``) are only ever written from webhook
    processing or the Platform Admin resync path, never from a mutation
    endpoint directly — see ``app/services/billing/service.py``.
    """

    __tablename__ = "market_subscriptions"
    __table_args__ = (
        CheckConstraint(
            f"status in {MARKET_SUBSCRIPTION_STATUSES}",
            name="ck_market_subscriptions_status",
        ),
        CheckConstraint(
            f"pending_change_reason is null or pending_change_reason in {PENDING_CHANGE_REASONS}",
            name="ck_market_subscriptions_pending_change_reason",
        ),
        Index("ix_market_subscriptions_stripe_customer_id", "stripe_customer_id"),
    )

    market_id: Mapped[UUID] = mapped_column(ForeignKey("markets.id"), nullable=False, unique=True)
    plan_code: Mapped[str] = mapped_column(String(32), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), default="stripe", nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)

    stripe_customer_id: Mapped[str | None] = mapped_column(String(255))
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    stripe_price_id: Mapped[str | None] = mapped_column(String(255))
    stripe_schedule_id: Mapped[str | None] = mapped_column(String(255), unique=True)

    currency: Mapped[str | None] = mapped_column(String(3))
    unit_amount: Mapped[int | None] = mapped_column(Integer)
    interval: Mapped[str | None] = mapped_column(String(16))

    current_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    subscription_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trial_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trial_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    pending_plan_code: Mapped[str | None] = mapped_column(String(32))
    pending_change_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pending_change_reason: Mapped[str | None] = mapped_column(String(32))

    latest_invoice_id: Mapped[str | None] = mapped_column(String(255))
    last_payment_status: Mapped[str | None] = mapped_column(String(32))
    last_payment_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sync_error: Mapped[str | None] = mapped_column(String(1000))
    last_stripe_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    market: Mapped[Market] = relationship()


class StripeWebhookEvent(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Idempotency + audit record for inbound Stripe webhook deliveries.

    The raw Stripe payload is intentionally not persisted (see plan) — only
    enough to dedupe, order, and diagnose failures.
    """

    __tablename__ = "stripe_webhook_events"
    __table_args__ = (
        CheckConstraint(
            f"status in {STRIPE_WEBHOOK_EVENT_STATUSES}",
            name="ck_stripe_webhook_events_status",
        ),
        Index("ix_stripe_webhook_events_market_id", "market_id"),
        Index("ix_stripe_webhook_events_created_at", "created_at"),
    )

    stripe_event_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    livemode: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="received", nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    market_id: Mapped[UUID | None] = mapped_column(ForeignKey("markets.id"))
    subscription_id: Mapped[UUID | None] = mapped_column(ForeignKey("market_subscriptions.id"))
    error: Mapped[str | None] = mapped_column(String(1000))
