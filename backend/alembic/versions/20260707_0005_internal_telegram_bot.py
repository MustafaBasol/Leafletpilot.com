"""internal telegram bot

Revision ID: 20260707_0005
Revises: 20260707_0004
Create Date: 2026-07-07 00:05:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260707_0005"
down_revision: str | None = "20260707_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "telegram_accounts",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("first_name", sa.String(length=255), nullable=True),
        sa.Column("last_name", sa.String(length=255), nullable=True),
        sa.Column("last_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_telegram_accounts_user_id", "telegram_accounts", ["user_id"])
    op.create_index(
        "ix_telegram_accounts_telegram_user_id",
        "telegram_accounts",
        ["telegram_user_id"],
        unique=True,
    )
    op.create_index(
        "uq_telegram_accounts_active_user_id",
        "telegram_accounts",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("is_active IS TRUE"),
    )

    op.create_table(
        "telegram_updates",
        sa.Column("update_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=True),
        sa.Column("update_type", sa.String(length=64), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(length=1000), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status in ('received', 'processing', 'completed', 'failed')",
            name="ck_telegram_updates_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_telegram_updates_update_id", "telegram_updates", ["update_id"], unique=True)
    op.create_index("ix_telegram_updates_status", "telegram_updates", ["status"])
    op.create_index("ix_telegram_updates_telegram_user_id", "telegram_updates", ["telegram_user_id"])
    op.create_index("ix_telegram_updates_chat_id", "telegram_updates", ["chat_id"])
    op.create_index("ix_telegram_updates_received_at", "telegram_updates", ["received_at"])

    op.create_table(
        "telegram_conversation_states",
        sa.Column("telegram_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=True),
        sa.Column("selected_market_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("state", sa.String(length=64), nullable=False),
        sa.Column("pending_raw_text", sa.Text(), nullable=True),
        sa.Column("parsed_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("pending_title", sa.String(length=255), nullable=True),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("export_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("last_error", sa.String(length=1000), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state in ('idle', 'awaiting_market', 'awaiting_product_list', 'awaiting_title', "
            "'awaiting_confirmation', 'generating_exports', 'completed')",
            name="ck_telegram_conversation_states_state",
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["export_job_id"], ["export_jobs.id"]),
        sa.ForeignKeyConstraint(["selected_market_id"], ["markets.id"]),
        sa.ForeignKeyConstraint(["telegram_account_id"], ["telegram_accounts.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_telegram_conversation_states_user_id", "telegram_conversation_states", ["user_id"])
    op.create_index(
        "ix_telegram_conversation_states_selected_market_id",
        "telegram_conversation_states",
        ["selected_market_id"],
    )
    op.create_index("ix_telegram_conversation_states_state", "telegram_conversation_states", ["state"])
    op.create_index(
        "ix_telegram_conversation_states_telegram_user_id",
        "telegram_conversation_states",
        ["telegram_user_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_telegram_conversation_states_telegram_user_id", table_name="telegram_conversation_states")
    op.drop_index("ix_telegram_conversation_states_state", table_name="telegram_conversation_states")
    op.drop_index("ix_telegram_conversation_states_selected_market_id", table_name="telegram_conversation_states")
    op.drop_index("ix_telegram_conversation_states_user_id", table_name="telegram_conversation_states")
    op.drop_table("telegram_conversation_states")

    op.drop_index("ix_telegram_updates_received_at", table_name="telegram_updates")
    op.drop_index("ix_telegram_updates_chat_id", table_name="telegram_updates")
    op.drop_index("ix_telegram_updates_telegram_user_id", table_name="telegram_updates")
    op.drop_index("ix_telegram_updates_status", table_name="telegram_updates")
    op.drop_index("ix_telegram_updates_update_id", table_name="telegram_updates")
    op.drop_table("telegram_updates")

    op.drop_index("uq_telegram_accounts_active_user_id", table_name="telegram_accounts")
    op.drop_index("ix_telegram_accounts_telegram_user_id", table_name="telegram_accounts")
    op.drop_index("ix_telegram_accounts_user_id", table_name="telegram_accounts")
    op.drop_table("telegram_accounts")
