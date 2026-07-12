from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PlatformCatalogBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    is_active: bool = True


class PlatformCategoryCreate(PlatformCatalogBase):
    slug: str | None = Field(default=None, min_length=1, max_length=120)
    parent_id: UUID | None = None
    color: str | None = Field(default=None, max_length=32)
    icon: str | None = Field(default=None, max_length=64)
    sort_order: int = 0


class PlatformCategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    slug: str | None = Field(default=None, min_length=1, max_length=120)
    parent_id: UUID | None = None
    color: str | None = Field(default=None, max_length=32)
    icon: str | None = Field(default=None, max_length=64)
    sort_order: int | None = None
    is_active: bool | None = None


class PlatformBrandCreate(PlatformCatalogBase):
    slug: str | None = Field(default=None, min_length=1, max_length=120)
    logo_url: str | None = Field(default=None, max_length=1000)


class PlatformBrandUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    slug: str | None = Field(default=None, min_length=1, max_length=120)
    logo_url: str | None = Field(default=None, max_length=1000)
    is_active: bool | None = None


class PlatformCategoryRead(PlatformCategoryCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    market_id: UUID | None
    is_global: bool
    created_at: datetime
    updated_at: datetime
    usage_count: int = 0


class PlatformBrandRead(PlatformBrandCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    market_id: UUID | None
    is_global: bool
    created_at: datetime
    updated_at: datetime
    usage_count: int = 0


class PlatformProductAlias(BaseModel):
    alias: str = Field(min_length=1, max_length=255)
    source: str | None = Field(default="platform", max_length=64)


class PlatformProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    short_name: str | None = Field(default=None, max_length=120)
    barcode: str | None = Field(default=None, max_length=64)
    brand_id: UUID | None = None
    category_id: UUID | None = None
    package_size: str | None = Field(default=None, max_length=64)
    package_type: str | None = Field(default=None, max_length=64)
    sort_order: int = 0
    is_active: bool = True
    quality_score: int | None = Field(default=None, ge=0, le=100)
    aliases: list[PlatformProductAlias] = Field(default_factory=list)


class PlatformProductUpdate(PlatformProductCreate):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    sort_order: int | None = None
    aliases: list[PlatformProductAlias] | None = None


class PlatformProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    market_id: UUID | None
    brand_id: UUID | None
    category_id: UUID | None
    name: str
    short_name: str | None
    barcode: str | None
    package_size: str | None
    package_type: str | None
    sort_order: int
    is_global: bool
    is_active: bool
    quality_score: int | None
    usage_count: int
    aliases: list[dict] = Field(default_factory=list)
    images: list[dict] = Field(default_factory=list)

