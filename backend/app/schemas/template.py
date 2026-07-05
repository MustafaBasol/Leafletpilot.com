from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TemplateBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str | None = Field(default=None, max_length=120)
    description: str | None = None
    template_type: str = Field(default="market", min_length=1, max_length=64)
    is_global: bool = True
    is_active: bool = True
    config_json: dict[str, Any] | None = None


class TemplateCreate(TemplateBase):
    pass


class TemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    slug: str | None = Field(default=None, max_length=120)
    description: str | None = None
    template_type: str | None = Field(default=None, min_length=1, max_length=64)
    is_global: bool | None = None
    is_active: bool | None = None
    config_json: dict[str, Any] | None = None


class TemplateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    market_id: UUID | None
    name: str
    slug: str
    description: str | None
    template_type: str
    is_global: bool
    is_active: bool
    config_json: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
