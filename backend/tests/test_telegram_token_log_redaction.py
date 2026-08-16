from __future__ import annotations

import logging

import httpx
import pytest

from app.core.logging import TelegramTokenRedactionFilter, install_telegram_token_redaction
from app.integrations.telegram.client import TelegramClient, TelegramClientError

# Shaped like a real Telegram bot token (numeric bot id + 35-char secret)
# but not a live credential.
REALISTIC_TOKEN = "123456789:AAFakeTokenNotReal_ABCDEFGHIJKLMNOPQ"


def _prepare_caplog(caplog: pytest.LogCaptureFixture) -> None:
    # install_telegram_token_redaction() is idempotent; call it after caplog's
    # handler is attached so the filter also covers caplog's own handler.
    install_telegram_token_redaction()
    caplog.set_level(logging.INFO)


def test_redaction_pattern_matches_task_example() -> None:
    filter_ = TelegramTokenRedactionFilter()
    record = logging.LogRecord(
        name="httpx",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='HTTP Request: %s %s "%s %d %s"',
        args=("POST", "https://api.telegram.org/bot123456789:ABCDEF/sendMessage", "HTTP/1.1", 200, "OK"),
        exc_info=None,
    )

    assert filter_.filter(record) is True
    assert record.getMessage() == (
        'HTTP Request: POST https://api.telegram.org/bot[REDACTED]/sendMessage "HTTP/1.1 200 OK"'
    )


def test_install_telegram_token_redaction_is_idempotent() -> None:
    root = logging.getLogger()
    handler = logging.StreamHandler()
    root.addHandler(handler)
    try:
        install_telegram_token_redaction()
        install_telegram_token_redaction()
        matching = [f for f in handler.filters if isinstance(f, TelegramTokenRedactionFilter)]
        assert len(matching) == 1
    finally:
        root.removeHandler(handler)


@pytest.mark.asyncio
async def test_successful_request_does_not_log_bot_token(caplog: pytest.LogCaptureFixture) -> None:
    _prepare_caplog(caplog)

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True, "result": {}})

    client = TelegramClient(
        token=REALISTIC_TOKEN,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    await client.send_message(1, "hello")

    assert REALISTIC_TOKEN not in caplog.text
    assert "sendMessage" in caplog.text
    assert "[REDACTED]" in caplog.text


@pytest.mark.asyncio
async def test_failed_http_response_does_not_log_bot_token(caplog: pytest.LogCaptureFixture) -> None:
    _prepare_caplog(caplog)
    logger = logging.getLogger("test.telegram.http_error_path")

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"ok": False, "description": "Not Found"})

    client = TelegramClient(
        token=REALISTIC_TOKEN,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(TelegramClientError):
        try:
            await client.send_message(1, "hello")
        except TelegramClientError:
            # Mirrors app.integrations.telegram.service.process_update, which
            # logs the failure via logger.exception(), chaining the original
            # httpx.HTTPStatusError (whose default str() embeds the request
            # URL, and therefore the token) into the traceback.
            logger.exception("Telegram request failed")
            raise

    assert REALISTIC_TOKEN not in caplog.text


@pytest.mark.asyncio
async def test_network_exception_does_not_log_bot_token(caplog: pytest.LogCaptureFixture) -> None:
    _prepare_caplog(caplog)
    logger = logging.getLogger("test.telegram.network_error_path")

    async def handler(request: httpx.Request) -> httpx.Response:
        # Some transport backends embed the request URL in connection-error
        # text (e.g. "Connection to <url> failed: ..."); simulate that shape.
        raise httpx.ConnectError(f"Connection to {request.url} failed: [Errno 111] Connection refused", request=request)

    client = TelegramClient(
        token=REALISTIC_TOKEN,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(TelegramClientError):
        try:
            await client.send_message(1, "hello")
        except TelegramClientError:
            logger.exception("Telegram request failed")
            raise

    assert REALISTIC_TOKEN not in caplog.text


@pytest.mark.asyncio
async def test_send_document_and_send_photo_do_not_log_bot_token(caplog: pytest.LogCaptureFixture, tmp_path) -> None:
    _prepare_caplog(caplog)
    path = tmp_path / "flyer.pdf"
    path.write_bytes(b"content")

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True, "result": {}})

    client = TelegramClient(
        token=REALISTIC_TOKEN,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    await client.send_document(1, path)
    await client.send_photo(1, path)

    assert REALISTIC_TOKEN not in caplog.text
    assert "sendDocument" in caplog.text
    assert "sendPhoto" in caplog.text


def test_httpcore_debug_trace_target_does_not_log_bot_token(caplog: pytest.LogCaptureFixture) -> None:
    # At LOG_LEVEL=DEBUG, httpcore's http11 tracer logs the raw request
    # target (path only, no host) via logger "httpcore.http11", e.g.:
    #   send_request_headers.started request=<Request ...> target=b'/bot<TOKEN>/sendMessage'
    # This does not contain "api.telegram.org", so it exercises the
    # path-anchored (rather than domain-anchored) redaction pattern.
    _prepare_caplog(caplog)
    logger = logging.getLogger("httpcore.http11")
    caplog.set_level(logging.DEBUG, logger="httpcore.http11")

    logger.debug(
        "send_request_headers.started target=%r",
        f"/bot{REALISTIC_TOKEN}/sendMessage".encode(),
    )

    assert REALISTIC_TOKEN not in caplog.text
    assert "sendMessage" in caplog.text
    assert "[REDACTED]" in caplog.text


def test_non_telegram_logging_remains_unaffected(caplog: pytest.LogCaptureFixture) -> None:
    _prepare_caplog(caplog)
    logger = logging.getLogger("test.unrelated")

    logger.info("Fetched %s items from %s", 5, "https://api.example.com/v1/products")

    assert "Fetched 5 items from https://api.example.com/v1/products" in caplog.text
    assert "[REDACTED]" not in caplog.text
