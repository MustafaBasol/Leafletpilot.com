from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.catalog import Product
    from app.models.catalog import MarketProduct
    from app.models.export import CampaignFile, ExportJob
    from app.models.market import Market
    from app.models.messaging import Conversation
    from app.models.template import Template
    from app.models.user import User


CAMPAIGN_STATUSES = (
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
)

CAMPAIGN_CHANNELS = ("panel", "telegram", "whatsapp", "import")
CAMPAIGN_SOURCE_TYPES = ("text", "excel", "pdf", "barcode_list", "manual")
CAMPAIGN_ITEM_MATCH_STATUSES = (
    "matched",
    "low_confidence",
    "not_found",
    "manual_selected",
    "new_product_needed",
    "use_without_image",
    "excluded",
)
MATCHING_SUGGESTION_REASONS = ("exact", "alias", "barcode", "fuzzy", "ai_normalized", "manual")


class Campaign(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "campaigns"
    __table_args__ = (
        CheckConstraint(
            "status in ("
            "'draft', 'parsing', 'matching', 'missing_products', 'preview_ready', "
            "'waiting_approval', 'revision_requested', 'approved', 'generating_files', "
            "'completed', 'failed', 'cancelled')",
            name="ck_campaigns_status",
        ),
        CheckConstraint(
            "channel is null or channel in ('panel', 'telegram', 'whatsapp', 'import')",
            name="ck_campaigns_channel",
        ),
        CheckConstraint(
            "source_type is null or source_type in ('text', 'excel', 'pdf', 'barcode_list', 'manual')",
            name="ck_campaigns_source_type",
        ),
        Index("ix_campaigns_market_id", "market_id"),
        Index("ix_campaigns_status", "status"),
        Index("ix_campaigns_channel", "channel"),
        Index("ix_campaigns_slug", "slug"),
        Index("ix_campaigns_created_at", "created_at"),
        Index("ix_campaigns_updated_at", "updated_at"),
    )

    market_id: Mapped[UUID] = mapped_column(ForeignKey("markets.id"), nullable=False)
    created_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str | None] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    channel: Mapped[str | None] = mapped_column(String(32))
    source_type: Mapped[str | None] = mapped_column(String(32))
    raw_input_text: Mapped[str | None] = mapped_column(Text)
    template_id: Mapped[UUID | None] = mapped_column(ForeignKey("templates.id"))
    # Exact template row is the immutable version reference.  These fields are
    # additive so existing campaigns continue to use template_id/product_id.
    snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    builder_config_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    campaign_start_date: Mapped[date | None]
    campaign_end_date: Mapped[date | None]
    currency: Mapped[str] = mapped_column(String(3), default="EUR", nullable=False)
    language: Mapped[str] = mapped_column(String(16), default="tr", nullable=False)
    product_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    matched_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    missing_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    low_confidence_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(Text)

    market: Mapped[Market] = relationship()
    created_by_user: Mapped[User | None] = relationship()
    template: Mapped[Template | None] = relationship()
    items: Mapped[list[CampaignItem]] = relationship(
        back_populates="campaign",
        cascade="all, delete-orphan",
    )
    files: Mapped[list[CampaignFile]] = relationship(
        back_populates="campaign",
        cascade="all, delete-orphan",
    )
    export_jobs: Mapped[list[ExportJob]] = relationship(
        back_populates="campaign",
        cascade="all, delete-orphan",
    )
    matching_suggestions: Mapped[list[MatchingSuggestion]] = relationship(
        back_populates="campaign",
        cascade="all, delete-orphan",
    )
    conversation: Mapped[Conversation | None] = relationship(back_populates="campaign", uselist=False)

    @property
    def template_name(self) -> str | None:
        return self.template.name if self.template is not None else None


class CampaignItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "campaign_items"
    __table_args__ = (
        CheckConstraint(
            "match_status in ("
            "'matched', 'low_confidence', 'not_found', 'manual_selected', "
            "'new_product_needed', 'use_without_image', 'excluded')",
            name="ck_campaign_items_match_status",
        ),
        Index("ix_campaign_items_campaign_id", "campaign_id"),
        Index("ix_campaign_items_market_id", "market_id"),
        Index("ix_campaign_items_product_id", "product_id"),
        Index("ix_campaign_items_normalized_name", "normalized_name"),
        Index("ix_campaign_items_match_status", "match_status"),
        Index("ix_campaign_items_sort_order", "sort_order"),
    )

    campaign_id: Mapped[UUID] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    market_id: Mapped[UUID] = mapped_column(ForeignKey("markets.id"), nullable=False)
    product_id: Mapped[UUID | None] = mapped_column(ForeignKey("products.id"))
    market_product_id: Mapped[UUID | None] = mapped_column(ForeignKey("market_products.id"))
    raw_line: Mapped[str] = mapped_column(Text, nullable=False)
    incoming_name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str | None] = mapped_column(String(255))
    display_name: Mapped[str | None] = mapped_column(String(255))
    price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    old_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3), default="EUR", nullable=False)
    unit_label: Mapped[str | None] = mapped_column(String(64))
    quantity_label: Mapped[str | None] = mapped_column(String(64))
    category_hint: Mapped[str | None] = mapped_column(String(120))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_hero: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    match_status: Mapped[str] = mapped_column(String(32), default="not_found", nullable=False)
    match_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    matching_notes: Mapped[str | None] = mapped_column(Text)
    parsed_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    campaign: Mapped[Campaign] = relationship(back_populates="items")
    market: Mapped[Market] = relationship()
    product: Mapped[Product | None] = relationship()
    market_product: Mapped[MarketProduct | None] = relationship()
    matching_suggestions: Mapped[list[MatchingSuggestion]] = relationship(
        back_populates="campaign_item",
        cascade="all, delete-orphan",
    )


class MatchingSuggestion(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "matching_suggestions"
    __table_args__ = (
        CheckConstraint(
            "reason is null or reason in ('exact', 'alias', 'barcode', 'fuzzy', 'ai_normalized', 'manual')",
            name="ck_matching_suggestions_reason",
        ),
        Index("ix_matching_suggestions_campaign_id", "campaign_id"),
        Index("ix_matching_suggestions_campaign_item_id", "campaign_item_id"),
        Index("ix_matching_suggestions_market_id", "market_id"),
        Index("ix_matching_suggestions_product_id", "product_id"),
        Index("ix_matching_suggestions_score", "score"),
        Index("ix_matching_suggestions_rank", "rank"),
    )

    campaign_id: Mapped[UUID] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    campaign_item_id: Mapped[UUID] = mapped_column(ForeignKey("campaign_items.id"), nullable=False)
    market_id: Mapped[UUID] = mapped_column(ForeignKey("markets.id"), nullable=False)
    product_id: Mapped[UUID | None] = mapped_column(ForeignKey("products.id"))
    suggested_name: Mapped[str | None] = mapped_column(String(255))
    score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(32))
    rank: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    campaign: Mapped[Campaign] = relationship(back_populates="matching_suggestions")
    campaign_item: Mapped[CampaignItem] = relationship(back_populates="matching_suggestions")
    market: Mapped[Market] = relationship()
    product: Mapped[Product | None] = relationship()
