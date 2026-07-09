from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

SIGNUP_REQUEST_STATUSES = ("pending", "reviewing", "approved", "rejected", "provisioned")


class SignupRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "signup_requests"
    __table_args__ = (
        CheckConstraint(
            "status in ('pending', 'reviewing', 'approved', 'rejected', 'provisioned')",
            name="ck_signup_requests_status",
        ),
        Index("ix_signup_requests_status_created_at", "status", "created_at"),
        Index("ix_signup_requests_email", "email"),
        Index("ix_signup_requests_provisioned_market_id", "provisioned_market_id"),
    )

    market_name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(64))
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    city: Mapped[str | None] = mapped_column(String(120))
    preferred_language: Mapped[str] = mapped_column(String(16), nullable=False)
    expected_campaigns_per_month: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    consent_accepted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    consent_accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    provisioned_market_id: Mapped[UUID | None] = mapped_column(ForeignKey("markets.id"))
    reviewed_by_platform_admin_id: Mapped[UUID | None] = mapped_column(ForeignKey("platform_admins.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provisioned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    provisioned_market = relationship("Market")
    reviewed_by = relationship("PlatformAdmin")


class SignupThrottle(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "signup_throttles"
    __table_args__ = (
        CheckConstraint("key_type in ('ip', 'email')", name="ck_signup_throttles_key_type"),
        UniqueConstraint("key_type", "key_hash", "window_bucket", name="uq_signup_throttles_type_key_bucket"),
        Index("ix_signup_throttles_bucket", "window_bucket"),
    )

    key_type: Mapped[str] = mapped_column(String(16), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    window_bucket: Mapped[int] = mapped_column(Integer, nullable=False)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    request_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
