from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from pydantic import BaseModel

from app.services.ai.types import AICapability, AIProviderResult


class AIProvider(Protocol):
    name: str

    async def generate_structured(
        self,
        *,
        capability: AICapability,
        model: str,
        system_prompt: str,
        user_prompt: str,
        schema: type[BaseModel],
        context: dict[str, Any] | None = None,
    ) -> AIProviderResult: ...


class MockAIProvider:
    """Deterministic provider for unit and API tests; never registered in production."""

    name = "mock"

    def __init__(self, responses: Sequence[AIProviderResult | Exception | dict[str, Any]]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

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
        self.calls.append(
            {
                "capability": capability,
                "model": model,
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "schema": schema,
                "context": context,
            }
        )
        if not self._responses:
            raise RuntimeError("MockAIProvider has no queued response.")
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        if isinstance(response, AIProviderResult):
            return response
        return AIProviderResult(output=response)
