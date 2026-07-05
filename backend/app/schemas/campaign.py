from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


CampaignStatus = Literal[
    "draft",
    "parsing",
    "matching",
    "missing_products",
    "preview_ready",
    "waiting_approval",
    "revision_requested",
    "approved",
    "generating_files",
    "completed",
    "failed",
    "cancelled",
]
CampaignChannel = Literal["panel", "telegram", "whatsapp", "import"]
CampaignSourceType = Literal["text", "excel", "pdf", "barcode_list", "manual"]
CampaignItemMatchStatus = Literal[
    "matched",
    "low_confidence",
    "not_found",
    "manual_selected",
    "new_product_needed",
    "use_without_image",
    "excluded",
]
MatchResolution = Literal[
    "manual_selected",
    "new_product_needed",
    "use_without_image",
    "excluded",
    "not_found",
]
MatchingSuggestionReason = Literal["exact", "alias", "barcode", "fuzzy", "ai_normalized", "manual"]
RAW_TEXT_MAX_LENGTH = 20_000


class CampaignItemCreate(BaseModel):
    raw_line: str = Field(min_length=1)
    incoming_name: str = Field(min_length=1, max_length=255)
    display_name: str | None = Field(default=None, max_length=255)
    price: Decimal | None = Field(default=None, max_digits=10, decimal_places=2)
    old_price: Decimal | None = Field(default=None, max_digits=10, decimal_places=2)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    unit_label: str | None = Field(default=None, max_length=64)
    quantity_label: str | None = Field(default=None, max_length=64)
    category_hint: str | None = Field(default=None, max_length=120)
    sort_order: int = 0
    is_hero: bool = False
    parsed_payload: dict[str, Any] | None = None


class CampaignItemUpdate(BaseModel):
    incoming_name: str | None = Field(default=None, min_length=1, max_length=255)
    display_name: str | None = Field(default=None, max_length=255)
    price: Decimal | None = Field(default=None, max_digits=10, decimal_places=2)
    old_price: Decimal | None = Field(default=None, max_digits=10, decimal_places=2)
    product_id: UUID | None = None
    category_hint: str | None = Field(default=None, max_length=120)
    sort_order: int | None = None
    is_hero: bool | None = None
    match_status: CampaignItemMatchStatus | None = None
    match_confidence: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)
    matching_notes: str | None = None


class CampaignItemResolveMatch(BaseModel):
    resolution: MatchResolution
    product_id: UUID | None = None
    display_name: str | None = Field(default=None, max_length=255)
    notes: str | None = None


class CampaignItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    campaign_id: UUID
    market_id: UUID
    product_id: UUID | None
    raw_line: str
    incoming_name: str
    normalized_name: str | None
    display_name: str | None
    price: Decimal | None
    old_price: Decimal | None
    currency: str
    unit_label: str | None
    quantity_label: str | None
    category_hint: str | None
    sort_order: int
    is_hero: bool
    match_status: str
    match_confidence: Decimal | None
    matching_notes: str | None
    parsed_payload: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class MatchingSuggestionCreate(BaseModel):
    product_id: UUID | None = None
    suggested_name: str | None = Field(default=None, max_length=255)
    score: Decimal = Field(ge=0, le=100, max_digits=5, decimal_places=2)
    reason: MatchingSuggestionReason | None = None
    rank: int = 0


class MatchingSuggestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    campaign_id: UUID
    campaign_item_id: UUID
    market_id: UUID
    product_id: UUID | None
    suggested_name: str | None
    score: Decimal
    reason: str | None
    rank: int
    accepted_at: datetime | None
    rejected_at: datetime | None
    created_at: datetime


class GenerateItemSuggestionsRequest(BaseModel):
    limit: int = Field(default=5, ge=1, le=20)


class GenerateCampaignSuggestionsRequest(BaseModel):
    limit_per_item: int = Field(default=5, ge=1, le=20)


