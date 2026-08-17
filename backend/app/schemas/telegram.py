from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class TelegramStatusRead(BaseModel):
    connected: bool
    username: str | None = None
    linked_at: datetime | None = None
    connected_member_count: int
