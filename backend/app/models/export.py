from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.campaign import Campaign
    from app.models.market import Market
    from app.models.user import User


CAMPAIGN_FILE_TYPES = (
    "preview_png",
    "brochure_pdf",
    "brochure_png",
    "instagram_post",
    "instagram_story",
    "whatsapp_image",
    "source_upload",
)
CAMPAIGN_FILE_STATUSES = ("pending", "generating", "ready", "failed", "sent")
EXPORT_JOB_TYPES = ("preview", "final_export", "regenerate_preview", "send_files")
EXPORT_JOB_STATUSES = ("queued", "running", "completed", "failed", "cancelled")


class CampaignFile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "campaign_files"
    __table_args__ = (
        CheckConstraint(
            "file_type in ("
            "'preview_png', 'brochure_pdf', 'brochure_png', 'instagram_post', "
            "'instagram_story', 'whatsapp_image', 'source_upload')",
            name="ck_campaign_files_file_type",
        ),
        CheckConstraint(
            "status in ('pending', 'generating', 'ready', 'failed', 'sent')",
            name="ck_campaign_files_status",
        ),
        Index("ix_campaign_files_campaign_id", "campaign_id"),
        Index("ix_campaign_files_market_id", "market_id"),
        Index("ix_campaign_files_file_type", "file_type"),
        Index("ix_campaign_files_status", "status"),
        Index("ix_campaign_files_created_at", "created_at"),
    )

    campaign_id: Mapped[UUID] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    market_id: Mapped[UUID] = mapped_column(ForeignKey("markets.id"), nullable=False)
    file_type: Mapped[str] = mapped_column(String(32), nullable=False)
    format: Mapped[str | None] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(1000))
    url: Mapped[str | None] = mapped_column(String(1000))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    page_number: Mapped[int | None] = mapped_column(Integer)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    sent_to_user_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)

    campaign: Mapped[Campaign] = relationship(back_populates="files")
    market: Mapped[Market] = relationship()


class ExportJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "export_jobs"
    __table_args__ = (
        CheckConstraint(
            "job_type in ('preview', 'final_export', 'regenerate_preview', 'send_files')",
            name="ck_export_jobs_job_type",
        ),
        CheckConstraint(
            "status in ('queued', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_export_jobs_status",
        ),
        Index("ix_export_jobs_campaign_id", "campaign_id"),
        Index("ix_export_jobs_market_id", "market_id"),
        Index("ix_export_jobs_status", "status"),
        Index("ix_export_jobs_job_type", "job_type"),
        Index("ix_export_jobs_created_at", "created_at"),
    )

    campaign_id: Mapped[UUID] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    market_id: Mapped[UUID] = mapped_column(ForeignKey("markets.id"), nullable=False)
    requested_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    job_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    requested_formats: Mapped[list[str] | None] = mapped_column(JSONB)
    result_file_ids: Mapped[list[str] | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    campaign: Mapped[Campaign] = relationship(back_populates="export_jobs")
    market: Mapped[Market] = relationship()
    requested_by_user: Mapped[User | None] = relationship()
