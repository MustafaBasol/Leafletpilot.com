from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin, utc_now


class PlatformAdmin(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "platform_admins"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PlatformAuditLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "platform_audit_logs"
    __table_args__ = (
        Index("ix_platform_audit_logs_actor_id", "actor_platform_admin_id"),
        Index("ix_platform_audit_logs_target", "target_type", "target_id"),
        Index("ix_platform_audit_logs_created_at", "created_at"),
    )

    actor_platform_admin_id: Mapped[UUID | None] = mapped_column(ForeignKey("platform_admins.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    target_type: Mapped[str] = mapped_column(String(120), nullable=False)
    target_id: Mapped[UUID | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)


class MarketCatalogImport(UUIDPrimaryKeyMixin, Base):
    """Platform-admin controlled market catalog import job (Phase 28D).

    The parsed spreadsheet is never persisted; only the derived preview rows
    are kept (as JSON) so a commit can revalidate against current catalog
    state without re-uploading. ``preview_payload`` is cleared once the job
    reaches a terminal status so old row data doesn't linger indefinitely.
    """

    __tablename__ = "market_catalog_imports"
    __table_args__ = (
        CheckConstraint(
            "status in ('previewed', 'committed', 'expired', 'failed')",
            name="ck_market_catalog_imports_status",
        ),
        Index("ix_market_catalog_imports_market_id", "market_id"),
        Index("ix_market_catalog_imports_status", "status"),
    )

    market_id: Mapped[UUID] = mapped_column(ForeignKey("markets.id"), nullable=False)
    uploaded_by_platform_admin_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("platform_admins.id")
    )
    original_filename: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="previewed", nullable=False)
    total_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    imported_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skipped_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    preview_payload: Mapped[list[Any] | None] = mapped_column(JSONB)
    result_payload: Mapped[list[Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
