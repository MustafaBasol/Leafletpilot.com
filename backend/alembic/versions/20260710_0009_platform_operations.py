"""platform operations audit and lifecycle controls

Revision ID: 20260710_0009
Revises: 20260709_0008
Create Date: 2026-07-10 00:09:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260710_0009"
down_revision: str | None = "20260709_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "platform_audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_platform_admin_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("target_type", sa.String(length=120), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["actor_platform_admin_id"], ["platform_admins.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_platform_audit_logs_actor_id", "platform_audit_logs", ["actor_platform_admin_id"])
    op.create_index("ix_platform_audit_logs_created_at", "platform_audit_logs", ["created_at"])
    op.create_index("ix_platform_audit_logs_target", "platform_audit_logs", ["target_type", "target_id"])

    op.add_column("markets", sa.Column("lifecycle_reason", sa.String(length=1000), nullable=True))
    op.add_column("markets", sa.Column("lifecycle_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("markets", sa.Column("lifecycle_updated_by_platform_admin_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_markets_lifecycle_platform_admin",
        "markets",
        "platform_admins",
        ["lifecycle_updated_by_platform_admin_id"],
        ["id"],
    )
    op.add_column("signup_requests", sa.Column("review_notes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("signup_requests", "review_notes")

    op.drop_constraint("fk_markets_lifecycle_platform_admin", "markets", type_="foreignkey")
    op.drop_column("markets", "lifecycle_updated_by_platform_admin_id")
    op.drop_column("markets", "lifecycle_updated_at")
    op.drop_column("markets", "lifecycle_reason")

    op.drop_index("ix_platform_audit_logs_target", table_name="platform_audit_logs")
    op.drop_index("ix_platform_audit_logs_created_at", table_name="platform_audit_logs")
    op.drop_index("ix_platform_audit_logs_actor_id", table_name="platform_audit_logs")
    op.drop_table("platform_audit_logs")
