from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class EmailChangeToken(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Verify-first email change (Team page). The account's `User.email` is only ever
    overwritten once this token is confirmed — until then the OLD email stays the active
    login identity. Reuses the same token-hash pattern as password_reset_tokens/
    market_invitations (app.core.security.generate_invitation_token/hash_invitation_token)."""

    __tablename__ = "email_change_tokens"
    __table_args__ = (
        Index("ix_email_change_tokens_user_id", "user_id"),
        Index("ix_email_change_tokens_token_hash", "token_hash"),
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    new_email: Mapped[str] = mapped_column(String(255), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))

    user: Mapped[User] = relationship(foreign_keys=[user_id])
