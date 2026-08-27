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


ProfessionalizationStatus = Literal["ready", "applied", "superseded", "failed"]


class ProfessionalizationRequest(BaseModel):
    """Explicit request only; no commercial facts are accepted from the client."""

    model_config = ConfigDict(extra="forbid")

    client_request_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    design_goal: str | None = Field(default=None, max_length=300)


class ProfessionalizationEmphasis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position: int = Field(ge=1, le=16)
    treatment: Literal["featured", "support"]


class AIProfessionalizationPlanEnvelope(BaseModel):
    """Strict, bounded design-direction contract consumed by our renderer."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ready", "unsupported"]
    header_style: Literal["burst", "band", "minimal"] | None = None
    card_style: Literal["shadow", "outlined", "rounded"] | None = None
    price_style: Literal["panel", "ticket", "split"] | None = None
    badge_style: Literal["pill", "sticker", "burst", "ribbon"] | None = None
    image_treatment: Literal["stage", "cutout", "photo"] | None = None
    price_prominence: Literal["normal", "high"] = "normal"
    headline_emphasis: Literal["normal", "high"] = "normal"
    emphasis: list[ProfessionalizationEmphasis] = Field(default_factory=list, max_length=3)
    rationale: list[str] = Field(default_factory=list, max_length=4)
    unsupported_reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_status_contract(self) -> AIProfessionalizationPlanEnvelope:
        visual_fields = (self.header_style, self.card_style, self.price_style, self.badge_style, self.image_treatment)
        if self.status == "ready" and not any(visual_fields) and not self.emphasis:
            raise ValueError("ready output requires a bounded visual treatment")
        if self.status == "unsupported" and (self.emphasis or not self.unsupported_reason):
            raise ValueError("unsupported output requires a reason and no emphasis")
        if len({entry.position for entry in self.emphasis}) != len(self.emphasis):
            raise ValueError("emphasis positions must be unique")
        return self


class ProfessionalizationRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    campaign_id: UUID
    snapshot_hash: str
    provider: str
    model: str
    status: ProfessionalizationStatus
    is_active: bool
    plan: AIProfessionalizationPlanEnvelope
    summary: list[str]
    applied_at: datetime | None
    created_at: datetime
    idempotent: bool = False


class ProfessionalizationApplyResult(BaseModel):
    run: ProfessionalizationRunRead
    original_available: bool = True


class ProfessionalizationHistoryRead(BaseModel):
    active_run_id: UUID | None = None
    original_available: bool = True
    runs: list[ProfessionalizationRunRead] = Field(default_factory=list)