from __future__ import annotations

from datetime import datetime
from typing import Any, TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.campaign import Campaign
    from app.models.market import Market


CONVERSATION_PROVIDERS = ("telegram", "whatsapp", "panel")
MESSAGE_DIRECTIONS = ("inbound", "outbound")
MESSAGE_TYPES = ("text", "file", "image", "button", "system")


class Conversation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint(
            "provider in ('telegram', 'whatsapp', 'panel')",
            name="ck_conversations_provider",
        ),
        Index("ix_conversations_market_id", "market_id"),
        Index("ix_conversations_provider", "provider"),
        Index("ix_conversations_external_chat_id", "external_chat_id"),
        Index("ix_conversations_current_state", "current_state"),
        Index("ix_conversations_last_message_at", "last_message_at"),
        Index(
            "uq_conversations_market_provider_external_chat_id",
            "market_id",
            "provider",
            "external_chat_id",
            unique=True,
            postgresql_where=text("external_chat_id IS NOT NULL"),
        ),
    )

    market_id: Mapped[UUID] = mapped_column(ForeignKey("markets.id"), nullable=False)
    campaign_id: Mapped[UUID | None] = mapped_column(ForeignKey("campaigns.id"))
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    external_chat_id: Mapped[str | None] = mapped_column(String(255))
    external_user_id: Mapped[str | None] = mapped_column(String(255))
    current_state: Mapped[str] = mapped_column(String(64), default="idle", nullable=False)
    state_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    market: Mapped[Market] = relationship()
    campaign: Mapped[Campaign | None] = relationship(back_populates="conversation")
    incoming_messages: Mapped[list[IncomingMessage]] = relationship(back_populates="conversation")


class IncomingMessage(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "incoming_messages"
    __table_args__ = (
        CheckConstraint(
            "provider in ('telegram', 'whatsapp', 'panel')",
            name="ck_incoming_messages_provider",
        ),
        CheckConstraint(
            "direction in ('inbound', 'outbound')",
            name="ck_incoming_messages_direction",
        ),
        CheckConstraint(
            "message_type in ('text', 'file', 'image', 'button', 'system')",
            name="ck_incoming_messages_message_type",
        ),
        Index("ix_incoming_messages_market_id", "market_id"),
        Index("ix_incoming_messages_provider", "provider"),
        Index("ix_incoming_messages_external_message_id", "external_message_id"),
        Index("ix_incoming_messages_conversation_id", "conversation_id"),
        Index("ix_incoming_messages_campaign_id", "campaign_id"),
        Index("ix_incoming_messages_created_at", "created_at"),
    )

    market_id: Mapped[UUID] = mapped_column(ForeignKey("markets.id"), nullable=False)
    conversation_id: Mapped[UUID | None] = mapped_column(ForeignKey("conversations.id"))
    campaign_id: Mapped[UUID | None] = mapped_column(ForeignKey("campaigns.id"))
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), default="inbound", nullable=False)
    message_type: Mapped[str] = mapped_column(String(32), nullable=False)
    external_message_id: Mapped[str | None] = mapped_column(String(255))
    text: Mapped[str | None] = mapped_column(Text)
    file_name: Mapped[str | None] = mapped_column(String(255))
    file_mime_type: Mapped[str | None] = mapped_column(String(100))
    file_size_bytes: Mapped[int | None] = mapped_column(Integer)
    storage_key: Mapped[str | None] = mapped_column(String(1000))
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    market: Mapped[Market] = relationship()
    conversation: Mapped[Conversation | None] = relationship(back_populates="incoming_messages")
    campaign: Mapped[Campaign | None] = relationship()
