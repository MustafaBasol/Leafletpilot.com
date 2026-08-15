from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic import field_validator
from app.services.product_normalization import normalize_currency, normalize_package_type, normalize_package_unit


class ProductAliasCreate(BaseModel):
    alias: str = Field(min_length=1, max_length=255)
    source: str | None = Field(default=None, max_length=64)


class ProductAliasRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_id: UUID
    alias: str
    normalized_alias: str
    source: str | None
    created_at: datetime


class ProductImageCreate(BaseModel):
    storage_key: str | None = Field(default=None, max_length=1000)
    url: str | None = Field(default=None, max_length=1000)
    image_type: str = Field(default="main", max_length=32)
    mime_type: str | None = Field(default=None, max_length=100)
    size_bytes: int | None = Field(default=None, ge=0)
    width: int | None = Field(default=None, ge=0)
    height: int | None = Field(default=None, ge=0)
    has_transparent_background: bool | None = None
    quality_status: str = Field(default="needs_review", max_length=32)
    is_primary: bool = False


class ProductImageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_id: UUID
    storage_key: str | None
    url: str | None
    image_type: str
    mime_type: str | None
    size_bytes: int | None
    width: int | None
    height: int | None
    has_transparent_background: bool | None
    quality_status: str
    is_primary: bool
    created_at: datetime


class ProductBase(BaseModel):
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
    regular_price: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    promo_price: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    sort_order: int = 0
    badge_text: str | None = Field(default=None, max_length=64)
    is_global: bool = False
    is_active: bool = True
    quality_score: int | None = Field(default=None, ge=0, le=100)

    @field_validator("currency", mode="before")
    @classmethod
    def canonical_currency(cls, value): return normalize_currency(value, strict=value is not None)

    @field_validator("package_type_canonical", mode="before")
    @classmethod
    def canonical_type(cls, value): return normalize_package_type(value, strict=value is not None)

    @field_validator("package_unit", mode="before")
    @classmethod
    def canonical_unit(cls, value): return normalize_package_unit(value, strict=value is not None)


class ProductCreate(ProductBase):
    aliases: list[str | ProductAliasCreate] = Field(default_factory=list)
    images: list[ProductImageCreate] = Field(default_factory=list)


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    short_name: str | None = Field(default=None, max_length=120)
    barcode: str | None = Field(default=None, max_length=64)
    brand_id: UUID | None = None
    category_id: UUID | None = None
    package_size: str | None = Field(default=None, max_length=64)
    package_type: str | None = Field(default=None, max_length=64)
    package_amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=3)
    package_unit: str | None = Field(default=None, max_length=16)
    package_type_canonical: str | None = Field(default=None, max_length=64)
    regular_price: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    promo_price: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    currency: str | None = Field(default=None, min_length=3, max_length=3)

    @field_validator("currency", mode="before")
    @classmethod
    def canonical_currency(cls, value): return normalize_currency(value, strict=value is not None)

    @field_validator("package_unit", mode="before")
    @classmethod
    def canonical_unit(cls, value): return normalize_package_unit(value, strict=value is not None)

    @field_validator("package_type_canonical", mode="before")
    @classmethod
    def canonical_type(cls, value): return normalize_package_type(value, strict=value is not None)
    sort_order: int | None = None
    badge_text: str | None = Field(default=None, max_length=64)
    is_active: bool | None = None
    quality_score: int | None = Field(default=None, ge=0, le=100)


class ProductRead(BaseModel):
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
    regular_price: Decimal | None
    promo_price: Decimal | None
    currency: str
    sort_order: int
    badge_text: str | None
    is_global: bool
    is_active: bool
    quality_score: int | None
    usage_count: int
    last_used_at: datetime | None
    created_at: datetime
    updated_at: datetime
    aliases: list[ProductAliasRead] = Field(default_factory=list)
    images: list[ProductImageRead] = Field(default_factory=list)
