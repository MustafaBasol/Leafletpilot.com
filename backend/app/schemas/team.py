from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.roles import MARKET_USER_ROLES


class MarketMemberRead(BaseModel):
    membership_id: UUID
    user_id: UUID
    email: str
    full_name: str | None
    role: str
    is_active: bool
    created_at: datetime


class MarketMemberUpdate(BaseModel):
    role: str = Field(pattern=f"^({'|'.join(MARKET_USER_ROLES)})$")


class MarketInvitationCreate(BaseModel):
    email: str = Field(min_length=3, max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    role: str = Field(pattern=f"^({'|'.join(MARKET_USER_ROLES)})$")


class MarketInvitationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    role: str
    status: str
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class MarketInvitationCreateResponse(MarketInvitationRead):
    invite_token: str
    accept_url: str


class AcceptInvitationRequest(BaseModel):
    token: str = Field(min_length=16, max_length=512)
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=256)


class AcceptInvitationAuthenticatedRequest(BaseModel):
    token: str = Field(min_length=16, max_length=512)
