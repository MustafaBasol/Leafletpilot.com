"""Central LeafletPilot WhatsApp channel (Evolution API).

Identity model, and why it is shaped this way:

    verified WhatsApp identity  ->  exactly one LeafletPilot user
                                ->  N active market memberships

A user legitimately operates several markets (Paris / Lyon / Grenoble), so
the identity hangs off `users`, never off `markets` — market scope is resolved
per command from the *current* `market_users` rows, not cached on the identity.
The three partial unique indexes on `user_whatsapp_identities` enforce the
security property that one phone/JID can never silently represent two
different LeafletPilot users, while still allowing an old revoked row to be
retained for audit.

`whatsapp_verifications` is the pending-challenge table (codes are stored
hashed, never in plaintext); `whatsapp_sessions` is the per-identity command
context; `whatsapp_webhook_events` is the idempotency ledger; and
`whatsapp_integration_state` is the single-row operational snapshot Platform
Admin reads (last webhook, last connectivity probe).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin, utc_now

if TYPE_CHECKING:
    from app.models.campaign import Campaign
    from app.models.export import ExportJob
    from app.models.market import Market
    from app.models.user import User


WHATSAPP_IDENTITY_STATUSES = ("verified", "revoked")
WHATSAPP_VERIFICATION_STATUSES = ("pending", "verified", "expired", "cancelled", "failed")
WHATSAPP_VERIFIED_SOURCES = ("evolution_whatsapp",)
WHATSAPP_SESSION_STATES = (
    "idle",
    "awaiting_market",
    "awaiting_product_list",
    "awaiting_title",
    "awaiting_confirmation",
    "generating_exports",
    "completed",
)
WHATSAPP_WEBHOOK_EVENT_STATUSES = ("received", "processing", "completed", "failed")


class UserWhatsAppIdentity(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A WhatsApp account proven to belong to a LeafletPilot user.

    `phone_e164`/`whatsapp_jid` are what the Evolution webhook actually
    reported, never what the UI typed — see
    `app/integrations/whatsapp/service.py`.
    """

    __tablename__ = "user_whatsapp_identities"
    __table_args__ = (
        CheckConstraint(
            "status in ('verified', 'revoked')",
            name="ck_user_whatsapp_identities_status",
        ),
        CheckConstraint(
            "verified_source in ('evolution_whatsapp')",
            name="ck_user_whatsapp_identities_verified_source",
        ),
        Index("ix_user_whatsapp_identities_user_id", "user_id"),
        Index("ix_user_whatsapp_identities_status", "status"),
        Index("ix_user_whatsapp_identities_phone_e164", "phone_e164"),
        # One *verified* identity per phone / per JID / per user. Revoked rows
        # are excluded so history survives and the same number can later be
        # re-verified (possibly by a different user, after an explicit revoke).
        Index(
            "uq_user_whatsapp_identities_verified_phone",
            "phone_e164",
            unique=True,
            postgresql_where=text("status = 'verified'"),
        ),
        Index(
            "uq_user_whatsapp_identities_verified_jid",
            "whatsapp_jid",
            unique=True,
            postgresql_where=text("status = 'verified'"),
        ),
        Index(
            "uq_user_whatsapp_identities_verified_user",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'verified'"),
        ),
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    phone_e164: Mapped[str] = mapped_column(String(32), nullable=False)
    whatsapp_jid: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="verified", nullable=False)
    verified_source: Mapped[str] = mapped_column(String(32), default="evolution_whatsapp", nullable=False)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    verified_via_market_id: Mapped[UUID | None] = mapped_column(ForeignKey("markets.id"))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(String(255))
    revoked_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    revoked_by_platform_admin_id: Mapped[UUID | None] = mapped_column(ForeignKey("platform_admins.id"))

    user: Mapped[User] = relationship(foreign_keys=[user_id])
    verified_via_market: Mapped[Market | None] = relationship()


