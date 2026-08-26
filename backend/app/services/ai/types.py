from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class AICapability(StrEnum):
    CHEAP_TEXT_REVISION = "cheap_text_revision"
    COMPLEX_TEXT_REVISION = "complex_text_revision"
    VISION_REASONING = "vision_reasoning"
    COMPLEX_DESIGN_ANALYSIS = "complex_design_analysis"
    IMAGE_GENERATION = "image_generation"
    IMAGE_EDITING = "image_editing"


@dataclass(frozen=True)
class AIModelRoute:
    capability: AICapability
    provider: str
    model: str


@dataclass(frozen=True)
class AIProviderUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True)
class AIProviderResult:
    output: Any
    usage: AIProviderUsage = AIProviderUsage()


@dataclass(frozen=True)
class AIInvocationResult:
    output: Any
    capability: AICapability
    provider: str
    model: str
    latency_ms: int
    usage: AIProviderUsage
