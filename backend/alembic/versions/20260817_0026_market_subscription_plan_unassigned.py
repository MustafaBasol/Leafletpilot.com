"""Allow the "unassigned" subscription plan code on markets.

Production incident: a Stripe `customer.subscription.deleted` webhook for a
canceled subscription made the application layer write
``markets.subscription_plan = 'unassigned'`` (the no-active-paid-entitlement
terminal state — see ``app/services/billing/service.py:_apply_entitlement``
and ``DOWNGRADE_TO_UNASSIGNED_STATUSES``), but ``ck_markets_subscription_plan``
never allowed that value, so the commit raised a ``CheckViolationError`` and
the webhook was stuck at status="received" with the IntegrityError recorded
in ``stripe_webhook_events.error``.

"unassigned" is canonical application-level state, not new domain concept —
this migration only catches the DB constraint up to what the code already
assumes. No data changes; existing starter/standard/growth/pro rows are
untouched.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260817_0026"
down_revision: str | None = "20260816_0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_markets_subscription_plan", "markets", type_="check")
    op.create_check_constraint(
        "ck_markets_subscription_plan",
        "markets",
        "subscription_plan in ('starter', 'standard', 'growth', 'pro', 'unassigned')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_markets_subscription_plan", "markets", type_="check")
    op.create_check_constraint(
        "ck_markets_subscription_plan",
        "markets",
        "subscription_plan in ('starter', 'standard', 'growth', 'pro')",
    )
