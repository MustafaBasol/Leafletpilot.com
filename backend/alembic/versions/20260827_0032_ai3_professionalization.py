"""AI-3 post-approval professionalization.

Revision ID: 20260827_0032
Revises: 20260826_0031
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260827_0032"
down_revision: str | None = "20260826_0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_professionalization_runs",
        sa.Column("market_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_request_id", sa.String(length=128), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("capability", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("design_goal", sa.Text(), nullable=True),
        sa.Column("plan_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status in ('ready', 'applied', 'superseded', 'failed')", name="ck_ai_professionalization_runs_status"),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("market_id", "created_by_user_id", "client_request_id", name="uq_ai_professionalization_runs_market_user_request"),
    )
    op.create_index("ix_ai_professionalization_runs_market_campaign", "ai_professionalization_runs", ["market_id", "campaign_id"])
    op.create_index("ix_ai_professionalization_runs_campaign_active", "ai_professionalization_runs", ["campaign_id", "is_active"])
    op.create_index("ix_ai_professionalization_runs_market_created_at", "ai_professionalization_runs", ["market_id", "created_at"])


def downgrade() -> None:
    op.drop_table("ai_professionalization_runs")