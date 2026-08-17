"""API contract for the central LeafletPilot WhatsApp channel.

Nothing in this module may ever carry a secret: the Evolution API key, the
webhook secret and verification codes are excluded by construction. The one
exception is `WhatsAppVerificationCreateResponse.code`, which returns the
freshly generated challenge exactly once, to the authorized caller that just
created it — it is never readable again from any other endpoint.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

# Statuses the market-side UI renders per member. "not_configured" is the
# synthetic state for a member who has never started verification.
WHATSAPP_MEMBER_STATUSES = ("not_configured", "pending", "verified", "expired", "revoked")


class WhatsAppMemberStatusRead(BaseModel):
    """One eligible market member and their WhatsApp verification state."""

    membership_id: UUID
    user_id: UUID
    email: str
    full_name: str | None = None
    role: str
    is_active: bool
    status: str
    # Only ever the number Evolution reported, and only for a verified identity.
    verified_phone: str | None = None
    verified_phone_masked: str | None = None
    verified_at: datetime | None = None
    last_seen_at: datetime | None = None
    revoked_at: datetime | None = None
    # Present while a challenge is live so the UI can resume the wait state
    # (never includes the code itself).
    pending_verification_id: UUID | None = None
    pending_expires_at: datetime | None = None
    # Advisory number the requester typed; not proof of ownership.
    claimed_phone: str | None = None
    can_manage: bool = False


class WhatsAppChannelStatusRead(BaseModel):
    """Market-scoped channel status. Safe for any active market member."""

    enabled: bool
    configured: bool
    official_number: str | None = None
    official_number_display: str | None = None
    verification_expire_minutes: int
    resend_cooldown_seconds: int
    can_manage_members: bool = False
    members: list[WhatsAppMemberStatusRead] = Field(default_factory=list)


class WhatsAppVerificationCreateRequest(BaseModel):
    membership_id: UUID
    # Optional, advisory only: shown back to the requester so they can sanity
    # check which handset should send the code. The authoritative number comes
    # from the Evolution webhook sender.
    phone: str | None = Field(default=None, max_length=32)


class WhatsAppVerificationCreateResponse(BaseModel):
    verification_id: UUID
    membership_id: UUID
    user_id: UUID
    # Returned once, at creation time, to the authorized requester only.
    code: str
    expires_at: datetime
    official_number: str
    official_number_display: str
    whatsapp_deep_link: str
    resend_available_at: datetime


class WhatsAppVerificationRead(BaseModel):
    """Polling shape. Deliberately omits the code."""

    verification_id: UUID
    membership_id: UUID | None = None
    user_id: UUID
    status: str
    expires_at: datetime
    created_at: datetime
    consumed_at: datetime | None = None
    verified_phone: str | None = None
    verified_phone_masked: str | None = None
    failure_reason: str | None = None


class WhatsAppRevokeRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=255)


# --- Platform Admin -------------------------------------------------------


class PlatformWhatsAppHealthRead(BaseModel):
    """Connection health. Contains no credential material of any kind."""

    enabled: bool
    configured: bool
    instance_name: str | None = None
    official_number_masked: str | None = None
    base_url_host: str | None = None
    connection_state: str | None = None
    connection_ok: bool | None = None
    last_connection_check_at: datetime | None = None
    last_connection_error: str | None = None
    last_webhook_at: datetime | None = None
    last_webhook_event_type: str | None = None
    last_inbound_message_at: datetime | None = None
    last_outbound_at: datetime | None = None
    last_outbound_error: str | None = None
    last_outbound_error_at: datetime | None = None
    verified_identity_count: int = 0
    pending_verification_count: int = 0
    market_count_with_verified_users: int = 0


class PlatformWhatsAppConnectionTestResponse(BaseModel):
    ok: bool
    state: str | None = None
    detail: str | None = None
    checked_at: datetime


class PlatformWhatsAppMarketRead(BaseModel):
    market_id: UUID
    market_name: str
    market_slug: str
    role: str
    membership_active: bool
    market_active: bool
    market_lifecycle_status: str


class PlatformWhatsAppIdentityRead(BaseModel):
    """One verified (or revoked) identity, with every market it can act for.

    A user belonging to three markets is ONE row with three `markets`
    entries — duplicating the identity per market would misrepresent the
    security model.
    """

    identity_id: UUID
    user_id: UUID
    user_email: str
    user_full_name: str | None = None
    user_is_active: bool
    phone_e164: str
    phone_masked: str
    status: str
    verified_at: datetime | None = None
    last_seen_at: datetime | None = None
    revoked_at: datetime | None = None
    revoked_reason: str | None = None
    markets: list[PlatformWhatsAppMarketRead] = Field(default_factory=list)
