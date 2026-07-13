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
    category: str | None = Field(default=None, max_length=120)
    minimum_plan: str = Field(default="starter", pattern="^(starter|growth|pro)$")


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
    category: str | None = Field(default=None, max_length=120)
    minimum_plan: str | None = Field(default=None, pattern="^(starter|growth|pro)$")


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
    status: str
    visibility: str
    minimum_plan: str
    category: str | None
    thumbnail_key: str | None
    source_template_id: UUID | None
    source_version: int | None
    version: int
    published_at: datetime | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TemplatePreviewResponse(BaseModel):
    html: str
    template_name: str
    generated_at: datetime


class TemplateAdoptResponse(TemplateRead):
    pass
