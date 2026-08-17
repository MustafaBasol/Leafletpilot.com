"""central whatsapp evolution integration

Revision ID: 20260817_0029
Revises: 20260817_0028
Create Date: 2026-08-17 00:29:00.000000

Additive only. Creates the five tables backing the central LeafletPilot
WhatsApp channel and widens the existing signup_throttles key_type CHECK so
the WhatsApp channel can reuse the proven bucketed rate limiter instead of
introducing a second one.

No existing table is dropped or rewritten and no existing row is modified, so
this is safe to run against production while the API is up. Rolling back drops
only the new objects and restores the original CHECK (which requires no
WhatsApp throttle rows to remain — the downgrade deletes them first).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260817_0029"
down_revision: str | None = "20260817_0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


WHATSAPP_THROTTLE_KEY_TYPES = ("whatsapp_ip", "whatsapp_user", "whatsapp_sender")


def upgrade() -> None:
    op.create_table(
        "user_whatsapp_identities",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("phone_e164", sa.String(length=32), nullable=False),
        sa.Column("whatsapp_jid", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="verified"),
        sa.Column("verified_source", sa.String(length=32), nullable=False, server_default="evolution_whatsapp"),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_via_market_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.String(length=255), nullable=True),
        sa.Column("revoked_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("revoked_by_platform_admin_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status in ('verified', 'revoked')", name="ck_user_whatsapp_identities_status"),
        sa.CheckConstraint(
            "verified_source in ('evolution_whatsapp')",
            name="ck_user_whatsapp_identities_verified_source",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["verified_via_market_id"], ["markets.id"]),
        sa.ForeignKeyConstraint(["revoked_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["revoked_by_platform_admin_id"], ["platform_admins.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_whatsapp_identities_user_id", "user_whatsapp_identities", ["user_id"])
    op.create_index("ix_user_whatsapp_identities_status", "user_whatsapp_identities", ["status"])
    op.create_index("ix_user_whatsapp_identities_phone_e164", "user_whatsapp_identities", ["phone_e164"])
    # The security-critical uniqueness guarantees: one verified identity per
    # phone, per JID and per user. Partial so revoked history is retained.
    op.create_index(
        "uq_user_whatsapp_identities_verified_phone",
        "user_whatsapp_identities",
        ["phone_e164"],
        unique=True,
        postgresql_where=sa.text("status = 'verified'"),
    )
    op.create_index(
        "uq_user_whatsapp_identities_verified_jid",
        "user_whatsapp_identities",
        ["whatsapp_jid"],
        unique=True,
        postgresql_where=sa.text("status = 'verified'"),
    )
    op.create_index(
        "uq_user_whatsapp_identities_verified_user",
        "user_whatsapp_identities",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'verified'"),
    )

    op.create_table(
        "whatsapp_verifications",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("market_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("membership_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("code_hash", sa.String(length=128), nullable=False),
        sa.Column("claimed_phone_e164", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_phone_e164", sa.String(length=32), nullable=True),
        sa.Column("resolved_jid", sa.String(length=255), nullable=True),
        sa.Column("failure_reason", sa.String(length=255), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status in ('pending', 'verified', 'expired', 'cancelled', 'failed')",
            name="ck_whatsapp_verifications_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.ForeignKeyConstraint(["membership_id"], ["market_users.id"]),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_whatsapp_verifications_user_id", "whatsapp_verifications", ["user_id"])
    op.create_index("ix_whatsapp_verifications_market_id", "whatsapp_verifications", ["market_id"])
    op.create_index("ix_whatsapp_verifications_status", "whatsapp_verifications", ["status"])
    op.create_index("ix_whatsapp_verifications_expires_at", "whatsapp_verifications", ["expires_at"])
    op.create_index(
        "uq_whatsapp_verifications_pending_code_hash",
        "whatsapp_verifications",
        ["code_hash"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "uq_whatsapp_verifications_pending_user",
        "whatsapp_verifications",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )

    op.create_table(
        "whatsapp_sessions",
        sa.Column("identity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("active_market_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("state", sa.String(length=64), nullable=False, server_default="idle"),
        sa.Column("pending_raw_text", sa.Text(), nullable=True),
        sa.Column("parsed_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("pending_title", sa.String(length=255), nullable=True),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("export_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("export_document_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("export_image_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("export_files_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revision_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pending_action", sa.String(length=64), nullable=True),
        sa.Column("pending_action_market_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("pending_action_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("pending_action_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("market_choice_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("last_error", sa.String(length=1000), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state in ('idle', 'awaiting_market', 'awaiting_product_list', 'awaiting_title', "
            "'awaiting_confirmation', 'generating_exports', 'completed')",
            name="ck_whatsapp_sessions_state",
        ),
        sa.ForeignKeyConstraint(["identity_id"], ["user_whatsapp_identities.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["active_market_id"], ["markets.id"]),
        sa.ForeignKeyConstraint(["pending_action_market_id"], ["markets.id"]),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["export_job_id"], ["export_jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_whatsapp_sessions_identity_id", "whatsapp_sessions", ["identity_id"], unique=True)
    op.create_index("ix_whatsapp_sessions_user_id", "whatsapp_sessions", ["user_id"])
    op.create_index("ix_whatsapp_sessions_active_market_id", "whatsapp_sessions", ["active_market_id"])
    op.create_index("ix_whatsapp_sessions_state", "whatsapp_sessions", ["state"])

    op.create_table(
        "whatsapp_webhook_events",
        sa.Column("event_key", sa.String(length=512), nullable=False),
        sa.Column("instance_name", sa.String(length=255), nullable=True),
        sa.Column("event_type", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="received"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(length=1000), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status in ('received', 'processing', 'completed', 'failed')",
            name="ck_whatsapp_webhook_events_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_whatsapp_webhook_events_event_key", "whatsapp_webhook_events", ["event_key"], unique=True)
    op.create_index("ix_whatsapp_webhook_events_status", "whatsapp_webhook_events", ["status"])
    op.create_index("ix_whatsapp_webhook_events_received_at", "whatsapp_webhook_events", ["received_at"])

    op.create_table(
        "whatsapp_integration_state",
        sa.Column("instance_name", sa.String(length=255), nullable=False),
        sa.Column("last_webhook_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_webhook_event_type", sa.String(length=120), nullable=True),
        sa.Column("last_inbound_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_connection_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_connection_state", sa.String(length=64), nullable=True),
        sa.Column("last_connection_ok", sa.Boolean(), nullable=True),
        sa.Column("last_connection_error", sa.String(length=1000), nullable=True),
        sa.Column("last_outbound_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_outbound_error", sa.String(length=1000), nullable=True),
        sa.Column("last_outbound_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_whatsapp_integration_state_instance",
        "whatsapp_integration_state",
        ["instance_name"],
        unique=True,
    )

    # Widen the shared throttle key_type CHECK so the WhatsApp limiter can use
    # the same table. Existing ('ip', 'email') rows remain valid.
    op.drop_constraint("ck_signup_throttles_key_type", "signup_throttles", type_="check")
    op.create_check_constraint(
        "ck_signup_throttles_key_type",
        "signup_throttles",
        "key_type in ('ip', 'email', 'whatsapp_ip', 'whatsapp_user', 'whatsapp_sender')",
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM signup_throttles WHERE key_type IN "
        "('whatsapp_ip', 'whatsapp_user', 'whatsapp_sender')"
    )
    op.drop_constraint("ck_signup_throttles_key_type", "signup_throttles", type_="check")
    op.create_check_constraint(
        "ck_signup_throttles_key_type",
        "signup_throttles",
        "key_type in ('ip', 'email')",
    )

    op.drop_index("uq_whatsapp_integration_state_instance", table_name="whatsapp_integration_state")
    op.drop_table("whatsapp_integration_state")

    op.drop_index("ix_whatsapp_webhook_events_received_at", table_name="whatsapp_webhook_events")
    op.drop_index("ix_whatsapp_webhook_events_status", table_name="whatsapp_webhook_events")
    op.drop_index("ix_whatsapp_webhook_events_event_key", table_name="whatsapp_webhook_events")
    op.drop_table("whatsapp_webhook_events")

    op.drop_index("ix_whatsapp_sessions_state", table_name="whatsapp_sessions")
    op.drop_index("ix_whatsapp_sessions_active_market_id", table_name="whatsapp_sessions")
    op.drop_index("ix_whatsapp_sessions_user_id", table_name="whatsapp_sessions")
    op.drop_index("ix_whatsapp_sessions_identity_id", table_name="whatsapp_sessions")
    op.drop_table("whatsapp_sessions")

    op.drop_index("uq_whatsapp_verifications_pending_user", table_name="whatsapp_verifications")
    op.drop_index("uq_whatsapp_verifications_pending_code_hash", table_name="whatsapp_verifications")
    op.drop_index("ix_whatsapp_verifications_expires_at", table_name="whatsapp_verifications")
    op.drop_index("ix_whatsapp_verifications_status", table_name="whatsapp_verifications")
    op.drop_index("ix_whatsapp_verifications_market_id", table_name="whatsapp_verifications")
    op.drop_index("ix_whatsapp_verifications_user_id", table_name="whatsapp_verifications")
    op.drop_table("whatsapp_verifications")

    op.drop_index("uq_user_whatsapp_identities_verified_user", table_name="user_whatsapp_identities")
    op.drop_index("uq_user_whatsapp_identities_verified_jid", table_name="user_whatsapp_identities")
    op.drop_index("uq_user_whatsapp_identities_verified_phone", table_name="user_whatsapp_identities")
    op.drop_index("ix_user_whatsapp_identities_phone_e164", table_name="user_whatsapp_identities")
    op.drop_index("ix_user_whatsapp_identities_status", table_name="user_whatsapp_identities")
    op.drop_index("ix_user_whatsapp_identities_user_id", table_name="user_whatsapp_identities")
    op.drop_table("user_whatsapp_identities")
