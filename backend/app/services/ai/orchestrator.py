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

async def _professionalize_brochure_image(self: AIOrchestrator, *, capability: AICapability, system_prompt: str, immutable_facts: dict[str, Any], source_image: bytes, source_mime_type: str, logo_image: bytes | None = None, logo_mime_type: str | None = None) -> AIInvocationResult:
    last_error: AIProviderTransientError | None = None
    for route in self._router.routes_for(capability):
        provider = self._registry.get(route.provider)
        method = getattr(provider, "professionalize_brochure_image", None)
        if method is None:
            continue
        started = perf_counter()
        try:
            result = await method(capability=capability, model=route.model, system_prompt=system_prompt, immutable_facts=immutable_facts, source_image=source_image, source_mime_type=source_mime_type, logo_image=logo_image, logo_mime_type=logo_mime_type)
            if not isinstance(result.output, bytes) or not result.output:
                raise AIProviderOutputError("AI provider did not return a brochure image.", provider=route.provider, model=route.model)
            return AIInvocationResult(output=result.output, capability=capability, provider=route.provider, model=route.model, latency_ms=max(0, round((perf_counter() - started) * 1000)), usage=result.usage)
        except AIProviderTransientError as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise AIProviderTransientError("No configured provider supports brochure image professionalization.")


AIOrchestrator.professionalize_brochure_image = _professionalize_brochure_image