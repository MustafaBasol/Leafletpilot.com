from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.product_normalization import (
    normalize_currency,
    normalize_package_type,
    normalize_package_unit,
)


class MarketProductBase(BaseModel):
    regular_price: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    promo_price: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    display_name_override: str | None = Field(default=None, max_length=255)
    category_override_id: UUID | None = None
    badge_text: str | None = Field(default=None, max_length=64)
    stock_note: str | None = Field(default=None, max_length=255)
    sort_order: int = 0
    is_active: bool = True
    private_brand_text: str | None = Field(default=None, max_length=255)
    private_barcode: str | None = Field(default=None, max_length=64)
    private_sku: str | None = Field(default=None, max_length=64)
    private_package_size: str | None = Field(default=None, max_length=64)
    private_package_type: str | None = Field(default=None, max_length=64)
    package_amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=3)
    package_unit: str | None = Field(default=None, max_length=16)
    package_type_canonical: str | None = Field(default=None, max_length=64)

    _canonical_currency = field_validator("currency", mode="before")(lambda value: normalize_currency(value, strict=value is not None))
    _canonical_unit = field_validator("package_unit", mode="before")(lambda value: normalize_package_unit(value, strict=value is not None))
    _canonical_type = field_validator("package_type_canonical", mode="before")(lambda value: normalize_package_type(value, strict=value is not None))


class MarketProductAdoptCreate(MarketProductBase):
    product_id: UUID


class PrivateMarketProductCreate(MarketProductBase):
    private_name: str = Field(min_length=1, max_length=255)
    allow_global_match_override: bool = False


class MarketProductRead(MarketProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    market_id: UUID
    product_id: UUID | None
    legacy_product_id: UUID | None
    private_name: str | None
    image_storage_key: str | None
    image_url: str | None
    image_mime_type: str | None
    image_quality_status: str | None
    created_at: datetime
    updated_at: datetime


class MarketProductUpdate(MarketProductBase):
    private_name: str | None = Field(default=None, min_length=1, max_length=255)


class ResolvedMarketProductRead(BaseModel):
    id: UUID
    market_id: UUID
    product_id: UUID | None
    name: str
    brand: str | None
    category: str | None
    package_size: str | None
    package_type: str | None
    package_amount: Decimal | None = None
    package_unit: str | None = None
    package_type_canonical: str | None = None
    regular_price: Decimal | None
    promo_price: Decimal | None
    currency: str
    badge_text: str | None
    stock_note: str | None
    sort_order: int
    is_active: bool
    source_type: str
    source_state: Literal["global", "local", "global_override"]
    global_product_id: UUID | None
    inherited_values: dict[str, Any]
    override_values: dict[str, Any]
    image_url: str | None
    image_override_active: bool
    promo_active: bool


class SharedCatalogProductRead(BaseModel):
    id: UUID
    name: str
    brand: str | None
    package_size: str | None
    package_type: str | None
    barcode: str | None
    sku: str | None = None
    category: str | None
    image_url: str | None
    is_active: bool
    already_added: bool


class CatalogProductMatchRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    barcode: str | None = Field(default=None, max_length=64)
    brand: str | None = Field(default=None, max_length=255)
    brand_id: UUID | None = None
    package_size: str | None = Field(default=None, max_length=64)
    package_type: str | None = Field(default=None, max_length=64)
    package_amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=3)
    package_unit: str | None = Field(default=None, max_length=16)
    package_type_canonical: str | None = Field(default=None, max_length=64)

    _canonical_unit = field_validator("package_unit", mode="before")(
        lambda value: normalize_package_unit(value, strict=value is not None)
    )
    _canonical_type = field_validator("package_type_canonical", mode="before")(
        lambda value: normalize_package_type(value, strict=value is not None)
    )


class CatalogProductMatchCandidate(BaseModel):
    product_id: UUID
    name: str
    brand: str | None
    package_size: str | None
    package_type: str | None
    package_amount: Decimal | None
    package_unit: str | None
    package_type_canonical: str | None
    image_url: str | None
    match_type: Literal["exact", "strong"]
    match_reason: str
    already_adopted: bool


class CatalogProductMatchResponse(BaseModel):
    match_type: Literal["exact", "strong", "none", "ambiguous"]
    match_reason: str
    candidate_count: int = Field(ge=0)
    candidates: list[CatalogProductMatchCandidate]


class MarketProductLinkGlobalRequest(BaseModel):
    product_id: UUID
