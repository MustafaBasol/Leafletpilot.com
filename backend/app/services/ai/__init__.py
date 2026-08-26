"""Provider-neutral AI orchestration for bounded, structured tasks."""

from app.services.ai.dependencies import get_ai_revision_service
from app.services.ai.types import AICapability

__all__ = ["AICapability", "get_ai_revision_service"]
