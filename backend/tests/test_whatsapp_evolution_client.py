"""Unit coverage for `app/integrations/whatsapp/client.py` and `app/services/phone.py`.

No network, no DB: the Evolution client is driven entirely through
`httpx.MockTransport`, so none of these tests need the
`when_test_database_url_is_configured` suffix.
"""

from __future__ import annotations

import base64
import json

import httpx
import pytest

from app.integrations.whatsapp.client import (
    EvolutionAuthError,
    EvolutionClient,
    EvolutionClientError,
    EvolutionUnavailableError,
)
from app.services.phone import mask_phone, normalize_phone_e164, parse_whatsapp_jid

BASE_URL = "https://evo.example.com"


def _client(handler, *, api_key: str = "test-key", instance_name: str = "main") -> EvolutionClient:
    return EvolutionClient(
        base_url=BASE_URL,
        api_key=api_key,
        instance_name=instance_name,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


# ---------------------------------------------------------------------------
# 1/2/3. send_text request shape, instance-name quoting, text bounding.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_text_request_shape_and_returns_message_id() -> None:
    captured: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["apikey_header"] = request.headers.get("apikey")
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"key": {"id": "MSG123"}})

    client = _client(handler, api_key="test-key", instance_name="main")

    message_id = await client.send_text("+33600000012", "hello world")

    assert captured["method"] == "POST"
    assert captured["url"] == f"{BASE_URL}/message/sendText/main"
    assert captured["apikey_header"] == "test-key"
    assert captured["body"] == {"number": "33600000012", "text": "hello world"}
    assert message_id == "MSG123"


@pytest.mark.asyncio
async def test_instance_name_is_url_quoted_in_request_path() -> None:
    captured_urls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured_urls.append(str(request.url))
        return httpx.Response(200, json={"key": {"id": "x"}})

    client = _client(handler, instance_name="My Instance/2")
    await client.send_text("+33600000012", "hi")

    assert captured_urls[0] == f"{BASE_URL}/message/sendText/My%20Instance%2F2"


@pytest.mark.asyncio
async def test_send_text_truncates_body_to_4096_characters() -> None:
    captured: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"key": {"id": "x"}})

    client = _client(handler)
    long_text = "a" * 9000
    await client.send_text("+33600000012", long_text)

    assert len(captured["body"]["text"]) == 4096
    assert captured["body"]["text"] == "a" * 4096


# ---------------------------------------------------------------------------
# 4. send_text is NOT retried (would duplicate a WhatsApp message).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_text_is_not_retried_on_connect_timeout() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectTimeout("boom", request=request)

    client = _client(handler)

    with pytest.raises(EvolutionUnavailableError):
        await client.send_text("+33600000012", "hi")

    assert calls == 1


# ---------------------------------------------------------------------------
# 5/6. fetch_connection_state — open/close mapping, retried once.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_connection_state_maps_open_and_close() -> None:
    async def open_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"instance": {"instanceName": "x", "state": "open"}})

    open_client = _client(open_handler)
    open_result = await open_client.fetch_connection_state()
    assert open_result.ok is True
    assert open_result.state == "open"

    async def close_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"instance": {"instanceName": "x", "state": "close"}})

    close_client = _client(close_handler)
    close_result = await close_client.fetch_connection_state()
    assert close_result.ok is False
    assert close_result.state == "close"


@pytest.mark.asyncio
async def test_fetch_connection_state_is_retried_once_on_transport_failure() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectTimeout("boom", request=request)
        return httpx.Response(200, json={"instance": {"instanceName": "x", "state": "open"}})

    client = _client(handler)
    result = await client.fetch_connection_state()

    assert result.ok is True
    assert calls == 2


# ---------------------------------------------------------------------------
# 7. Status-code -> exception mapping, and the exception hierarchy.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_code_maps_to_the_correct_exception_class() -> None:
    for status_code, expected_exc in (
        (401, EvolutionAuthError),
        (403, EvolutionAuthError),
        (500, EvolutionUnavailableError),
        (400, EvolutionClientError),
    ):

        async def handler(request: httpx.Request, status_code=status_code) -> httpx.Response:
            return httpx.Response(status_code, json={"message": "nope"})

        client = _client(handler)
        with pytest.raises(expected_exc):
            await client.send_text("+33600000012", "hi")


def test_evolution_error_hierarchy() -> None:
    assert issubclass(EvolutionAuthError, EvolutionClientError)
    assert issubclass(EvolutionUnavailableError, EvolutionClientError)


# ---------------------------------------------------------------------------
# 8. A non-JSON 200 response must not let a JSONDecodeError escape.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_json_200_response_raises_client_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>not json</html>", headers={"content-type": "text/html"})

    client = _client(handler)
    with pytest.raises(EvolutionClientError):
        await client.send_text("+33600000012", "hi")


