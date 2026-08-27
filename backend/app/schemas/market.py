from __future__ import annotations

import re
from urllib.parse import urlparse
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_TEXT_LIMITS = {
    "address_line_1": 255, "address_line_2": 255, "postal_code": 32,
    "city": 120, "phone": 64,
}


def _clean(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if len(value) > limit:
        raise ValueError(f"Must be at most {limit} characters.")
    return value


def _http_url(value: str | None) -> str | None:
    value = _clean(value, 500)
    if value is None:
        return None
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Must be a valid http/https URL.")
    return value


class BrochurePreferences(BaseModel):
    show_logo: bool = True
    show_address: bool = False
    show_phone: bool = False
    show_website: bool = False
    show_instagram: bool = False
    show_facebook: bool = False


class MarketSettingsUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    address_line_1: str | None = Field(default=None, max_length=255)
    address_line_2: str | None = Field(default=None, max_length=255)
    postal_code: str | None = Field(default=None, max_length=32)
    city: str | None = Field(default=None, max_length=120)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    phone: str | None = Field(default=None, max_length=64)
    website_url: str | None = Field(default=None, max_length=500)
    instagram_url: str | None = Field(default=None, max_length=500)
    facebook_url: str | None = Field(default=None, max_length=500)
    brochure_preferences: BrochurePreferences | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        return _clean(value, 255)

    @model_validator(mode="after")
    def require_name_when_updated(self):
        if "name" in self.model_fields_set and not self.name:
            raise ValueError("Market name is required.")
        return self

    @field_validator(*_TEXT_LIMITS)
    @classmethod
    def validate_text(cls, value: str | None, info) -> str | None:
        value = _clean(value, _TEXT_LIMITS[info.field_name])
        if info.field_name == "phone" and value and not re.fullmatch(r"[0-9+().\\-\\s]{3,64}", value):
            raise ValueError("Phone contains unsupported characters.")
        return value

    @field_validator("country_code")
    @classmethod
    def normalize_country(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else None

    @field_validator("website_url")
    @classmethod
    def validate_website(cls, value: str | None) -> str | None:
        return _http_url(value)

    @field_validator("instagram_url", "facebook_url")
    @classmethod
    def validate_social(cls, value: str | None) -> str | None:
        value = _clean(value, 500)
        if value is None or re.fullmatch(r"@?[A-Za-z0-9._-]{1,100}", value):
            return value
        return _http_url(value)


class MarketSettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    address_line_1: str | None = None
    address_line_2: str | None = None
    postal_code: str | None = None
    city: str | None = None
    country_code: str
    phone: str | None = None
    website_url: str | None = None
    instagram_url: str | None = None
    facebook_url: str | None = None
    brochure_preferences: BrochurePreferences
    has_logo: bool
    logo_mime_type: str | None = None