from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator


Color = str
GridPreset = Literal["promo-4", "promo-6", "promo-9", "promo-12", "promo-16"]

GRID_PRESETS: dict[int, tuple[GridPreset, int, int]] = {
    4: ("promo-4", 2, 2),
    6: ("promo-6", 2, 3),
    9: ("promo-9", 3, 3),
    12: ("promo-12", 3, 4),
    16: ("promo-16", 4, 4),
}


class TemplateConfig(BaseModel):
    """Canonical, forward-compatible configuration shared by editor and renderer."""

    model_config = ConfigDict(extra="allow")

    # `layout` is the renderer/template family. It deliberately remains open so
    # persisted families continue to round-trip as new renderers are introduced.
    layout: str = Field(default="promo-4", min_length=1)
    grid_preset: GridPreset | None = None
    columns: int = Field(default=2, ge=1, le=4)
    rows: int = Field(default=2, ge=1, le=4)
    slot_count: int = Field(default=4, ge=1, le=16)
    page_format: Literal["a4_portrait", "a4_landscape"] = "a4_portrait"
    primary_color: Color = Field(default="#c1121f", pattern=r"^#[0-9A-Fa-f]{6}$")
    secondary_color: Color = Field(default="#fffaf0", pattern=r"^#[0-9A-Fa-f]{6}$")
    background_start: Color | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    background_end: Color | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    card_background: Color | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    card_border_color: Color | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    price_panel_background: Color | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    price_color: Color | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    title_color: Color | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    product_title_color: Color | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    brand_label_background: Color | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    brand_label_color: Color | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    show_header_title: bool = True
    show_market_name: bool = True
    show_old_price: bool = True
    show_discount_badge: bool = True
    show_product_image: bool = True
    show_product_name: bool = True
    show_package_size: bool = True
    header_style: Literal["burst", "band", "minimal"] = "burst"
    card_style: Literal["shadow", "outlined", "rounded"] = "shadow"
    price_style: Literal["bold", "compact", "panel", "ticket", "split"] = "bold"
    badge_style: Literal["pill", "square", "sticker", "burst", "ribbon"] = "pill"
    image_treatment: Literal["stage", "cutout", "photo"] = "stage"
    show_footer: bool = True
    show_payment_icons: bool = True
    show_additional_logos: bool = True
    show_stock_message: bool = True
    show_footer_note: bool = True

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_capacity(cls, value):
        if not isinstance(value, dict):
            return value

        normalized = dict(value)
        layout = normalized.get("layout")
        preset = normalized.get("grid_preset")
        if preset is None and layout in {grid[0] for grid in GRID_PRESETS.values()}:
            preset = layout
        if preset is None and layout in {"supermarket-promo-4", "supermarket-promo-9", "supermarket-promo-16"}:
            preset = layout.removeprefix("supermarket-")
        if preset is not None:
            normalized.setdefault("grid_preset", preset)

        capacity = normalized.get("slot_count")
        if capacity is None and preset is not None:
            capacity = int(str(preset).removeprefix("promo-"))
            normalized["slot_count"] = capacity
        if capacity is None:
            return normalized
        capacity = int(capacity)
        if capacity not in GRID_PRESETS:
            raise ValueError("Ürün kapasitesi 4, 6, 9, 12 veya 16 olmalıdır.")
        canonical_preset, columns, rows = GRID_PRESETS[capacity]
        normalized.setdefault("layout", canonical_preset)
        normalized.setdefault("grid_preset", canonical_preset)
        normalized.setdefault("columns", columns)
        normalized.setdefault("rows", rows)
        return normalized

    @model_validator(mode="after")
    def validate_grid(self):
        expected = self.columns * self.rows
        if self.slot_count != expected:
            raise ValueError("Ürün kapasitesi sütun × satır değerine eşit olmalıdır.")
        canonical_layouts = {grid[0] for grid in GRID_PRESETS.values()}
        preset = self.grid_preset or (self.layout if self.layout in canonical_layouts else None)
        if preset is not None and int(preset.removeprefix("promo-")) != self.slot_count:
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
    minimum_plan: str = Field(default="starter", pattern="^(starter|standard|growth|pro)$")


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
    minimum_plan: str | None = Field(default=None, pattern="^(starter|standard|growth|pro)$")


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

    @computed_field
    @property
    def ideal_product_min(self) -> int:
        from app.services.template_gallery import suitability_for_template
        return suitability_for_template(self.slug, self.config_json).minimum

    @computed_field
    @property
    def ideal_product_max(self) -> int:
        from app.services.template_gallery import suitability_for_template
        return suitability_for_template(self.slug, self.config_json).maximum

    @computed_field
    @property
    def user_description(self) -> str:
        from app.services.template_gallery import suitability_for_template
        return suitability_for_template(self.slug, self.config_json).description

    @computed_field
    @property
    def display_category(self) -> str:
        from app.services.template_gallery import suitability_for_template
        return suitability_for_template(self.slug, self.config_json).category


class TemplatePreviewResponse(BaseModel):
    html: str
    template_name: str
    generated_at: datetime


class TemplateAdoptResponse(TemplateRead):
    pass
