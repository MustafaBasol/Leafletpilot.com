from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=256)


class InvitationPreviewRequest(BaseModel):
    token: str = Field(min_length=16, max_length=512)


class InvitationPreviewResponse(BaseModel):
    status: str
    email: str | None = None
    market_name: str | None = None
    role: str | None = None
    expires_at: datetime | None = None
    requires_existing_login: bool = False


class AuthUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AuthMarketRead(BaseModel):
    id: UUID
    name: str
    slug: str
    role: str
    is_active: bool
    lifecycle_status: str = "active"
    onboarding_status: str = "completed"
    onboarding_step: int = 4


class AuthSessionRead(BaseModel):
    user: AuthUserRead
    markets: list[AuthMarketRead]


class LoginResponse(AuthSessionRead):
    access_token: str
    token_type: str = "bearer"
