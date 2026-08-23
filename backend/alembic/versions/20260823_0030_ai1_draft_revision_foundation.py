"""AI-1 deterministic campaign draft revisions.

Revision ID: 20260823_0030
Revises: 20260817_0029
Create Date: 2026-08-23 00:30:00.000000

Additive migration: existing campaigns begin at draft revision zero and no
catalog product data is rewritten. Revision history is tenant scoped and has
DB uniqueness guarantees for both idempotency and sequence ordering.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260823_0030"
down_revision: str | None = "20260817_0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "campaigns",
        sa.Column("draft_revision", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("campaigns", sa.Column("approved_revision", sa.Integer(), nullable=True))
    op.add_column(
        "campaign_items",
        sa.Column("is_hidden", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "campaign_items",
        sa.Column("emphasis", sa.String(length=16), nullable=False, server_default="normal"),
    )
    op.add_column(
        "campaign_items",
        sa.Column("image_override_product_image_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_campaign_items_image_override_product_image",
        "campaign_items",
        "product_images",
        ["image_override_product_image_id"],
        ["id"],
    )
    op.create_index("ix_campaign_items_campaign_hidden", "campaign_items", ["campaign_id", "is_hidden"])

    op.create_table(
        "campaign_revisions",
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("market_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="applied"),
        sa.Column("actions_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("before_snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("after_snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reverts_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source in ('panel', 'telegram', 'whatsapp', 'ai', 'system')",
            name="ck_campaign_revisions_source",
        ),
        sa.CheckConstraint("status in ('applied', 'undone')", name="ck_campaign_revisions_status"),
        sa.CheckConstraint("sequence > 0", name="ck_campaign_revisions_sequence_positive"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["reverts_revision_id"], ["campaign_revisions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_id", "request_id", name="uq_campaign_revisions_campaign_request"),
        sa.UniqueConstraint("campaign_id", "sequence", name="uq_campaign_revisions_campaign_sequence"),
    )
    op.create_index("ix_campaign_revisions_market_campaign", "campaign_revisions", ["market_id", "campaign_id"])
    op.create_index("ix_campaign_revisions_campaign_sequence", "campaign_revisions", ["campaign_id", "sequence"])
    op.create_index("ix_campaign_revisions_created_by_user_id", "campaign_revisions", ["created_by_user_id"])


def downgrade() -> None:
    op.drop_table("campaign_revisions")
    op.drop_index("ix_campaign_items_campaign_hidden", table_name="campaign_items")
    op.drop_constraint(
        "fk_campaign_items_image_override_product_image",
        "campaign_items",
        type_="foreignkey",
    )
    op.drop_column("campaign_items", "image_override_product_image_id")
    op.drop_column("campaign_items", "emphasis")
    op.drop_column("campaign_items", "is_hidden")
    op.drop_column("campaigns", "approved_revision")
    op.drop_column("campaigns", "draft_revision")
