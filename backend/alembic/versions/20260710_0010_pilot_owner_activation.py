"""pilot owner activation hardening

Revision ID: 20260710_0010
Revises: 20260710_0009
Create Date: 2026-07-10 20:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260710_0010"
down_revision: str | None = "20260710_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_market_invitations_status", "market_invitations", type_="check")
    op.create_check_constraint(
        "ck_market_invitations_status",
        "market_invitations",
        "status in ('pending', 'sent', 'accepted', 'revoked', 'expired', 'failed')",
    )
    op.add_column("market_invitations", sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("market_invitations", sa.Column("send_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("market_invitations", sa.Column("last_send_error", sa.String(length=1000), nullable=True))
    op.alter_column("market_invitations", "send_count", server_default=None)
    op.alter_column("platform_audit_logs", "actor_platform_admin_id", existing_type=sa.UUID(), nullable=True)

    op.drop_index("uq_market_invitations_pending_market_email", table_name="market_invitations")
    op.create_index(
        "uq_market_invitations_active_market_email",
        "market_invitations",
        ["market_id", "email"],
        unique=True,
        postgresql_where=sa.text("status in ('pending', 'sent', 'failed')"),
    )


def downgrade() -> None:
    op.drop_index("uq_market_invitations_active_market_email", table_name="market_invitations")
    op.create_index(
        "uq_market_invitations_pending_market_email",
        "market_invitations",
        ["market_id", "email"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.alter_column("platform_audit_logs", "actor_platform_admin_id", existing_type=sa.UUID(), nullable=False)
    op.drop_column("market_invitations", "last_send_error")
    op.drop_column("market_invitations", "send_count")
    op.drop_column("market_invitations", "last_sent_at")
    op.drop_constraint("ck_market_invitations_status", "market_invitations", type_="check")
    op.create_check_constraint(
        "ck_market_invitations_status",
        "market_invitations",
        "status in ('pending', 'accepted', 'revoked', 'expired')",
    )
