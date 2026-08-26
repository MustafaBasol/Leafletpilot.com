from __future__ import annotations

from time import perf_counter
from typing import Any

from pydantic import BaseModel, ValidationError

from app.services.ai.errors import AIProviderOutputError, AIProviderTransientError
from app.services.ai.registry import AIProviderRegistry
from app.services.ai.router import AIModelRouter
from app.services.ai.types import AICapability, AIInvocationResult


class AIOrchestrator:
    def __init__(self, registry: AIProviderRegistry, router: AIModelRouter) -> None:
        self._registry = registry
        self._router = router

    async def generate_structured(
        self,
        *,
        capability: AICapability,
        system_prompt: str,
        user_prompt: str,
        schema: type[BaseModel],
        context: dict[str, Any],
    ) -> AIInvocationResult:
        routes = self._router.routes_for(capability)
        last_error: AIProviderTransientError | None = None
        for route in routes:
            started = perf_counter()
            provider = self._registry.get(route.provider)
            try:
                result = await provider.generate_structured(
                    capability=capability,
                    model=route.model,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    schema=schema,
                    context=context,
                )
                try:
                    parsed = schema.model_validate(result.output)
                except ValidationError as exc:
                    raise AIProviderOutputError(
                        "AI provider output failed schema validation.",
                        provider=route.provider,
                        model=route.model,
                    ) from exc
                return AIInvocationResult(
                    output=parsed,
                    capability=capability,
                    provider=route.provider,
                    model=route.model,
                    latency_ms=max(0, round((perf_counter() - started) * 1000)),
                    usage=result.usage,
                )
            except AIProviderTransientError as exc:
                last_error = exc
                continue
        if last_error is not None:
            raise last_error
        raise RuntimeError("AI router returned no usable route.")
