"""Persist versioned campaign intelligence plans."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260809_0018"
down_revision: str | None = "20260716_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("campaigns", sa.Column("intelligence_json", postgresql.JSONB(), nullable=True))
    op.add_column(
        "campaigns",
        sa.Column("intelligence_analyzed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("campaigns", "intelligence_analyzed_at")
    op.drop_column("campaigns", "intelligence_json")
