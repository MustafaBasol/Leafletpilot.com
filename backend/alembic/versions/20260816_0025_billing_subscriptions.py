"""Add market_subscriptions and stripe_webhook_events for Stripe sandbox billing.

One row per market in ``market_subscriptions`` mirrors that market's Stripe
subscription; it (and ``Market.subscription_plan``) are only ever written
from webhook processing or the Platform Admin resync path. ``stripe_webhook_events``
provides DB-level idempotency (unique ``stripe_event_id``) for inbound webhook
deliveries.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260816_0025"
down_revision: str | None = "20260816_0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "market_subscriptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("market_id", sa.Uuid(), nullable=False),
        sa.Column("plan_code", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("stripe_customer_id", sa.String(length=255), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(length=255), nullable=True),
        sa.Column("stripe_price_id", sa.String(length=255), nullable=True),
        sa.Column("stripe_schedule_id", sa.String(length=255), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("unit_amount", sa.Integer(), nullable=True),
        sa.Column("interval", sa.String(length=16), nullable=True),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("subscription_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trial_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trial_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pending_plan_code", sa.String(length=32), nullable=True),
        sa.Column("pending_change_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pending_change_reason", sa.String(length=32), nullable=True),
        sa.Column("latest_invoice_id", sa.String(length=255), nullable=True),
        sa.Column("last_payment_status", sa.String(length=32), nullable=True),
        sa.Column("last_payment_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_error", sa.String(length=1000), nullable=True),
        sa.Column("last_stripe_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("market_id"),
        sa.UniqueConstraint("stripe_subscription_id"),
        sa.UniqueConstraint("stripe_schedule_id"),
        sa.CheckConstraint(
            "status in ('incomplete', 'incomplete_expired', 'trialing', 'active', 'past_due', "
            "'canceled', 'unpaid', 'paused')",
            name="ck_market_subscriptions_status",
        ),
        sa.CheckConstraint(
            "pending_change_reason is null or pending_change_reason in ('downgrade', 'upgrade_pending_payment')",
            name="ck_market_subscriptions_pending_change_reason",
        ),
    )
    op.create_index(
        "ix_market_subscriptions_stripe_customer_id", "market_subscriptions", ["stripe_customer_id"]
    )

    op.create_table(
        "stripe_webhook_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stripe_event_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("livemode", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("market_id", sa.Uuid(), nullable=True),
        sa.Column("subscription_id", sa.Uuid(), nullable=True),
        sa.Column("error", sa.String(length=1000), nullable=True),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.ForeignKeyConstraint(["subscription_id"], ["market_subscriptions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stripe_event_id"),
        sa.CheckConstraint(
            "status in ('received', 'processed', 'ignored', 'ignored_stale', 'failed')",
            name="ck_stripe_webhook_events_status",
        ),
    )
    op.create_index("ix_stripe_webhook_events_market_id", "stripe_webhook_events", ["market_id"])
    op.create_index("ix_stripe_webhook_events_created_at", "stripe_webhook_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_stripe_webhook_events_created_at", table_name="stripe_webhook_events")
    op.drop_index("ix_stripe_webhook_events_market_id", table_name="stripe_webhook_events")
    op.drop_table("stripe_webhook_events")
    op.drop_index("ix_market_subscriptions_stripe_customer_id", table_name="market_subscriptions")
    op.drop_table("market_subscriptions")
