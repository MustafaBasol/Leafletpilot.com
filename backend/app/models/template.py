from __future__ import annotations

from datetime import datetime
from typing import Any, TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.market import Market


class Template(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "templates"
    __table_args__ = (
        CheckConstraint(
            "(is_global = true and market_id is null) or (is_global = false and market_id is not null)",
            name="ck_templates_market_scope",
        ),
        Index("ix_templates_market_id", "market_id"),
        Index("ix_templates_slug", "slug"),
        Index("ix_templates_is_active", "is_active"),
        Index("ix_templates_is_global", "is_global"),
        Index("uq_templates_global_slug", "slug", unique=True, postgresql_where=text("market_id IS NULL")),
        Index(
            "uq_templates_market_slug",
            "market_id",
            "slug",
            unique=True,
            postgresql_where=text("market_id IS NOT NULL"),
        ),
    )

    market_id: Mapped[UUID | None] = mapped_column(ForeignKey("markets.id"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    template_type: Mapped[str] = mapped_column(String(64), nullable=False)
    is_global: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    visibility: Mapped[str] = mapped_column(String(32), default="shared", nullable=False)
    minimum_plan: Mapped[str] = mapped_column(String(32), default="starter", nullable=False)
    category: Mapped[str | None] = mapped_column(String(120))
    thumbnail_key: Mapped[str | None] = mapped_column(String(1000))
    source_template_id: Mapped[UUID | None] = mapped_column(ForeignKey("templates.id"))
    source_version: Mapped[int | None] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    config_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    market: Mapped[Market | None] = relationship(foreign_keys=[market_id])
