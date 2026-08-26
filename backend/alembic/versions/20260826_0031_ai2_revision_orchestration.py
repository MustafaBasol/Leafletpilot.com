"""AI-2 provider-neutral revision orchestration.

Revision ID: 20260826_0031
Revises: 20260823_0030
Create Date: 2026-08-26 00:31:00.000000

Additive tenant-scoped proposal and prompt-free usage telemetry tables. The
existing shared fixed-window throttle table gains one non-sensitive AI user
key type; no campaign/catalog data is rewritten.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260826_0031"
down_revision: str | None = "20260823_0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_signup_throttles_key_type", "signup_throttles", type_="check")
    op.create_check_constraint(
        "ck_signup_throttles_key_type",
        "signup_throttles",
        "key_type in ('ip', 'email', 'whatsapp_ip', 'whatsapp_user', 'whatsapp_sender', 'ai_user')",
    )

    op.create_table(
        "ai_revision_proposals",
        sa.Column("market_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_request_id", sa.String(length=128), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("instruction", sa.Text(), nullable=False),
        sa.Column("expected_revision", sa.Integer(), nullable=False),
        sa.Column("capability", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("actions_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("clarification_question", sa.Text(), nullable=True),
        sa.Column("unsupported_reason", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status in ('ready', 'clarification_required', 'unsupported', 'applied', 'expired', 'failed')",
            name="ck_ai_revision_proposals_status",
        ),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["revision_id"], ["campaign_revisions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "market_id",
            "created_by_user_id",
            "client_request_id",
            name="uq_ai_revision_proposals_market_user_request",
        ),
    )
    op.create_index(
        "ix_ai_revision_proposals_market_campaign",
        "ai_revision_proposals",
        ["market_id", "campaign_id"],
    )
    op.create_index(
        "ix_ai_revision_proposals_campaign_status",
        "ai_revision_proposals",
        ["campaign_id", "status"],
    )
    op.create_index(
        "ix_ai_revision_proposals_market_created_at",
        "ai_revision_proposals",
        ["market_id", "created_at"],
    )

    op.create_table(
        "ai_usage_events",
        sa.Column("market_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("proposal_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("capability", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("request_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost_minor", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status in ('success', 'failed', 'timeout')",
            name="ck_ai_usage_events_status",
        ),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["proposal_id"], ["ai_revision_proposals.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_usage_events_market_created_at",
        "ai_usage_events",
        ["market_id", "created_at"],
    )
    op.create_index("ix_ai_usage_events_campaign_id", "ai_usage_events", ["campaign_id"])
    op.create_index("ix_ai_usage_events_proposal_id", "ai_usage_events", ["proposal_id"])


def downgrade() -> None:
    op.drop_table("ai_usage_events")
    op.drop_table("ai_revision_proposals")
    op.execute("DELETE FROM signup_throttles WHERE key_type = 'ai_user'")
    op.drop_constraint("ck_signup_throttles_key_type", "signup_throttles", type_="check")
    op.create_check_constraint(
        "ck_signup_throttles_key_type",
        "signup_throttles",
        "key_type in ('ip', 'email', 'whatsapp_ip', 'whatsapp_user', 'whatsapp_sender')",
    )
