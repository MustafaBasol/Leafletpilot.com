"""telegram idempotency stabilization

Revision ID: 20260707_0006
Revises: 20260707_0005
Create Date: 2026-07-07 00:06:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260707_0006"
down_revision: str | None = "20260707_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("telegram_updates", sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_telegram_updates_processing_started_at", "telegram_updates", ["processing_started_at"])
    op.add_column(
        "telegram_conversation_states",
        sa.Column("export_document_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "telegram_conversation_states",
        sa.Column("export_photo_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "telegram_conversation_states",
        sa.Column("export_files_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "telegram_conversation_states",
        sa.Column("export_delivery_started_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("telegram_conversation_states", "export_delivery_started_at")
    op.drop_column("telegram_conversation_states", "export_files_sent_at")
    op.drop_column("telegram_conversation_states", "export_photo_sent_at")
    op.drop_column("telegram_conversation_states", "export_document_sent_at")
    op.drop_index("ix_telegram_updates_processing_started_at", table_name="telegram_updates")
    op.drop_column("telegram_updates", "processing_started_at")
