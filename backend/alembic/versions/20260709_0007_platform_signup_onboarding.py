"""platform signup and onboarding

Revision ID: 20260709_0007
Revises: 20260707_0006
Create Date: 2026-07-09 00:07:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260709_0007"
down_revision: str | None = "20260707_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "platform_admins",
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_platform_admins_email", "platform_admins", ["email"])

    op.add_column("markets", sa.Column("country_code", sa.String(length=2), nullable=False, server_default="FR"))
    op.add_column("markets", sa.Column("city", sa.String(length=120), nullable=True))
    op.add_column("markets", sa.Column("contact_email", sa.String(length=255), nullable=True))
    op.add_column("markets", sa.Column("contact_phone", sa.String(length=64), nullable=True))
    op.add_column("markets", sa.Column("default_template_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("markets", sa.Column("lifecycle_status", sa.String(length=32), nullable=False, server_default="active"))
    op.add_column("markets", sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("markets", sa.Column("onboarding_status", sa.String(length=32), nullable=False, server_default="completed"))
    op.add_column("markets", sa.Column("onboarding_step", sa.Integer(), nullable=False, server_default="4"))
    op.add_column("markets", sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key("fk_markets_default_template_id_templates", "markets", "templates", ["default_template_id"], ["id"])
    op.create_check_constraint(
        "ck_markets_lifecycle_status",
        "markets",
        "lifecycle_status in ('trial', 'active', 'suspended', 'archived')",
    )
    op.create_check_constraint(
        "ck_markets_onboarding_status",
        "markets",
        "onboarding_status in ('not_started', 'in_progress', 'completed')",
    )

    op.add_column("market_invitations", sa.Column("created_by_platform_admin_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.alter_column("market_invitations", "created_by_user_id", existing_type=postgresql.UUID(as_uuid=True), nullable=True)
    op.create_foreign_key(
        "fk_market_invites_platform_admin",
        "market_invitations",
        "platform_admins",
        ["created_by_platform_admin_id"],
        ["id"],
    )

    op.create_table(
        "signup_requests",
        sa.Column("market_name", sa.String(length=255), nullable=False),
        sa.Column("contact_name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=64), nullable=True),
        sa.Column("country_code", sa.String(length=2), nullable=False),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("preferred_language", sa.String(length=16), nullable=False),
        sa.Column("expected_campaigns_per_month", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("consent_accepted", sa.Boolean(), nullable=False),
        sa.Column("consent_accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("provisioned_market_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_by_platform_admin_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provisioned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status in ('pending', 'reviewing', 'approved', 'rejected', 'provisioned')",
            name="ck_signup_requests_status",
        ),
        sa.ForeignKeyConstraint(["provisioned_market_id"], ["markets.id"]),
        sa.ForeignKeyConstraint(["reviewed_by_platform_admin_id"], ["platform_admins.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_signup_requests_status_created_at", "signup_requests", ["status", "created_at"])
    op.create_index("ix_signup_requests_email", "signup_requests", ["email"])
    op.create_index("ix_signup_requests_provisioned_market_id", "signup_requests", ["provisioned_market_id"])

    op.create_table(
        "signup_throttles",
        sa.Column("key_hash", sa.String(length=128), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_signup_throttles_key_window", "signup_throttles", ["key_hash", "window_started_at"])


def downgrade() -> None:
    op.drop_index("ix_signup_throttles_key_window", table_name="signup_throttles")
    op.drop_table("signup_throttles")
    op.drop_index("ix_signup_requests_provisioned_market_id", table_name="signup_requests")
    op.drop_index("ix_signup_requests_email", table_name="signup_requests")
    op.drop_index("ix_signup_requests_status_created_at", table_name="signup_requests")
    op.drop_table("signup_requests")
    op.drop_constraint("fk_market_invites_platform_admin", "market_invitations", type_="foreignkey")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM market_invitations
                WHERE created_by_user_id IS NULL
                  AND created_by_platform_admin_id IS NOT NULL
            ) THEN
                RAISE EXCEPTION
                    'Cannot downgrade 20260709_0007: platform-created invitations exist without tenant user creators. Revoke/resolve them or keep this migration.';
            END IF;
        END $$;
        """
    )
    op.alter_column("market_invitations", "created_by_user_id", existing_type=postgresql.UUID(as_uuid=True), nullable=False)
    op.drop_column("market_invitations", "created_by_platform_admin_id")
    op.drop_constraint("ck_markets_onboarding_status", "markets", type_="check")
    op.drop_constraint("ck_markets_lifecycle_status", "markets", type_="check")
    op.drop_constraint("fk_markets_default_template_id_templates", "markets", type_="foreignkey")
    op.drop_column("markets", "onboarding_completed_at")
    op.drop_column("markets", "onboarding_step")
    op.drop_column("markets", "onboarding_status")
    op.drop_column("markets", "trial_ends_at")
    op.drop_column("markets", "lifecycle_status")
    op.drop_column("markets", "default_template_id")
    op.drop_column("markets", "contact_phone")
    op.drop_column("markets", "contact_email")
    op.drop_column("markets", "city")
    op.drop_column("markets", "country_code")
    op.drop_index("ix_platform_admins_email", table_name="platform_admins")
    op.drop_table("platform_admins")
