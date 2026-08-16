"""Add the canonical "standard" subscription plan code.

"growth" remains a valid, persisted legacy code (existing markets, seed
scripts, and fixtures still write it); the service layer resolves it as an
alias of "standard" for capability/ranking purposes. This migration only
widens the CHECK constraint so new markets can be provisioned directly onto
"standard" without renaming or backfilling existing "growth" rows.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260816_0023"
down_revision: str | None = "20260816_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_markets_subscription_plan", "markets", type_="check")
    op.create_check_constraint(
        "ck_markets_subscription_plan",
        "markets",
        "subscription_plan in ('starter', 'standard', 'growth', 'pro')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_markets_subscription_plan", "markets", type_="check")
    op.create_check_constraint(
        "ck_markets_subscription_plan",
        "markets",
        "subscription_plan in ('starter', 'growth', 'pro')",
    )
