from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from typing import Any

import httpx
from pydantic import BaseModel

from app.services.ai.errors import (
    AIConfigurationError,
    AIProviderAuthenticationError,
    AIProviderError,
    AIProviderOutputError,
    AIProviderTimeoutError,
    AIProviderTransientError,
)
from app.services.ai.types import AICapability, AIProviderResult, AIProviderUsage


def build_openai_strict_schema(schema: type[BaseModel]) -> dict[str, Any]:
    """Project a Pydantic schema into OpenAI's strict Structured Outputs subset.

    Pydantic remains the source of truth for runtime validation. This projection
    only adapts its JSON Schema for the provider: OpenAI requires closed objects
    whose every property is required, and represents optional values with null.
    """

    return _make_openai_strict_schema(deepcopy(schema.model_json_schema()))


def _make_openai_strict_schema(value: Any) -> Any:
    if isinstance(value, list):
        return [_make_openai_strict_schema(item) for item in value]
    if not isinstance(value, dict):
        return value

    strict_schema = {
        key: _make_openai_strict_schema(item)
        for key, item in value.items()
        # Defaults are authoring hints, not strict-output validation rules.
        # The provider must emit every property, including nullable ones.
        if key not in {"default", "discriminator"}
    }

    # OpenAI's strict subset supports anyOf, not oneOf. Pydantic emits oneOf
    # for discriminated unions; their literal discriminator makes branches
    # mutually exclusive, so anyOf preserves the contract.
    one_of = strict_schema.pop("oneOf", None)
    if one_of is not None:
        if "anyOf" in strict_schema:
            raise ValueError("OpenAI strict schema cannot combine oneOf and anyOf.")
        strict_schema["anyOf"] = one_of

    if strict_schema.get("type") == "object":
        strict_schema["additionalProperties"] = False

    properties = strict_schema.get("properties")
    if isinstance(properties, dict):
        strict_schema["required"] = list(properties)

    return strict_schema


class OpenAICompatibleProvider:
    """Isolated adapter for OpenAI-compatible structured chat-completion APIs."""

    name = "openai_compatible"

    def __init__(
        self,
        *,
        api_base_url: str,
        api_key: str,
        timeout_seconds: int,
        max_attempts: int,
    ) -> None:
        self._api_base_url = api_base_url.rstrip("/")
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._max_attempts = max(1, min(max_attempts, 2))

    async def generate_structured(
        self,
        *,
        capability: AICapability,
        model: str,
        system_prompt: str,
        user_prompt: str,
        schema: type[BaseModel],
        context: dict[str, Any] | None = None,
    ) -> AIProviderResult:
        if not self._api_base_url or not self._api_key or not model:
            raise AIConfigurationError(
                "OpenAI-compatible provider configuration is incomplete.",
                provider=self.name,
                model=model,
            )
        user_content = json.dumps(
            {"instruction": user_prompt, "context": context or {}},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "strict": True,
                    "schema": build_openai_strict_schema(schema),
                },
            },
        }
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        for attempt in range(self._max_attempts):
            try:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    response = await client.post(
                        f"{self._api_base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    )
            except httpx.TimeoutException as exc:
                if attempt + 1 < self._max_attempts:
                    await asyncio.sleep(0)
                    continue
                raise AIProviderTimeoutError(
                    "AI provider timed out.", provider=self.name, model=model
                ) from exc
            except httpx.HTTPError as exc:
                if attempt + 1 < self._max_attempts:
                    await asyncio.sleep(0)
                    continue
                raise AIProviderTransientError(
                    "AI provider network failure.", provider=self.name, model=model
                ) from exc

            if response.status_code in {401, 403}:
                raise AIProviderAuthenticationError(
                    "AI provider authentication failed.", provider=self.name, model=model
                )
            if response.status_code in {408, 429} or response.status_code >= 500:
                if attempt + 1 < self._max_attempts:
                    await asyncio.sleep(0)
                    continue
                raise AIProviderTransientError(
                    "AI provider is temporarily unavailable.", provider=self.name, model=model
                )
            if response.is_error:
                raise AIProviderError(
                    f"AI provider rejected the request ({response.status_code}).",
                    provider=self.name,
                    model=model,
                )
            try:
                body = response.json()
                content = body["choices"][0]["message"]["content"]
                output = json.loads(content) if isinstance(content, str) else content
                usage = body.get("usage") or {}
                return AIProviderResult(
                    output=output,
                    usage=AIProviderUsage(
                        input_tokens=usage.get("prompt_tokens"),
                        output_tokens=usage.get("completion_tokens"),
                    ),
                )
            except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise AIProviderOutputError(
                    "AI provider returned malformed structured output.",
                    provider=self.name,
                    model=model,
                ) from exc
        raise AIProviderTransientError(
            "AI provider is temporarily unavailable.", provider=self.name, model=model
        )

async def _professionalize_brochure_image(self: OpenAICompatibleProvider, *, capability: AICapability, model: str, system_prompt: str, immutable_facts: dict[str, Any], source_image: bytes, source_mime_type: str, logo_image: bytes | None = None, logo_mime_type: str | None = None) -> AIProviderResult:
    """OpenAI-compatible image edit adapter; unsupported endpoints fail closed."""
    if not self._api_base_url or not self._api_key or not model:
        raise AIConfigurationError("Image professionalization configuration is incomplete.", provider=self.name, model=model)
    prompt = system_prompt + "\\n\\nImmutable commercial facts (preserve exactly):\\n" + json.dumps(immutable_facts, ensure_ascii=False, separators=(",", ":"))
    files: list[tuple[str, tuple[str, bytes, str]]] = [("image[]", ("approved-brochure.png", source_image, source_mime_type))]
    if logo_image and logo_mime_type:
        files.append(("image[]", ("market-logo", logo_image, logo_mime_type)))
    try:
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.post(f"{self._api_base_url}/images/edits", headers={"Authorization": f"Bearer {self._api_key}"}, data={"model": model, "prompt": prompt, "size": "1024x1536"}, files=files)
    except httpx.TimeoutException as exc:
        raise AIProviderTimeoutError("AI image provider timed out.", provider=self.name, model=model) from exc
    except httpx.HTTPError as exc:
        raise AIProviderTransientError("AI image provider network failure.", provider=self.name, model=model) from exc
    if response.status_code in {401, 403}:
        raise AIProviderAuthenticationError("AI image provider authentication failed.", provider=self.name, model=model)
    if response.status_code in {404, 405, 408, 429} or response.status_code >= 500:
        raise AIProviderTransientError("AI image professionalization is unavailable.", provider=self.name, model=model)
    if response.is_error:
        raise AIProviderError(f"AI image provider rejected the request ({response.status_code}).", provider=self.name, model=model)
    try:
        import base64
        body = response.json(); image = base64.b64decode(body["data"][0]["b64_json"], validate=True)
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AIProviderOutputError("AI image provider returned malformed image output.", provider=self.name, model=model) from exc
    return AIProviderResult(output=image, usage=AIProviderUsage(input_tokens=(body.get("usage") or {}).get("input_tokens"), output_tokens=(body.get("usage") or {}).get("output_tokens")))


OpenAICompatibleProvider.professionalize_brochure_image = _professionalize_brochure_image