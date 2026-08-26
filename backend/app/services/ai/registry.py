from __future__ import annotations

from app.services.ai.errors import AIConfigurationError
from app.services.ai.provider import AIProvider


class AIProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, AIProvider] = {}

    def register(self, provider: AIProvider) -> None:
        self._providers[provider.name] = provider

    def get(self, name: str) -> AIProvider:
        provider = self._providers.get(name)
        if provider is None:
            raise AIConfigurationError(f"AI provider '{name}' is not registered.", provider=name)
        return provider
