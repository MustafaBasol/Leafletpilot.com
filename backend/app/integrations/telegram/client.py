from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

import httpx

from app.core.config import settings
from app.integrations.telegram.schemas import InlineKeyboardMarkup


class TelegramClientError(RuntimeError):
    pass


class TelegramClientProtocol(Protocol):
    async def send_message(
        self,
        chat_id: int,
        text: str,
        *,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> None: ...

    async def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        *,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> None: ...

    async def answer_callback_query(self, callback_query_id: str, *, text: str | None = None) -> None: ...

    async def send_document(self, chat_id: int, path: Path, *, caption: str | None = None) -> None: ...

    async def send_photo(self, chat_id: int, path: Path, *, caption: str | None = None) -> None: ...

    async def aclose(self) -> None: ...


class TelegramClient:
    def __init__(
        self,
        *,
        token: str,
        timeout_seconds: int = 20,
        max_attempts: int = 1,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._token = token
        self._base_url = f"https://api.telegram.org/bot{token}"
        self._timeout = httpx.Timeout(timeout_seconds)
        self._max_attempts = 1
        self._client = http_client or httpx.AsyncClient(timeout=self._timeout)
        self._owns_client = http_client is None

    async def send_message(
        self,
        chat_id: int,
        text: str,
        *,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> None:
        payload: dict[str, Any] = {"chat_id": chat_id, "text": _bound_text(text)}
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        await self._post_json("sendMessage", payload)

    async def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        *,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> None:
        payload: dict[str, Any] = {"chat_id": chat_id, "message_id": message_id, "text": _bound_text(text)}
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        await self._post_json("editMessageText", payload)

    async def answer_callback_query(self, callback_query_id: str, *, text: str | None = None) -> None:
        payload: dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = _bound_text(text, limit=200)
        await self._post_json("answerCallbackQuery", payload)

    async def send_document(self, chat_id: int, path: Path, *, caption: str | None = None) -> None:
        await self._send_file("sendDocument", chat_id, path, "document", caption=caption)

    async def send_photo(self, chat_id: int, path: Path, *, caption: str | None = None) -> None:
        await self._send_file("sendPhoto", chat_id, path, "photo", caption=caption)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _post_json(self, method: str, payload: dict[str, Any]) -> None:
        await self._request(method, json=payload)

    async def _send_file(self, method: str, chat_id: int, path: Path, field_name: str, *, caption: str | None) -> None:
        if not path.is_file() or path.stat().st_size <= 0:
            raise TelegramClientError("Generated file is missing or empty.")
        data: dict[str, Any] = {"chat_id": chat_id}
        if caption:
            data["caption"] = _bound_text(caption, limit=1024)
        with path.open("rb") as file_obj:
            await self._request(method, data=data, files={field_name: (path.name, file_obj)})

    async def _request(self, method: str, **kwargs: Any) -> None:
        url = f"{self._base_url}/{method}"
        try:
            response = await self._client.post(url, **kwargs)
            response.raise_for_status()
            body = response.json()
            if body.get("ok") is not True:
                description = str(body.get("description") or "Telegram API returned ok=false")
                raise TelegramClientError(_redact(description, self._token))
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise TelegramClientError(_redact("Telegram API request failed.", self._token)) from exc
        except httpx.HTTPStatusError as exc:
            message = f"Telegram API HTTP error {exc.response.status_code}"
            raise TelegramClientError(_redact(message, self._token)) from exc


def build_telegram_client() -> TelegramClient:
    return TelegramClient(
        token=settings.telegram_bot_token,
        timeout_seconds=settings.telegram_http_timeout_seconds,
        max_attempts=settings.telegram_http_max_attempts,
    )


def _bound_text(value: str, *, limit: int = 4096) -> str:
    return value[:limit]


def _redact(value: str, token: str) -> str:
    return value.replace(token, "<redacted>") if token else value
