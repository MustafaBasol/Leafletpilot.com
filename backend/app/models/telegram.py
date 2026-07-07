from __future__ import annotations

from datetime import datetime
from typing import Any, TYPE_CHECKING
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin, utc_now

if TYPE_CHECKING:
    from app.models.campaign import Campaign
    from app.models.export import ExportJob
    from app.models.market import Market
    from app.models.user import User


TELEGRAM_UPDATE_STATUSES = ("received", "processing", "completed", "failed")
TELEGRAM_CONVERSATION_STATES = (
    "idle",
    "awaiting_market",
    "awaiting_product_list",
    "awaiting_title",
    "awaiting_confirmation",
    "generating_exports",
    "completed",
)


class TelegramAccount(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "telegram_accounts"
    __table_args__ = (
        Index("ix_telegram_accounts_user_id", "user_id"),
        Index("ix_telegram_accounts_telegram_user_id", "telegram_user_id", unique=True),
        Index(
            "uq_telegram_accounts_active_user_id",
            "user_id",
            unique=True,
            postgresql_where=text("is_active IS TRUE"),
        ),
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    username: Mapped[str | None] = mapped_column(String(255))
    first_name: Mapped[str | None] = mapped_column(String(255))
    last_name: Mapped[str | None] = mapped_column(String(255))
    last_chat_id: Mapped[int | None] = mapped_column(BigInteger)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    user: Mapped[User] = relationship()


class TelegramUpdate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "telegram_updates"
    __table_args__ = (
        CheckConstraint(
            "status in ('received', 'processing', 'completed', 'failed')",
            name="ck_telegram_updates_status",
        ),
        Index("ix_telegram_updates_update_id", "update_id", unique=True),
        Index("ix_telegram_updates_status", "status"),
        Index("ix_telegram_updates_telegram_user_id", "telegram_user_id"),
        Index("ix_telegram_updates_chat_id", "chat_id"),
        Index("ix_telegram_updates_received_at", "received_at"),
    )

    update_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="received", nullable=False)
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger)
    chat_id: Mapped[int | None] = mapped_column(BigInteger)
    update_type: Mapped[str | None] = mapped_column(String(64))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(String(1000))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TelegramConversationState(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "telegram_conversation_states"
    __table_args__ = (
        CheckConstraint(
            "state in ('idle', 'awaiting_market', 'awaiting_product_list', 'awaiting_title', "
            "'awaiting_confirmation', 'generating_exports', 'completed')",
            name="ck_telegram_conversation_states_state",
        ),
        Index("ix_telegram_conversation_states_user_id", "user_id"),
        Index("ix_telegram_conversation_states_selected_market_id", "selected_market_id"),
        Index("ix_telegram_conversation_states_state", "state"),
        Index("ix_telegram_conversation_states_telegram_user_id", "telegram_user_id", unique=True),
    )

    telegram_account_id: Mapped[UUID] = mapped_column(ForeignKey("telegram_accounts.id"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    chat_id: Mapped[int | None] = mapped_column(BigInteger)
    selected_market_id: Mapped[UUID | None] = mapped_column(ForeignKey("markets.id"))
    state: Mapped[str] = mapped_column(String(64), default="idle", nullable=False)
    pending_raw_text: Mapped[str | None] = mapped_column(Text)
    parsed_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    pending_title: Mapped[str | None] = mapped_column(String(255))
    campaign_id: Mapped[UUID | None] = mapped_column(ForeignKey("campaigns.id"))
    export_job_id: Mapped[UUID | None] = mapped_column(ForeignKey("export_jobs.id"))
    export_document_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    export_photo_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    export_files_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    export_delivery_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(1000))
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    telegram_account: Mapped[TelegramAccount] = relationship()
    user: Mapped[User] = relationship()
    selected_market: Mapped[Market | None] = relationship()
    campaign: Mapped[Campaign | None] = relationship()
    export_job: Mapped[ExportJob | None] = relationship()
