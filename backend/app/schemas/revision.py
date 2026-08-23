from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

RevisionSource = Literal["panel", "telegram", "whatsapp", "ai", "system"]
RevisionStatus = Literal["applied", "undone"]
ItemEmphasis = Literal["normal", "large", "hero"]


class MoveItemAction(BaseModel):
    type: Literal["move_item"]
    item_id: UUID
    target_position: int = Field(ge=1)


class RemoveItemAction(BaseModel):
    type: Literal["remove_item"]
    item_id: UUID


class RestoreItemAction(BaseModel):
    type: Literal["restore_item"]
    item_id: UUID


class UpdatePriceAction(BaseModel):
    type: Literal["update_price"]
    item_id: UUID
    price: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    old_price: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)


class UpdateDisplayNameAction(BaseModel):
    type: Literal["update_display_name"]
    item_id: UUID
    display_name: str = Field(min_length=1, max_length=255)


class SetHeroAction(BaseModel):
    type: Literal["set_hero"]
    item_id: UUID
    is_hero: bool


class SetItemEmphasisAction(BaseModel):
    type: Literal["set_item_emphasis"]
    item_id: UUID
    emphasis: ItemEmphasis


class ReplaceImageAction(BaseModel):
    type: Literal["replace_image"]
    item_id: UUID
    image_id: UUID


RevisionAction = Annotated[
    MoveItemAction
    | RemoveItemAction
    | RestoreItemAction
    | UpdatePriceAction
    | UpdateDisplayNameAction
    | SetHeroAction
    | SetItemEmphasisAction
    | ReplaceImageAction,
    Field(discriminator="type"),
]


class RevisionCommand(BaseModel):
    client_request_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    source: RevisionSource
    expected_revision: int = Field(ge=0)
    actions: list[RevisionAction] = Field(min_length=1, max_length=100)


class PanelRevisionCommand(BaseModel):
    """Public panel contract. The API, not the browser, owns the source."""

    model_config = ConfigDict(extra="forbid")

    client_request_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    expected_revision: int = Field(ge=0)
    actions: list[RevisionAction] = Field(min_length=1, max_length=100)

    def trusted_command(self) -> RevisionCommand:
        return RevisionCommand(
            client_request_id=self.client_request_id,
            source="panel",
            expected_revision=self.expected_revision,
            actions=self.actions,
        )


class UndoRevisionRequest(BaseModel):
    client_request_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    expected_revision: int = Field(ge=0)
    source: RevisionSource = "panel"


class PanelUndoRevisionRequest(BaseModel):
    """Public panel undo contract. The source is always server-owned panel."""

    model_config = ConfigDict(extra="forbid")

    client_request_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    expected_revision: int = Field(ge=0)

    def trusted_request(self) -> UndoRevisionRequest:
        return UndoRevisionRequest(
            client_request_id=self.client_request_id,
            expected_revision=self.expected_revision,
            source="panel",
        )


class CampaignApprovalRequest(BaseModel):
    """Approval is an optimistic-concurrency operation, never a blind freeze."""

    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=0)


class CampaignRevisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    campaign_id: UUID
    market_id: UUID
    created_by_user_id: UUID | None
    source: RevisionSource
    request_id: str
    request_fingerprint: str
    sequence: int
    status: RevisionStatus
    actions_json: list[dict]
    before_snapshot_json: dict
    after_snapshot_json: dict
    reverts_revision_id: UUID | None
    created_at: datetime


class RevisionResult(BaseModel):
    revision: CampaignRevisionRead
    draft_revision: int = Field(ge=0)
    idempotent: bool = False


class CampaignItemImageOptionRead(BaseModel):
    id: UUID
    label: str
    is_primary: bool
    is_selected: bool
