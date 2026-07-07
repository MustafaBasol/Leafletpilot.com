from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.roles import MARKET_USER_ROLES
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.market import Market
    from app.models.user import User


INVITATION_STATUSES = ("pending", "accepted", "revoked", "expired")


class MarketInvitation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "market_invitations"
    __table_args__ = (
        CheckConstraint(
            f"role in {MARKET_USER_ROLES}",
            name="ck_market_invitations_role",
        ),
        CheckConstraint(
            "status in ('pending', 'accepted', 'revoked', 'expired')",
            name="ck_market_invitations_status",
        ),
        Index(
            "uq_market_invitations_pending_market_email",
            "market_id",
            "email",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index("ix_market_invitations_market_id", "market_id"),
        Index("ix_market_invitations_token_hash", "token_hash"),
    )

    market_id: Mapped[UUID] = mapped_column(ForeignKey("markets.id"), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    accepted_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    market: Mapped[Market] = relationship()
    created_by: Mapped[User] = relationship(foreign_keys=[created_by_user_id])
    accepted_by: Mapped[User | None] = relationship(foreign_keys=[accepted_by_user_id])
