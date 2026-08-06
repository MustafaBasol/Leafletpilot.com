from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


Color = str


class TemplateConfig(BaseModel):
    """Canonical, forward-compatible configuration shared by editor and renderer."""

    model_config = ConfigDict(extra="allow")

    layout: Literal["promo-4", "promo-6", "promo-9", "promo-12", "promo-16"] = "promo-4"
    columns: int = Field(default=2, ge=1, le=4)
    rows: int = Field(default=2, ge=1, le=4)
    slot_count: int = Field(default=4, ge=1, le=16)
    page_format: Literal["a4_portrait", "a4_landscape"] = "a4_portrait"
    primary_color: Color = Field(default="#c1121f", pattern=r"^#[0-9A-Fa-f]{6}$")
    secondary_color: Color = Field(default="#fffaf0", pattern=r"^#[0-9A-Fa-f]{6}$")
    show_header_title: bool = True
    show_market_name: bool = True
    show_old_price: bool = True
    show_discount_badge: bool = True
    show_product_image: bool = True
    show_product_name: bool = True
    show_package_size: bool = True
    price_style: Literal["bold", "compact", "panel"] = "bold"
    badge_style: Literal["pill", "square", "burst"] = "pill"
    show_footer: bool = True

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_capacity(cls, value):
        if not isinstance(value, dict) or "slot_count" not in value:
            return value
        capacity = int(value["slot_count"])
        grids = {4: ("promo-4", 2, 2), 6: ("promo-6", 2, 3), 9: ("promo-9", 3, 3), 12: ("promo-12", 3, 4), 16: ("promo-16", 4, 4)}
        if capacity not in grids:
            raise ValueError("Ürün kapasitesi 4, 6, 9, 12 veya 16 olmalıdır.")
        layout, columns, rows = grids[capacity]
        normalized = dict(value)
        normalized.setdefault("layout", layout)
        normalized.setdefault("columns", columns)
        normalized.setdefault("rows", rows)
        return normalized

    @model_validator(mode="after")
    def validate_grid(self):
        expected = self.columns * self.rows
        if self.slot_count != expected:
            raise ValueError("Ürün kapasitesi sütun × satır değerine eşit olmalıdır.")
        layout_capacity = int(self.layout.removeprefix("promo-"))
        if layout_capacity != self.slot_count:
            raise ValueError("Düzen ön ayarı ile ürün kapasitesi uyuşmuyor.")
        return self


class TemplateBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str | None = Field(default=None, max_length=120)
    description: str | None = None
    template_type: str = Field(default="market", min_length=1, max_length=64)
    is_global: bool = True
    is_active: bool = True
    config_json: TemplateConfig | None = None
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
    config_json: TemplateConfig | None = None
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
