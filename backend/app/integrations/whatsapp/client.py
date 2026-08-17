"""Outbound Evolution API (WhatsApp) client for the central platform channel.

Version assumption: this client targets **Evolution API v2.x** (the current
maintained line as of writing). It uses the v2 endpoint shapes:
- `POST /message/sendText/{instance}` with body `{"number": ..., "text": ...}`
- `GET /instance/connectionState/{instance}` returning
  `{"instance": {"instanceName": ..., "state": "open" | "connecting" | "close"}}`

Auth is via the `apikey` header on every request (Evolution's scheme), not
`Authorization: Bearer`.

There is exactly ONE platform-owned Evolution instance shared by all markets
(see `app/core/config.py`), so this module has no per-market state.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote

import httpx

from app.core.config import settings
from app.services.phone import phone_to_whatsapp_number


class EvolutionClientError(RuntimeError):
    """Base error for all Evolution API client failures."""


class EvolutionAuthError(EvolutionClientError):
    """Raised when Evolution rejects the request as unauthenticated/forbidden (401/403)."""


class EvolutionUnavailableError(EvolutionClientError):
    """Raised on timeout, transport failure, or a 5xx response from Evolution."""


@dataclass(frozen=True)
class EvolutionConnectionState:
    ok: bool
    state: str | None
    detail: str | None = None


class EvolutionClientProtocol(Protocol):
    async def send_text(self, phone_e164: str, text: str) -> str | None: ...

    async def send_media(
        self,
        phone_e164: str,
        path: Path,
        *,
        media_type: str,
        mime_type: str,
        file_name: str,
        caption: str | None = None,
    ) -> str | None: ...

    async def fetch_connection_state(self) -> EvolutionConnectionState: ...

    async def aclose(self) -> None: ...


# Evolution accepts media inline as base64 in the JSON body. Base64 inflates
# by ~33%, and the whole body must be buffered in memory on both sides, so a
# generated flyer well above this is refused locally rather than sent — a
# LeafletPilot PDF/PNG is normally a few hundred KB.
MAX_MEDIA_BYTES = 16 * 1024 * 1024


class EvolutionClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        instance_name: str,
        timeout_seconds: int = 20,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._instance_name = instance_name
        self._instance_path = quote(instance_name, safe="")
        self._timeout = httpx.Timeout(timeout_seconds)
        self._client = http_client or httpx.AsyncClient(timeout=self._timeout)
        self._owns_client = http_client is None

    async def send_text(self, phone_e164: str, text: str) -> str | None:
        payload: dict[str, Any] = {
            "number": phone_to_whatsapp_number(phone_e164),
            "text": _bound_text(text),
        }
        # Deliberately NOT retried: Evolution has no idempotency key for
        # sendText, so retrying a timed-out/ambiguous request risks sending
        # the same WhatsApp message twice. A duplicate delivery to a market
        # owner is worse than a single failed send that the caller can retry
        # at a higher, message-aware level (with its own dedup).
        body = await self._request(
            "POST", f"/message/sendText/{self._instance_path}", json=payload, allow_retry=False
        )
        return _extract_message_id(body)

    async def send_media(
        self,
        phone_e164: str,
        path: Path,
        *,
        media_type: str,
        mime_type: str,
        file_name: str,
        caption: str | None = None,
    ) -> str | None:
        """Sends a locally rendered flyer file as a WhatsApp image or document.

        `POST /message/sendMedia/{instance}` with the bytes inlined as base64,
        which is the transport that does not require Evolution to be able to
        reach a LeafletPilot URL (campaign files are only served behind
        authentication, so a link would be useless to the recipient).
        """
        if not path.is_file():
            raise EvolutionClientError("Generated file is missing.")
        size = path.stat().st_size
        if size <= 0:
            raise EvolutionClientError("Generated file is empty.")
        if size > MAX_MEDIA_BYTES:
            raise EvolutionClientError("Generated file is too large for WhatsApp delivery.")
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        payload: dict[str, Any] = {
            "number": phone_to_whatsapp_number(phone_e164),
            "mediatype": media_type,
            "mimetype": mime_type,
            "media": encoded,
            "fileName": file_name,
        }
        if caption:
            payload["caption"] = _bound_text(caption, limit=1024)
        # Same no-retry rule as send_text: a retried media send delivers the
        # flyer twice.
        body = await self._request(
            "POST", f"/message/sendMedia/{self._instance_path}", json=payload, allow_retry=False
        )
        return _extract_message_id(body)

    async def fetch_connection_state(self) -> EvolutionConnectionState:
        # Safe to retry once: this is a plain read with no side effects.
        body = await self._request(
            "GET", f"/instance/connectionState/{self._instance_path}", allow_retry=True
        )
        instance = body.get("instance") if isinstance(body, dict) else None
        state = instance.get("state") if isinstance(instance, dict) else None
        return EvolutionConnectionState(ok=state == "open", state=state)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        allow_retry: bool = False,
    ) -> Any:
        url = f"{self._base_url}{path}"
        headers = {"apikey": self._api_key}
        attempts = 2 if allow_retry else 1
        last_exc: Exception | None = None
        for attempt in range(attempts):
            try:
                response = await self._client.request(method, url, json=json, headers=headers)
                if response.status_code in (401, 403):
                    raise EvolutionAuthError(
                        self._redact(f"Evolution API auth error {response.status_code}.")
                    )
                response.raise_for_status()
                try:
                    return response.json()
                except ValueError:
                    # A proxy/error page in front of Evolution can return 200
                    # with HTML. Treat an unparseable body as an upstream
                    # failure rather than letting a JSONDecodeError escape as
                    # an unhandled 500 — and never echo the body itself.
                    raise EvolutionClientError(
                        self._redact("Evolution API returned a non-JSON response.")
                    ) from None
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_exc = exc
                if attempt + 1 < attempts:
                    continue
                raise EvolutionUnavailableError(
                    self._redact("Evolution API request failed.")
                ) from exc
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                if status_code >= 500:
                    raise EvolutionUnavailableError(
                        self._redact(f"Evolution API HTTP error {status_code}.")
                    ) from exc
                raise EvolutionClientError(
                    self._redact(f"Evolution API HTTP error {status_code}.")
                ) from exc
        # Unreachable, but keeps type checkers happy.
        raise EvolutionUnavailableError(self._redact("Evolution API request failed.")) from last_exc

    def _redact(self, value: str) -> str:
        return _redact(value, self._api_key)


def build_evolution_client() -> EvolutionClient:
    return EvolutionClient(
        base_url=settings.evolution_api_base_url,
        api_key=settings.evolution_api_key,
        instance_name=settings.evolution_instance_name,
        timeout_seconds=settings.evolution_http_timeout_seconds,
    )


def evolution_base_url_host() -> str | None:
    """Hostname only (never the full URL, never credentials) for admin display."""
    base_url = settings.evolution_api_base_url.strip()
    if not base_url:
        return None
    return httpx.URL(base_url).host or None


def _bound_text(value: str, *, limit: int = 4096) -> str:
    return value[:limit]


def _extract_message_id(body: Any) -> str | None:
    if not isinstance(body, dict):
        return None
    key = body.get("key")
    if not isinstance(key, dict):
        return None
    message_id = key.get("id")
    return message_id if isinstance(message_id, str) else None


def _redact(value: str, api_key: str) -> str:
    return value.replace(api_key, "<redacted>") if api_key else value
