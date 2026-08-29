from __future__ import annotations

import json
from typing import ClassVar, Self

import httpx
import pytest
from pydantic import BaseModel

from app.schemas.ai import AIRevisionParseEnvelope
from app.services.ai.errors import (
    AIProviderAuthenticationError,
    AIProviderError,
    AIProviderOutputError,
    AIProviderTimeoutError,
    AIProviderTransientError,
)
from app.services.ai.openai_compatible import OpenAICompatibleProvider, build_openai_strict_schema
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
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, object] | None = None,
        data: dict[str, str] | None = None,
        files: list[tuple[str, tuple[str, bytes, str]]] | None = None,
    ) -> httpx.Response:
        self.calls.append(
            {"url": url, "headers": headers, "json": json, "data": data, "files": files}
        )
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture(autouse=True)
def mock_async_client(monkeypatch: pytest.MonkeyPatch) -> None:
    RecordingAsyncClient.responses = []
    RecordingAsyncClient.calls = []
    RecordingAsyncClient.timeouts = []
    monkeypatch.setattr("app.services.ai.openai_compatible.httpx.AsyncClient", RecordingAsyncClient)


def _provider(
    *, timeout_seconds: int = 15, image_timeout_seconds: int | None = None, max_attempts: int = 2
) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        api_base_url="https://api.openai.com/v1",
        api_key="test-provider-key",
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
        image_timeout_seconds=image_timeout_seconds,
    )


async def _generate(
    provider: OpenAICompatibleProvider,
    *,
    model: str = "gpt-5-mini",
    schema: type[BaseModel] = StructuredOutput,
):
    return await provider.generate_structured(
        capability=AICapability.CHEAP_TEXT_REVISION,
        model=model,
        system_prompt="Return the requested structured result.",
        user_prompt="Revise this campaign.",
        schema=schema,
        context={"campaign_id": "campaign-test-id"},
    )


def _success_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [
                {"message": {"content": json.dumps({"status": "ready", "summary": "Done"})}}
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
            "schema": build_openai_strict_schema(StructuredOutput),
        },
    }


def _schema_nodes(value: object):
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _schema_nodes(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _schema_nodes(nested)


def _allows_null(schema: dict[str, object]) -> bool:
    return any(
        isinstance(option, dict) and option.get("type") == "null"
        for option in schema.get("anyOf", [])
    )


@pytest.mark.asyncio
async def test_ai_revision_provider_schema_is_openai_strict_compatible() -> None:
    RecordingAsyncClient.responses = [_success_response()]

    await _generate(_provider(), schema=AIRevisionParseEnvelope)

    payload = RecordingAsyncClient.calls[0]["json"]
    response_format = payload["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    provider_schema = response_format["json_schema"]["schema"]

    for node in _schema_nodes(provider_schema):
        if "properties" in node:
            assert set(node["required"]) == set(node["properties"])
            assert node["additionalProperties"] is False
        assert "default" not in node
        assert "discriminator" not in node
        assert "oneOf" not in node

    root_properties = provider_schema["properties"]
    for field_name in ("confidence", "clarification_question", "unsupported_reason"):
        assert field_name in provider_schema["required"]
        assert _allows_null(root_properties[field_name])

    update_price = provider_schema["$defs"]["UpdatePriceAction"]
    assert "old_price" in update_price["required"]
    assert _allows_null(update_price["properties"]["old_price"])

    action_items = root_properties["actions"]["items"]
    assert {entry["$ref"].split("/")[-1] for entry in action_items["anyOf"]} == {
        "MoveItemAction",
        "RemoveItemAction",
        "RestoreItemAction",
        "UpdatePriceAction",
        "UpdateDisplayNameAction",
        "SetHeroAction",
        "SetItemEmphasisAction",
        "ReplaceImageAction",
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


async def _professionalize(
    provider: OpenAICompatibleProvider,
    *,
    logo_image: bytes | None = None,
):
    return await provider.professionalize_brochure_image(
        capability=AICapability.BROCHURE_IMAGE_PROFESSIONALIZATION,
        model="configured-image-model",
        system_prompt="Make this brochure professional.",
        immutable_facts={"market_name": "LeafletPilot Market"},
        source_image=b"source-png",
        source_mime_type="image/png",
        logo_image=logo_image,
        logo_mime_type="image/png" if logo_image else None,
    )


@pytest.mark.asyncio
async def test_image_edit_request_omits_response_format_and_preserves_multipart_fields() -> None:
    RecordingAsyncClient.responses = [
        httpx.Response(200, json={"data": [{"b64_json": "Z2VuZXJhdGVkLXBuZw=="}]})
    ]

    result = await _professionalize(_provider(), logo_image=b"logo-png")

    assert result.output == b"generated-png"
    request = RecordingAsyncClient.calls[0]
    assert request["url"] == "https://api.openai.com/v1/images/edits"
    assert request["headers"] == {"Authorization": "Bearer test-provider-key"}
    assert request["data"] == {
        "model": "configured-image-model",
        "prompt": (
            "Make this brochure professional.\n\n"
            "Immutable commercial facts (preserve exactly; these override every visual request):\n"
            '{"market_name":"LeafletPilot Market"}'
        ),
        "size": "1024x1536",
    }
    assert "response_format" not in request["data"]
    assert request["files"] == [
        ("image[]", ("approved-brochure.png", b"source-png", "image/png")),
        ("image[]", ("market-logo", b"logo-png", "image/png")),
    ]


@pytest.mark.asyncio
async def test_image_edit_unknown_parameter_response_is_a_non_retryable_provider_error() -> None:
    RecordingAsyncClient.responses = [
        httpx.Response(
            400,
            json={
                "error": {
                    "type": "invalid_request_error",
                    "code": "unknown_parameter",
                    "param": "response_format",
                    "message": "Unknown parameter: 'response_format'.",
                }
            },
        )
    ]

    with pytest.raises(AIProviderError, match="rejected the request \\(400\\)"):
        await _professionalize(_provider())

    assert len(RecordingAsyncClient.calls) == 1
    assert "response_format" not in RecordingAsyncClient.calls[0]["data"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "error_type"),
    [
        (httpx.Response(401), AIProviderAuthenticationError),
        (httpx.Response(503), AIProviderTransientError),
        (httpx.Response(200, json={"data": [{}]}), AIProviderOutputError),
    ],
)
async def test_image_edit_error_mappings_remain_intact(
    response: httpx.Response, error_type: type[Exception]
) -> None:
    RecordingAsyncClient.responses = [response]

    with pytest.raises(error_type):
        await _professionalize(_provider())


@pytest.mark.asyncio
async def test_image_edit_uses_dedicated_timeout_beyond_generic_sixty_second_ceiling() -> None:
    RecordingAsyncClient.responses = [
        httpx.Response(200, json={"data": [{"b64_json": "Z2VuZXJhdGVkLXBuZw=="}]})
    ]

    await _professionalize(_provider(timeout_seconds=15, image_timeout_seconds=120))

    assert RecordingAsyncClient.timeouts == [120]


@pytest.mark.asyncio
async def test_image_edit_timeout_maps_using_dedicated_timeout() -> None:
    RecordingAsyncClient.responses = [httpx.TimeoutException("slow image generation")]

    with pytest.raises(AIProviderTimeoutError):
        await _professionalize(_provider(timeout_seconds=15, image_timeout_seconds=121))

    assert RecordingAsyncClient.timeouts == [121]
