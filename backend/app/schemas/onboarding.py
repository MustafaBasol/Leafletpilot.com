from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator


class OnboardingProfileUpdate(BaseModel):
    display_name: str = Field(min_length=2, max_length=255)
    legal_name: str | None = Field(default=None, max_length=255)
    country_code: str = Field(min_length=2, max_length=2)
    city: str | None = Field(default=None, max_length=120)
    language: str = Field(min_length=2, max_length=16)
    currency: str = Field(min_length=3, max_length=3)
    timezone: str = Field(min_length=3, max_length=64)
    contact_email: str | None = Field(default=None, max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    contact_phone: str | None = Field(default=None, max_length=64)

    @field_validator("country_code")
    @classmethod
    def normalize_country(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        normalized = value.strip()
        try:
            ZoneInfo(normalized)
        except ZoneInfoNotFoundError:
            raise ValueError("Invalid timezone.") from None
        return normalized


class OnboardingBrandUpdate(BaseModel):
    primary_color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    secondary_color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")


class OnboardingTemplateUpdate(BaseModel):
    default_template_id: UUID | None = None


class OnboardingStateRead(BaseModel):
    market_id: UUID
    display_name: str
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
    default_template_id: UUID | None
    onboarding_status: str
    onboarding_step: int
    onboarding_completed_at: datetime | None
