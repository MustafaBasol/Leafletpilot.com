from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.services.ai.openai_compatible import OpenAICompatibleProvider
from app.services.ai.orchestrator import AIOrchestrator
from app.services.ai.professionalization import AIProfessionalizationService
from app.services.ai.registry import AIProviderRegistry
from app.services.ai.revision_parser import AIRevisionService
from app.services.ai.router import AIModelRouter
from app.services.ai.types import AICapability, AIModelRoute


@lru_cache
def get_ai_revision_service() -> AIRevisionService:
    registry = AIProviderRegistry()
    registry.register(
        OpenAICompatibleProvider(
            api_base_url=settings.ai_openai_compatible_api_base_url,
            api_key=settings.ai_openai_compatible_api_key.get_secret_value(),
            timeout_seconds=settings.ai_http_timeout_seconds,
            max_attempts=settings.ai_http_max_attempts,
        )
    )

    def configured_routes(provider: str, model: str) -> list[AIModelRoute]:
        routes = [AIModelRoute(AICapability.CHEAP_TEXT_REVISION, provider, model)]
        if settings.ai_fallback_provider and settings.ai_fallback_model:
            routes.append(
                AIModelRoute(
                    AICapability.CHEAP_TEXT_REVISION,
                    settings.ai_fallback_provider,
                    settings.ai_fallback_model,
                )
            )
        return routes

    cheap_routes = configured_routes(settings.ai_revision_provider, settings.ai_revision_model)
    complex_provider = settings.ai_complex_revision_provider or settings.ai_revision_provider
    complex_model = settings.ai_complex_revision_model or settings.ai_revision_model
    complex_routes = [
        AIModelRoute(AICapability.COMPLEX_TEXT_REVISION, route.provider, route.model)
        for route in configured_routes(complex_provider, complex_model)
    ]
    router = AIModelRouter(
        {
            AICapability.CHEAP_TEXT_REVISION: cheap_routes,
            AICapability.COMPLEX_TEXT_REVISION: complex_routes,
        }
    )
    return AIRevisionService(AIOrchestrator(registry, router))


@lru_cache
def get_ai_professionalization_service() -> AIProfessionalizationService:
    registry = AIProviderRegistry()
    registry.register(
        OpenAICompatibleProvider(
            api_base_url=settings.ai_openai_compatible_api_base_url,
            api_key=settings.ai_openai_compatible_api_key.get_secret_value(),
            timeout_seconds=settings.ai_http_timeout_seconds,
            max_attempts=settings.ai_http_max_attempts,
        )
    )
    provider = settings.ai_professionalization_provider or settings.ai_revision_provider
    model = settings.ai_professionalization_model or settings.ai_revision_model
    routes = [AIModelRoute(AICapability.COMPLEX_DESIGN_ANALYSIS, provider, model)]
    if settings.ai_professionalization_fallback_provider and settings.ai_professionalization_fallback_model:
        routes.append(AIModelRoute(AICapability.COMPLEX_DESIGN_ANALYSIS, settings.ai_professionalization_fallback_provider, settings.ai_professionalization_fallback_model))
    return AIProfessionalizationService(AIOrchestrator(registry, AIModelRouter({AICapability.COMPLEX_DESIGN_ANALYSIS: routes})))