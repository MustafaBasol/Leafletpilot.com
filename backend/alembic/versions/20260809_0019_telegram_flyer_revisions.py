"""Persist Telegram flyer revision context."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260809_0019"
down_revision: str | None = "20260809_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "telegram_conversation_states",
        sa.Column("revision_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "telegram_conversation_states",
        sa.Column("last_edit_intent_json", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("telegram_conversation_states", "last_edit_intent_json")
    op.drop_column("telegram_conversation_states", "revision_count")