class CampaignItemSuggestionResult(BaseModel):
    item: CampaignItemRead
    suggestions: list[MatchingSuggestionRead] = Field(default_factory=list)


class CampaignSuggestionSummary(BaseModel):
    campaign_id: UUID
    items_processed: int
    auto_matched: int
    low_confidence: int
    not_found: int
    suggestions_created: int


class CampaignParseRequest(BaseModel):
    raw_text: str = Field(default="", max_length=RAW_TEXT_MAX_LENGTH)
    default_currency: str = Field(default="EUR", min_length=3, max_length=3)


class ParsedCampaignLineRead(BaseModel):
    raw_line: str
    incoming_name: str
    display_name: str
    price: Decimal | None
    old_price: Decimal | None
    currency: str
    unit_label: str | None = None
    quantity_label: str | None = None
    category_hint: str | None = None
    sort_order: int
    parsed_payload: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class CampaignParseResponse(BaseModel):
    items: list[ParsedCampaignLineRead]
    total_lines: int
    parsed_count: int
    warning_count: int


class CampaignCreateFromTextRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    raw_text: str = Field(min_length=1, max_length=RAW_TEXT_MAX_LENGTH)
    channel: CampaignChannel = "panel"
    source_type: CampaignSourceType = "text"
    template_id: UUID | None = None
    campaign_start_date: date | None = None
    campaign_end_date: date | None = None
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    language: str = Field(default="tr", min_length=2, max_length=16)
    generate_suggestions: bool = True
    suggestion_limit: int = Field(default=5, ge=1, le=20)


class CampaignCreateFromTextResponse(BaseModel):
    campaign_id: UUID
    product_count: int
    matched_count: int
    missing_count: int
    low_confidence_count: int
    parsed_count: int
    warning_count: int
    suggestions_created: int = 0
    campaign: "CampaignDetail"


class CampaignCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    channel: CampaignChannel = "panel"
    source_type: CampaignSourceType = "manual"
    raw_input_text: str | None = None
    template_id: UUID | None = None
    campaign_start_date: date | None = None
    campaign_end_date: date | None = None
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    language: str = Field(default="tr", min_length=2, max_length=16)
    items: list[CampaignItemCreate] = Field(default_factory=list)


class CampaignUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    status: CampaignStatus | None = None
    channel: CampaignChannel | None = None
    source_type: CampaignSourceType | None = None
    raw_input_text: str | None = None
    template_id: UUID | None = None
    campaign_start_date: date | None = None
    campaign_end_date: date | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    language: str | None = Field(default=None, min_length=2, max_length=16)
    failure_reason: str | None = None


class CampaignListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    market_id: UUID
    title: str
    status: str
    channel: str | None
    source_type: str | None
    template_id: UUID | None = None
    template_name: str | None = None
    product_count: int
    matched_count: int
    missing_count: int
    low_confidence_count: int
    campaign_start_date: date | None
    campaign_end_date: date | None
    currency: str
    language: str
    created_at: datetime
    updated_at: datetime


class CampaignDetail(CampaignListItem):
    slug: str | None
    raw_input_text: str | None
    approved_at: datetime | None
    completed_at: datetime | None
    failed_at: datetime | None
    failure_reason: str | None
    items: list[CampaignItemRead] = Field(default_factory=list)
    files: list["CampaignFileRead"] = Field(default_factory=list)
    export_jobs: list["ExportJobRead"] = Field(default_factory=list)
    matching_suggestions: list[MatchingSuggestionRead] = Field(default_factory=list)


class CampaignPreviewHtml(BaseModel):
    campaign_id: UUID
    template_id: UUID | None = None
    template_name: str
    html: str
    generated_at: datetime


from app.schemas.export import CampaignFileRead, ExportJobRead  # noqa: E402

CampaignDetail.model_rebuild()
CampaignCreateFromTextResponse.model_rebuild()
