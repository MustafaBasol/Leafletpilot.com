from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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


class MarketProductAdoptCreate(MarketProductBase):
    product_id: UUID


class PrivateMarketProductCreate(MarketProductBase):
    private_name: str = Field(min_length=1, max_length=255)


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
    pass


class ResolvedMarketProductRead(BaseModel):
    id: UUID
    market_id: UUID
    product_id: UUID | None
    name: str
    brand: str | None
    category: str | None
    package_size: str | None
    package_type: str | None
    regular_price: Decimal | None
    promo_price: Decimal | None
    currency: str
    badge_text: str | None
    stock_note: str | None
    sort_order: int
    is_active: bool
    source_type: str
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
