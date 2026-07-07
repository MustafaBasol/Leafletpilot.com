"""roles and market invitations

Revision ID: 20260707_0004
Revises: 20260704_0003
Create Date: 2026-07-07 00:04:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260707_0004"
down_revision: str | None = "20260704_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE market_users SET role = 'viewer' WHERE role = 'operator'")
    op.execute("UPDATE market_users SET role = 'market_admin' WHERE role = 'platform_admin'")
    op.drop_constraint("ck_market_users_role", "market_users", type_="check")
    op.create_check_constraint(
        "ck_market_users_role",
        "market_users",
        "role in ('market_admin', 'market_staff', 'viewer')",
    )
    op.create_table(
        "market_invitations",
        sa.Column("market_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("accepted_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "role in ('market_admin', 'market_staff', 'viewer')",
            name="ck_market_invitations_role",
        ),
        sa.CheckConstraint(
            "status in ('pending', 'accepted', 'revoked', 'expired')",
            name="ck_market_invitations_status",
        ),
        sa.ForeignKeyConstraint(["accepted_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_market_invitations_market_id", "market_invitations", ["market_id"])
    op.create_index("ix_market_invitations_token_hash", "market_invitations", ["token_hash"])
    op.create_index(
        "uq_market_invitations_pending_market_email",
        "market_invitations",
        ["market_id", "email"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_market_invitations_pending_market_email")
    op.drop_index("ix_market_invitations_token_hash", table_name="market_invitations")
    op.drop_index("ix_market_invitations_market_id", table_name="market_invitations")
    op.drop_table("market_invitations")
    op.drop_constraint("ck_market_users_role", "market_users", type_="check")
    op.execute("UPDATE market_users SET role = 'operator' WHERE role = 'viewer'")
    op.create_check_constraint(
        "ck_market_users_role",
        "market_users",
        "role in ('platform_admin', 'market_admin', 'market_staff', 'operator')",
    )
