"""Add truthful disabled invitation delivery state."""

from alembic import op
import sqlalchemy as sa

revision = "20260711_0011"
down_revision = "20260710_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_market_invitations_status", "market_invitations", type_="check")
    op.create_check_constraint(
        "ck_market_invitations_status",
        "market_invitations",
        "status in ('pending', 'sent', 'manual_delivery_required', 'accepted', 'revoked', 'expired', 'failed')",
    )
    op.drop_index("uq_market_invitations_active_market_email", table_name="market_invitations")
    op.create_index(
        "uq_market_invitations_active_market_email",
        "market_invitations",
        ["market_id", "email"],
        unique=True,
        postgresql_where=sa.text("status in ('pending', 'sent', 'manual_delivery_required', 'failed')"),
    )


def downgrade() -> None:
    op.drop_index("uq_market_invitations_active_market_email", table_name="market_invitations")
    op.create_index(
        "uq_market_invitations_active_market_email",
        "market_invitations",
        ["market_id", "email"],
        unique=True,
        postgresql_where=sa.text("status in ('pending', 'sent', 'failed')"),
    )
    op.drop_constraint("ck_market_invitations_status", "market_invitations", type_="check")
    op.create_check_constraint(
        "ck_market_invitations_status",
        "market_invitations",
        "status in ('pending', 'sent', 'accepted', 'revoked', 'expired', 'failed')",
    )
