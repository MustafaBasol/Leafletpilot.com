from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


def normalize_email(value: str) -> str:
    return value.strip().lower()


class PlatformLoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def normalize(cls, value: str) -> str:
        return normalize_email(value)


class PlatformAdminRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: str
    is_active: bool
    last_login_at: datetime | None


class PlatformLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    admin: PlatformAdminRead


class PublicSignupRequestCreate(BaseModel):
    market_name: str = Field(min_length=2, max_length=255)
    contact_name: str = Field(min_length=2, max_length=255)
    email: str = Field(min_length=3, max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    phone: str | None = Field(default=None, max_length=64)
    country_code: str = Field(min_length=2, max_length=2)
    city: str | None = Field(default=None, max_length=120)
    preferred_language: str = Field(default="tr", min_length=2, max_length=16)
    expected_campaigns_per_month: int | None = Field(default=None, ge=0, le=1000)
    notes: str | None = Field(default=None, max_length=2000)
    consent_accepted: bool
    website: str | None = Field(default=None, max_length=255)

    @field_validator("email")
    @classmethod
    def normalize_signup_email(cls, value: str) -> str:
        return normalize_email(value)

    @field_validator("country_code")
    @classmethod
    def normalize_country(cls, value: str) -> str:
        return value.strip().upper()


class PublicSignupAccepted(BaseModel):
    status: str = "accepted"
    message: str = "Başvurunuz alındı. Ekibimiz sizinle iletişime geçecek."


class SignupRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    market_name: str
    contact_name: str
    email: str
    phone: str | None
    country_code: str
    city: str | None
    preferred_language: str
    expected_campaigns_per_month: int | None
    notes: str | None
    consent_accepted: bool
    status: str
    review_notes: str | None
    rejection_reason: str | None
    provisioned_market_id: UUID | None
    reviewed_by_platform_admin_id: UUID | None
    reviewed_at: datetime | None
    provisioned_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SignupRequestUpdate(BaseModel):
    status: str = Field(pattern="^(reviewing|approved|rejected)$")
    review_notes: str | None = Field(default=None, max_length=2000)
    rejection_reason: str | None = Field(default=None, max_length=2000)


class ProvisionMarketRequest(BaseModel):
    final_market_name: str = Field(min_length=2, max_length=255)
    requested_slug: str | None = Field(default=None, max_length=120, pattern=r"^[a-z0-9-]+$")
    country_code: str = Field(min_length=2, max_length=2)
    preferred_language: str = Field(default="tr", min_length=2, max_length=16)
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    timezone: str = Field(default="Europe/Paris", min_length=3, max_length=64)
    trial_length_days: int = Field(default=14, ge=1, le=90)

    @field_validator("country_code")
    @classmethod
    def normalize_provision_country(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.strip().upper()


class ProvisionMarketResponse(BaseModel):
    signup_request: SignupRequestRead
    market_id: UUID
    accept_url: str | None = None
    already_provisioned: bool = False


class PlatformInvitationSummary(BaseModel):
    id: UUID
    email: str
    role: str
    status: str
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None
    last_sent_at: datetime | None = None
    send_count: int = 0
    created_at: datetime
    delivery_status: str = "pending"
    last_send_error: str | None = None
    is_effective: bool = False


class PlatformReadinessSummary(BaseModel):
    state: str
    blockers: list[str] = Field(default_factory=list)
    has_active_market_user: bool
    required_setup_complete: bool
    last_activity_at: datetime | None = None


class PlatformAuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    actor_platform_admin_id: UUID | None
    action: str
    target_type: str
    target_id: UUID | None
    created_at: datetime
    metadata_: dict | None = Field(default=None, serialization_alias="metadata")


class PlatformMarketListItem(BaseModel):
    id: UUID
    name: str
    slug: str
    lifecycle_status: str
    trial_ends_at: datetime | None
    onboarding_status: str
    member_count: int
    product_count: int
    campaign_count: int
    readiness: PlatformReadinessSummary
    owner_invitation: PlatformInvitationSummary | None = None
    created_at: datetime


class PlatformMarketDetail(PlatformMarketListItem):
    legal_name: str | None
    country_code: str
    city: str | None
    language: str
    currency: str
    timezone: str
    contact_email: str | None
    contact_phone: str | None
    primary_color: str | None
    secondary_color: str | None
    onboarding_step: int
    onboarding_completed_at: datetime | None
    lifecycle_reason: str | None
    lifecycle_updated_at: datetime | None
    lifecycle_updated_by_platform_admin_id: UUID | None
    recent_activity: list[PlatformAuditLogRead] = Field(default_factory=list)


class LifecycleUpdateRequest(BaseModel):
    lifecycle_status: str = Field(pattern="^(active|suspended|archived)$")
    confirm_archive: bool = False
    reason: str | None = Field(default=None, max_length=1000)


class OwnerInvitationActionRequest(BaseModel):
    email: str | None = Field(default=None, max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

    @field_validator("email")
    @classmethod
    def normalize_optional_email(cls, value: str | None) -> str | None:
        return normalize_email(value) if value else None


class OwnerInvitationActionResponse(BaseModel):
    invitation: PlatformInvitationSummary
    accept_url: str | None = None


class PlatformOverview(BaseModel):
    pending_signup_count: int
    markets_awaiting_owner: int
    markets_onboarding: int
    ready_markets: int
    suspended_markets: int
    recent_activity: list[PlatformAuditLogRead]
