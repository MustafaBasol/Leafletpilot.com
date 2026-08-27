from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.campaign import Campaign, CampaignRevision
    from app.models.market import Market
    from app.models.user import User


AI_PROPOSAL_STATUSES = (
    "ready",
    "clarification_required",
    "unsupported",
    "applied",
    "expired",
    "failed",
)
AI_USAGE_STATUSES = ("success", "failed", "timeout")
AI_PROFESSIONALIZATION_STATUSES = ("pending", "generating", "validating", "ready", "applied", "rejected", "superseded", "failed")


class AIRevisionProposal(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Tenant-scoped, immutable AI interpretation awaiting explicit approval."""

    __tablename__ = "ai_revision_proposals"
    __table_args__ = (
        CheckConstraint(f"status in {AI_PROPOSAL_STATUSES}", name="ck_ai_revision_proposals_status"),
        UniqueConstraint(
            "market_id",
            "created_by_user_id",
            "client_request_id",
            name="uq_ai_revision_proposals_market_user_request",
        ),
        Index("ix_ai_revision_proposals_market_campaign", "market_id", "campaign_id"),
        Index("ix_ai_revision_proposals_campaign_status", "campaign_id", "status"),
        Index("ix_ai_revision_proposals_market_created_at", "market_id", "created_at"),
    )

    market_id: Mapped[UUID] = mapped_column(ForeignKey("markets.id"), nullable=False)
    campaign_id: Mapped[UUID] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    client_request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    instruction: Mapped[str] = mapped_column(Text, nullable=False)
    expected_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    capability: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    actions_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    summary_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    clarification_question: Mapped[str | None] = mapped_column(Text)
    unsupported_reason: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revision_id: Mapped[UUID | None] = mapped_column(ForeignKey("campaign_revisions.id"))

    market: Mapped[Market] = relationship()
    campaign: Mapped[Campaign] = relationship()
    created_by_user: Mapped[User] = relationship()
    revision: Mapped[CampaignRevision | None] = relationship()


class AIProfessionalizationRun(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Versioned, tenant-scoped visual plan layered over a frozen snapshot."""

    __tablename__ = "ai_professionalization_runs"
    __table_args__ = (
        CheckConstraint(f"status in {AI_PROFESSIONALIZATION_STATUSES}", name="ck_ai_professionalization_runs_status"),
        UniqueConstraint("market_id", "created_by_user_id", "client_request_id", name="uq_ai_professionalization_runs_market_user_request"),
        Index("ix_ai_professionalization_runs_market_campaign", "market_id", "campaign_id"),
        Index("ix_ai_professionalization_runs_campaign_active", "campaign_id", "is_active"),
        Index("ix_ai_professionalization_runs_market_created_at", "market_id", "created_at"),
    )

    market_id: Mapped[UUID] = mapped_column(ForeignKey("markets.id"), nullable=False)
    campaign_id: Mapped[UUID] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    created_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    client_request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    capability: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ready")
    is_active: Mapped[bool] = mapped_column(nullable=False, default=False)
    request_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="automatic")
    source_image_storage_key: Mapped[str | None] = mapped_column(String(1000))
    logo_storage_key: Mapped[str | None] = mapped_column(String(1000))
    generated_image_storage_key: Mapped[str | None] = mapped_column(String(1000))
    generated_image_file_id: Mapped[UUID | None] = mapped_column(ForeignKey("campaign_files.id"))
    generated_pdf_storage_key: Mapped[str | None] = mapped_column(String(1000))
    validation_report_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(String(64))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    design_goal: Mapped[str | None] = mapped_column(Text)
    plan_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    summary_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    market: Mapped[Market] = relationship()
    campaign: Mapped[Campaign] = relationship(back_populates="professionalization_runs")
    created_by_user: Mapped[User] = relationship()

class AIUsageEvent(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Prompt-free provider usage and failure telemetry."""

    __tablename__ = "ai_usage_events"
    __table_args__ = (
        CheckConstraint(f"status in {AI_USAGE_STATUSES}", name="ck_ai_usage_events_status"),
        Index("ix_ai_usage_events_market_created_at", "market_id", "created_at"),
        Index("ix_ai_usage_events_campaign_id", "campaign_id"),
        Index("ix_ai_usage_events_proposal_id", "proposal_id"),
    )

    market_id: Mapped[UUID] = mapped_column(ForeignKey("markets.id"), nullable=False)
    campaign_id: Mapped[UUID | None] = mapped_column(ForeignKey("campaigns.id"))
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    proposal_id: Mapped[UUID | None] = mapped_column(ForeignKey("ai_revision_proposals.id"))
    capability: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    request_type: Mapped[str] = mapped_column(String(64), nullable=False, default="revision_intent")
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    estimated_cost_minor: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(64))

    market: Mapped[Market] = relationship()
    campaign: Mapped[Campaign | None] = relationship()
    user: Mapped[User | None] = relationship()
    proposal: Mapped[AIRevisionProposal | None] = relationship()
