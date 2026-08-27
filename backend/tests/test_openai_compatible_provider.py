from __future__ import annotations

import json
from typing import ClassVar, Self

import httpx
import pytest
from pydantic import BaseModel

from app.services.ai.errors import (
    AIProviderAuthenticationError,
    AIProviderError,
    AIProviderTimeoutError,
)
from app.services.ai.openai_compatible import OpenAICompatibleProvider
from app.services.ai.types import AICapability


class StructuredOutput(BaseModel):
    status: str
    summary: str


class RecordingAsyncClient:
    responses: ClassVar[list[httpx.Response | Exception]] = []
    calls: ClassVar[list[dict[str, object]]] = []
    timeouts: ClassVar[list[int]] = []

    def __init__(self, *, timeout: int) -> None:
        self.timeouts.append(timeout)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def post(
        self, url: str, *, headers: dict[str, str], json: dict[str, object]
    ) -> httpx.Response:
        self.calls.append({"url": url, "headers": headers, "json": json})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture(autouse=True)
def mock_async_client(monkeypatch: pytest.MonkeyPatch) -> None:
    RecordingAsyncClient.responses = []
    RecordingAsyncClient.calls = []
    RecordingAsyncClient.timeouts = []
    monkeypatch.setattr(
        "app.services.ai.openai_compatible.httpx.AsyncClient", RecordingAsyncClient
    )


def _provider(*, timeout_seconds: int = 15, max_attempts: int = 2) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        api_base_url="https://api.openai.com/v1",
        api_key="test-provider-key",
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
    )


async def _generate(provider: OpenAICompatibleProvider, *, model: str = "gpt-5-mini"):
    return await provider.generate_structured(
        capability=AICapability.CHEAP_TEXT_REVISION,
        model=model,
        system_prompt="Return the requested structured result.",
        user_prompt="Revise this campaign.",
        schema=StructuredOutput,
        context={"campaign_id": "campaign-test-id"},
    )


def _success_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "message": {
                        "content": json.dumps({"status": "ready", "summary": "Done"})
                    }
                }
            ],
            "usage": {"prompt_tokens": 11, "completion_tokens": 7},
        },
    )


@pytest.mark.asyncio
async def test_gpt5_mini_structured_request_uses_defaults_and_parses_response() -> None:
    RecordingAsyncClient.responses = [_success_response()]

    result = await _generate(_provider())

    assert result.output == {"status": "ready", "summary": "Done"}
    assert result.usage.input_tokens == 11
    assert result.usage.output_tokens == 7
    request = RecordingAsyncClient.calls[0]
    assert request["url"] == "https://api.openai.com/v1/chat/completions"
    assert request["headers"] == {
        "Authorization": "Bearer test-provider-key",
        "Content-Type": "application/json",
    }
    payload = request["json"]
    assert payload["model"] == "gpt-5-mini"
    assert "temperature" not in payload
    assert payload["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "StructuredOutput",
            "strict": True,
            "schema": StructuredOutput.model_json_schema(),
        },
    }


@pytest.mark.asyncio
async def test_provider_keeps_configured_model_value() -> None:
    RecordingAsyncClient.responses = [_success_response()]

    await _generate(_provider(), model="configured-model")

    assert RecordingAsyncClient.calls[0]["json"]["model"] == "configured-model"


@pytest.mark.asyncio
async def test_non_transient_client_error_is_not_retried() -> None:
    RecordingAsyncClient.responses = [
        httpx.Response(400, json={"error": {"message": "bad request"}})
    ]

    with pytest.raises(AIProviderError, match="rejected the request \\(400\\)"):
        await _generate(_provider())

    assert len(RecordingAsyncClient.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [401, 403])
async def test_authentication_errors_are_not_retried(status_code: int) -> None:
    RecordingAsyncClient.responses = [httpx.Response(status_code)]

    with pytest.raises(AIProviderAuthenticationError):
        await _generate(_provider())

    assert len(RecordingAsyncClient.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [408, 429, 500, 503])
async def test_transient_http_statuses_retry_once(status_code: int) -> None:
    RecordingAsyncClient.responses = [httpx.Response(status_code), _success_response()]

    result = await _generate(_provider())

    assert result.output["status"] == "ready"
    assert len(RecordingAsyncClient.calls) == 2


@pytest.mark.asyncio
async def test_timeout_retry_limit_and_timeout_value_are_unchanged() -> None:
    RecordingAsyncClient.responses = [
        httpx.TimeoutException("timeout"),
        httpx.TimeoutException("timeout"),
    ]

    with pytest.raises(AIProviderTimeoutError):
        await _generate(_provider(timeout_seconds=17, max_attempts=9))

    assert len(RecordingAsyncClient.calls) == 2
    assert RecordingAsyncClient.timeouts == [17, 17]
