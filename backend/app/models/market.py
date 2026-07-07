from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, String, UniqueConstraint
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
    logo_url: Mapped[str | None] = mapped_column(String(1000))
    primary_color: Mapped[str | None] = mapped_column(String(32))
    secondary_color: Mapped[str | None] = mapped_column(String(32))
    currency: Mapped[str] = mapped_column(String(3), default="EUR", nullable=False)
    language: Mapped[str] = mapped_column(String(16), default="tr", nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Paris", nullable=False)
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