# ---------------------------------------------------------------------------
# 9. The API key is redacted from every error message; the response body is
# never echoed into the message either.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_key_and_response_body_never_appear_in_error_messages() -> None:
    secret = "sk-leak-me-please"

    async def handler_401(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text=f"unauthorized, key={secret}")

    client_401 = _client(handler_401, api_key=secret)
    with pytest.raises(EvolutionAuthError) as exc_info_401:
        await client_401.send_text("+33600000012", "hi")
    assert secret not in str(exc_info_401.value)
    assert "unauthorized, key=" not in str(exc_info_401.value)

    async def handler_500(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text=f"server exploded {secret}")

    client_500 = _client(handler_500, api_key=secret)
    with pytest.raises(EvolutionUnavailableError) as exc_info_500:
        await client_500.send_text("+33600000012", "hi")
    assert secret not in str(exc_info_500.value)
    assert "server exploded" not in str(exc_info_500.value)

    async def handler_400(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text=f"bad request {secret}")

    client_400 = _client(handler_400, api_key=secret)
    with pytest.raises(EvolutionClientError) as exc_info_400:
        await client_400.send_text("+33600000012", "hi")
    assert secret not in str(exc_info_400.value)
    assert "bad request" not in str(exc_info_400.value)


# ---------------------------------------------------------------------------
# 10. send_media.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_media_uploads_base64_encoded_file_contents(tmp_path) -> None:
    file_path = tmp_path / "flyer.png"
    content = b"\x89PNG\r\n\x1a\nfake-flyer-bytes"
    file_path.write_bytes(content)
    captured: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"key": {"id": "MEDIA1"}})

    client = _client(handler)
    message_id = await client.send_media(
        "+33600000012",
        file_path,
        media_type="image",
        mime_type="image/png",
        file_name="flyer.png",
    )

    assert captured["url"] == f"{BASE_URL}/message/sendMedia/main"
    assert captured["body"]["mediatype"] == "image"
    assert captured["body"]["mimetype"] == "image/png"
    assert captured["body"]["fileName"] == "flyer.png"
    assert base64.b64decode(captured["body"]["media"]) == content
    assert message_id == "MEDIA1"


@pytest.mark.asyncio
async def test_send_media_rejects_missing_empty_and_oversized_files_without_a_request(tmp_path, monkeypatch) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("send_media must not perform a request for an invalid file")

    client = _client(handler)

    missing_path = tmp_path / "missing.png"
    with pytest.raises(EvolutionClientError):
        await client.send_media(
            "+33600000012", missing_path, media_type="image", mime_type="image/png", file_name="missing.png"
        )

    empty_path = tmp_path / "empty.png"
    empty_path.write_bytes(b"")
    with pytest.raises(EvolutionClientError):
        await client.send_media(
            "+33600000012", empty_path, media_type="image", mime_type="image/png", file_name="empty.png"
        )

    oversized_path = tmp_path / "big.png"
    oversized_path.write_bytes(b"x" * 1024)
    monkeypatch.setattr("app.integrations.whatsapp.client.MAX_MEDIA_BYTES", 100)
    with pytest.raises(EvolutionClientError):
        await client.send_media(
            "+33600000012", oversized_path, media_type="image", mime_type="image/png", file_name="big.png"
        )


# ---------------------------------------------------------------------------
# 11. aclose only closes a client it owns.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aclose_only_closes_a_client_it_owns() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"key": {"id": "x"}})

    injected = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = EvolutionClient(base_url=BASE_URL, api_key="key", instance_name="main", http_client=injected)

    await client.aclose()

    assert injected.is_closed is False
    await injected.aclose()


@pytest.mark.asyncio
async def test_aclose_closes_a_client_it_created() -> None:
    client = EvolutionClient(base_url=BASE_URL, api_key="key", instance_name="main")
    owned_client = client._client  # noqa: SLF001 - inspecting internal state deliberately

    await client.aclose()

    assert owned_client.is_closed is True


# ---------------------------------------------------------------------------
# 12. Phone helpers (app/services/phone.py).
# ---------------------------------------------------------------------------


def test_normalize_phone_e164_handles_various_inputs() -> None:
    assert normalize_phone_e164("33612345678") == "+33612345678"
    assert normalize_phone_e164("+33 6 12 34 56 78") == "+33612345678"
    assert normalize_phone_e164("0612345678", default_region="FR") == "+33612345678"
    assert normalize_phone_e164("05321234567", default_region="TR") == "+905321234567"
    assert normalize_phone_e164("not a phone") is None
    assert normalize_phone_e164("") is None
    assert normalize_phone_e164(None) is None


def test_mask_phone_keeps_country_code_and_last_two_digits() -> None:
    masked = mask_phone("+33612345678")
    assert masked.startswith("+33")
    assert masked.endswith("78")
    assert "*" in masked
    assert "612345" not in masked


def test_parse_whatsapp_jid_handles_user_group_lid_and_device_suffix() -> None:
    user_jid = parse_whatsapp_jid("33612345678@s.whatsapp.net")
    assert user_jid is not None
    assert user_jid.phone_e164 == "+33612345678"
    assert user_jid.is_user is True
    assert user_jid.is_group is False
    assert user_jid.is_lid is False

    group_jid = parse_whatsapp_jid("123456789-987654@g.us")
    assert group_jid is not None
    assert group_jid.is_group is True
    assert group_jid.phone_e164 is None

    lid_jid = parse_whatsapp_jid("999999999@lid")
    assert lid_jid is not None
    assert lid_jid.is_lid is True
    assert lid_jid.phone_e164 is None

    device_jid = parse_whatsapp_jid("33612345678:12@s.whatsapp.net")
    assert device_jid is not None
    assert device_jid.phone_e164 == "+33612345678"
    assert device_jid.is_user is True

    assert parse_whatsapp_jid("no-at-sign-here") is None
    assert parse_whatsapp_jid(None) is None
