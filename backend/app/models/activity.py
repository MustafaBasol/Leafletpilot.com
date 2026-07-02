from __future__ import annotations

from typing import Any, TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.market import Market
    from app.models.user import User


class ActivityLog(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "activity_logs"
    __table_args__ = (
        Index("ix_activity_logs_market_id", "market_id"),
        Index("ix_activity_logs_user_id", "user_id"),
        Index("ix_activity_logs_entity_type_entity_id", "entity_type", "entity_id"),
        Index("ix_activity_logs_created_at", "created_at"),
    )

    market_id: Mapped[UUID | None] = mapped_column(ForeignKey("markets.id"))
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    entity_type: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_id: Mapped[UUID | None]
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000))
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)

    market: Mapped[Market | None] = relationship(back_populates="activity_logs")
    user: Mapped[User | None] = relationship(back_populates="activity_logs")
