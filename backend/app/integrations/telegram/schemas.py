from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TelegramUser(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    is_bot: bool | None = None
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None


class TelegramChat(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    type: str


class TelegramMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message_id: int
    from_: TelegramUser | None = Field(default=None, alias="from")
    chat: TelegramChat
    text: str | None = None
    date: int | None = None


class TelegramCallbackQuery(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    from_: TelegramUser = Field(alias="from")
    message: TelegramMessage | None = None
    data: str | None = None


class TelegramUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    update_id: int
    message: TelegramMessage | None = None
    callback_query: TelegramCallbackQuery | None = None

    @property
    def update_type(self) -> str:
        if self.callback_query is not None:
            return "callback_query"
        if self.message is not None:
            return "message"
        return "unsupported"

    @property
    def telegram_user(self) -> TelegramUser | None:
        if self.callback_query is not None:
            return self.callback_query.from_
        if self.message is not None:
            return self.message.from_
        return None

    @property
    def chat(self) -> TelegramChat | None:
        if self.callback_query is not None and self.callback_query.message is not None:
            return self.callback_query.message.chat
        if self.message is not None:
            return self.message.chat
        return None

    @property
    def text(self) -> str | None:
        return self.message.text if self.message is not None else None

    @property
    def callback_data(self) -> str | None:
        return self.callback_query.data if self.callback_query is not None else None


InlineKeyboardMarkup = dict[str, list[list[dict[str, Any]]]]
