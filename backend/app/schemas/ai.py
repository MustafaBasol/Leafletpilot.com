from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.revision import RevisionAction, RevisionResult

AIProposalStatus = Literal[
    "ready",
    "clarification_required",
    "unsupported",
    "applied",
    "expired",
    "failed",
]


class RevisionIntentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instruction: str = Field(min_length=1, max_length=2000)
    expected_revision: int = Field(ge=0)
    client_request_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")


class AIRevisionParseEnvelope(BaseModel):
    """Strict provider output contract; provider JSON is never trusted directly."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ready", "clarification_required", "unsupported"]
    actions: list[RevisionAction] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)
    clarification_question: str | None = Field(default=None, max_length=1000)
    unsupported_reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_status_contract(self) -> AIRevisionParseEnvelope:
        if self.status == "ready" and not self.actions:
            raise ValueError("ready output requires at least one action")
        if self.status == "clarification_required" and (
            self.actions or not self.clarification_question
        ):
            raise ValueError("clarification output requires only a clarification question")
        if self.status == "unsupported" and (self.actions or not self.unsupported_reason):
            raise ValueError("unsupported output requires only an unsupported reason")
        return self


class AIRevisionProposalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    campaign_id: UUID
    status: AIProposalStatus
    expected_revision: int
    actions: list[RevisionAction]
    summary: list[str]
    clarification_question: str | None
    unsupported_reason: str | None
    expires_at: datetime
    created_at: datetime
    idempotent: bool = False


class AIRevisionApplyResult(BaseModel):
    proposal: AIRevisionProposalRead
    revision: RevisionResult