class WhatsAppVerification(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A one-time challenge the user must send from their own WhatsApp.

    Only `code_hash` is persisted; the plaintext code is returned exactly once
    (in the creation response) and never logged, re-read or audited.
    """

    __tablename__ = "whatsapp_verifications"
    __table_args__ = (
        CheckConstraint(
            "status in ('pending', 'verified', 'expired', 'cancelled', 'failed')",
            name="ck_whatsapp_verifications_status",
        ),
        Index("ix_whatsapp_verifications_user_id", "user_id"),
        Index("ix_whatsapp_verifications_market_id", "market_id"),
        Index("ix_whatsapp_verifications_status", "status"),
        Index("ix_whatsapp_verifications_expires_at", "expires_at"),
        # Lookup path for an inbound message that might be a code.
        Index(
            "uq_whatsapp_verifications_pending_code_hash",
            "code_hash",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        # At most one live challenge per user: issuing a new code invalidates
        # the previous one in the same transaction.
        Index(
            "uq_whatsapp_verifications_pending_user",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    market_id: Mapped[UUID] = mapped_column(ForeignKey("markets.id"), nullable=False)
    membership_id: Mapped[UUID | None] = mapped_column(ForeignKey("market_users.id"))
    requested_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    code_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    claimed_phone_e164: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_phone_e164: Mapped[str | None] = mapped_column(String(32))
    resolved_jid: Mapped[str | None] = mapped_column(String(255))
    failure_reason: Mapped[str | None] = mapped_column(String(255))

    user: Mapped[User] = relationship(foreign_keys=[user_id])
    market: Mapped[Market] = relationship()


class WhatsAppSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Per-identity command context (active market + brochure draft state).

    Mirrors the shape the Telegram channel proved out, but is an entirely
    separate table so the WhatsApp channel can never mutate Telegram state.
    `active_market_id` is a *cache of a choice*, not an authorization: every
    command re-resolves the membership before acting.
    """

    __tablename__ = "whatsapp_sessions"
    __table_args__ = (
        CheckConstraint(
            "state in ('idle', 'awaiting_market', 'awaiting_product_list', 'awaiting_title', "
            "'awaiting_confirmation', 'generating_exports', 'completed')",
            name="ck_whatsapp_sessions_state",
        ),
        Index("ix_whatsapp_sessions_identity_id", "identity_id", unique=True),
        Index("ix_whatsapp_sessions_user_id", "user_id"),
        Index("ix_whatsapp_sessions_active_market_id", "active_market_id"),
        Index("ix_whatsapp_sessions_state", "state"),
    )

    identity_id: Mapped[UUID] = mapped_column(ForeignKey("user_whatsapp_identities.id"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    active_market_id: Mapped[UUID | None] = mapped_column(ForeignKey("markets.id"))
    state: Mapped[str] = mapped_column(String(64), default="idle", nullable=False)
    pending_raw_text: Mapped[str | None] = mapped_column(Text)
    parsed_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    pending_title: Mapped[str | None] = mapped_column(String(255))
    campaign_id: Mapped[UUID | None] = mapped_column(ForeignKey("campaigns.id"))
    export_job_id: Mapped[UUID | None] = mapped_column(ForeignKey("export_jobs.id"))
    export_document_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    export_image_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    export_files_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revision_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # High-impact actions (publish/delete/export) are held here until the user
    # replies ONAYLA, and are bound to user + market + action + expiry so a
    # stale confirmation can never execute against a different market.
    pending_action: Mapped[str | None] = mapped_column(String(64))
    pending_action_market_id: Mapped[UUID | None] = mapped_column(ForeignKey("markets.id"))
    pending_action_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    pending_action_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    market_choice_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    last_error: Mapped[str | None] = mapped_column(String(1000))
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    identity: Mapped[UserWhatsAppIdentity] = relationship()
    user: Mapped[User] = relationship()
    active_market: Mapped[Market | None] = relationship(foreign_keys=[active_market_id])
    campaign: Mapped[Campaign | None] = relationship()
    export_job: Mapped[ExportJob | None] = relationship()


class WhatsAppWebhookEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Idempotency ledger for Evolution webhook deliveries.

    `event_key` is `<instance>:<event>:<message id>`; Evolution and WhatsApp
    both redeliver, so a duplicate delivery must never verify twice or
    generate a second campaign. The processing lease mirrors the Telegram
    ledger so a crashed in-flight event is retried rather than wedged.
    """

    __tablename__ = "whatsapp_webhook_events"
    __table_args__ = (
        CheckConstraint(
            "status in ('received', 'processing', 'completed', 'failed')",
            name="ck_whatsapp_webhook_events_status",
        ),
        Index("ix_whatsapp_webhook_events_event_key", "event_key", unique=True),
        Index("ix_whatsapp_webhook_events_status", "status"),
        Index("ix_whatsapp_webhook_events_received_at", "received_at"),
    )

    event_key: Mapped[str] = mapped_column(String(512), nullable=False)
    instance_name: Mapped[str | None] = mapped_column(String(255))
    event_type: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(32), default="received", nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(String(1000))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WhatsAppIntegrationState(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Operational snapshot per Evolution instance for Platform Admin.

    Holds only derived signals (timestamps, connection state, last error
    string) — never the API key, the webhook secret, or message content, so it
    is safe to surface verbatim in the Platform Admin UI.
    """

    __tablename__ = "whatsapp_integration_state"
    __table_args__ = (Index("uq_whatsapp_integration_state_instance", "instance_name", unique=True),)

    instance_name: Mapped[str] = mapped_column(String(255), nullable=False)
    last_webhook_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_webhook_event_type: Mapped[str | None] = mapped_column(String(120))
    last_inbound_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_connection_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_connection_state: Mapped[str | None] = mapped_column(String(64))
    last_connection_ok: Mapped[bool | None] = mapped_column(Boolean)
    last_connection_error: Mapped[str | None] = mapped_column(String(1000))
    last_outbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_outbound_error: Mapped[str | None] = mapped_column(String(1000))
    last_outbound_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
