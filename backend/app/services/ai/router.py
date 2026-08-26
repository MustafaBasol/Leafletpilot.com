from __future__ import annotations

import re

from app.services.ai.errors import AIUnsupportedCapabilityError
from app.services.ai.types import AICapability, AIModelRoute

_COMPLEX_MARKERS = (
    "grupla",
    "topla",
    "ürünleri",
    "produits",
    "regroupe",
    "group ",
    "items",
    "en dikkat çekici",
    "most eye-catching",
)
_CONJUNCTIONS = re.compile(r"\b(ve|and|et|puis|sonra|then)\b", re.IGNORECASE)


def classify_revision_capability(instruction: str) -> AICapability:
    normalized = " ".join(instruction.casefold().split())
    if any(marker in normalized for marker in _COMPLEX_MARKERS) or len(_CONJUNCTIONS.findall(normalized)) >= 2:
        return AICapability.COMPLEX_TEXT_REVISION
    return AICapability.CHEAP_TEXT_REVISION


class AIModelRouter:
    def __init__(self, routes: dict[AICapability, list[AIModelRoute]]) -> None:
        self._routes = routes

    def routes_for(self, capability: AICapability) -> list[AIModelRoute]:
        routes = [route for route in self._routes.get(capability, []) if route.provider and route.model]
        if not routes:
            raise AIUnsupportedCapabilityError(
                f"No configured route supports capability '{capability.value}'."
            )
        return routes
