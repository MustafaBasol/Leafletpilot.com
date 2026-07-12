from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.roles import MARKET_USER_ROLES
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.activity import ActivityLog
    from app.models.catalog import Brand, Category, Product
    from app.models.user import User


class Market(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "markets"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String(255))
    country_code: Mapped[str] = mapped_column(String(2), default="FR", nullable=False)
    city: Mapped[str | None] = mapped_column(String(120))
    logo_url: Mapped[str | None] = mapped_column(String(1000))
    primary_color: Mapped[str | None] = mapped_column(String(32))
    secondary_color: Mapped[str | None] = mapped_column(String(32))
    promo_profile_json: Mapped[dict | None] = mapped_column(JSONB)
    currency: Mapped[str] = mapped_column(String(3), default="EUR", nullable=False)
    language: Mapped[str] = mapped_column(String(16), default="tr", nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Paris", nullable=False)
    contact_email: Mapped[str | None] = mapped_column(String(255))
    contact_phone: Mapped[str | None] = mapped_column(String(64))
    default_template_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("templates.id", name="fk_markets_default_template_id_templates", use_alter=True)
    )
    lifecycle_status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    lifecycle_reason: Mapped[str | None] = mapped_column(String(1000))
    lifecycle_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lifecycle_updated_by_platform_admin_id: Mapped[UUID | None] = mapped_column(ForeignKey("platform_admins.id"))
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    onboarding_status: Mapped[str] = mapped_column(String(32), default="completed", nullable=False)
    onboarding_step: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    users: Mapped[list[MarketUser]] = relationship(
        back_populates="market",
        cascade="save-update, merge",
    )
    brands: Mapped[list[Brand]] = relationship(back_populates="market")
    categories: Mapped[list[Category]] = relationship(back_populates="market")
    products: Mapped[list[Product]] = relationship(back_populates="market")
    activity_logs: Mapped[list[ActivityLog]] = relationship(back_populates="market")


class MarketUser(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "market_users"
    __table_args__ = (
        UniqueConstraint("market_id", "user_id", name="uq_market_users_market_id_user_id"),
        CheckConstraint(
            f"role in {MARKET_USER_ROLES}",
            name="ck_market_users_role",
        ),
        Index("ix_market_users_market_id", "market_id"),
        Index("ix_market_users_user_id", "user_id"),
    )

    market_id: Mapped[UUID] = mapped_column(ForeignKey("markets.id"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    market: Mapped[Market] = relationship(back_populates="users")
    user: Mapped[User] = relationship(back_populates="market_memberships")
