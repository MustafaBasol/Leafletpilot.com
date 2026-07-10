from __future__ import annotations

import hmac
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import ValidationError

from app.api.deps import get_catalog_session
from app.core.config import settings
from app.integrations.telegram.client import TelegramClientProtocol, build_telegram_client
from app.integrations.telegram.schemas import TelegramUpdate
from app.integrations.telegram.service import process_update

router = APIRouter(prefix="/integrations/telegram", tags=["telegram"])

MAX_TELEGRAM_BODY_BYTES = 64 * 1024


async def get_telegram_client() -> AsyncGenerator[TelegramClientProtocol, None]:
    client = build_telegram_client()
    try:
        yield client
    finally:
        await client.aclose()


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, bool]:
    if not settings.telegram_bot_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Telegram integration is disabled.")
    if not _valid_secret(x_telegram_bot_api_secret_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Telegram webhook secret.")

    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared_length = int(content_length)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Content-Length header.",
            ) from exc
        if declared_length > MAX_TELEGRAM_BODY_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Telegram update is too large.",
            )
    body = await request.body()
    if len(body) > MAX_TELEGRAM_BODY_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Telegram update is too large.")
    try:
        update = TelegramUpdate.model_validate_json(body)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Malformed Telegram update.") from exc

    client_dependency = request.app.dependency_overrides.get(get_telegram_client, get_telegram_client)
    async for session in get_catalog_session():
        async for client in client_dependency():
            await process_update(session, update, client)
    return {"ok": True}


def _valid_secret(candidate: str | None) -> bool:
    if candidate is None:
        return False
    return hmac.compare_digest(candidate, settings.telegram_webhook_secret)
