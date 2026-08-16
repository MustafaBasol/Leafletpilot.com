from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.services.product_normalization import normalize_currency, normalize_package_type, normalize_package_unit


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
    package_amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=3)
    package_unit: str | None = Field(default=None, max_length=16)
    package_type_canonical: str | None = Field(default=None, max_length=64)

    _canonical_unit = field_validator("package_unit", mode="before")(lambda value: normalize_package_unit(value, strict=value is not None))
    _canonical_type = field_validator("package_type_canonical", mode="before")(lambda value: normalize_package_type(value, strict=value is not None))
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
    package_amount: Decimal | None
    package_unit: str | None
    package_type_canonical: str | None
    sort_order: int
    is_global: bool
    is_active: bool
    quality_score: int | None
    usage_count: int
    aliases: list[dict] = Field(default_factory=list)
    images: list[dict] = Field(default_factory=list)


class PlatformImageIdsPayload(BaseModel):
    image_ids: list[UUID] = Field(min_length=1, max_length=200)


class PlatformBulkImageResolution(BaseModel):
    row_index: int
    product_id: UUID


class PlatformCatalogQualityIgnore(BaseModel):
    product_a_id: UUID
    product_b_id: UUID
    note: str | None = Field(default=None, max_length=1000)


class PlatformCatalogMergePreview(BaseModel):
    source_product_id: UUID
    target_product_id: UUID


class PlatformCatalogMerge(PlatformCatalogMergePreview):
    confirm_barcode_mismatch: bool = False
