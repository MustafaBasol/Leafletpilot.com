"""Make market plans explicit and prepare the production template bootstrap."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260716_0017"
down_revision: str | None = "20260713_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE markets SET subscription_plan = 'starter' WHERE subscription_plan IS NULL")
    op.alter_column("markets", "subscription_plan", existing_type=sa.String(length=32), nullable=False, server_default="starter")
    op.create_check_constraint(
        "ck_markets_subscription_plan",
        "markets",
        "subscription_plan in ('starter', 'growth', 'pro')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_markets_subscription_plan", "markets", type_="check")
    op.alter_column("markets", "subscription_plan", existing_type=sa.String(length=32), nullable=True, server_default=None)
