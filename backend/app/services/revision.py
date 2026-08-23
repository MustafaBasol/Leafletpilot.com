"""Deterministic, audited mutations for a campaign brochure draft.

This service deliberately accepts only validated structured commands.  A future
AI intent parser may construct those commands, but it never owns layout or
persists arbitrary campaign fields.
"""

from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Campaign, CampaignItem, CampaignRevision, ProductImage
from app.schemas.revision import (
    MoveItemAction,
    RemoveItemAction,
    ReplaceImageAction,
    RestoreItemAction,
    RevisionAction,
    RevisionCommand,
    SetHeroAction,
    SetItemEmphasisAction,
    UndoRevisionRequest,
    UpdateDisplayNameAction,
    UpdatePriceAction,
)
from app.services.campaign import (
    _clear_applied_intelligence,
    advance_draft_revision,
    canonical_request_fingerprint,
    capture_campaign_draft_state,
    recalculate_campaign_counts,
)


@dataclass(frozen=True)
class RevisionApplication:
    revision: CampaignRevision
    draft_revision: int
    idempotent: bool = False


async def apply_revision(
    session: AsyncSession,
    campaign_id: UUID,
    command: RevisionCommand,
    market_id: UUID,
    *,
    actor_id: UUID | None,
) -> RevisionApplication:
    """Apply all requested actions and their audit event in one transaction."""
    try:
        actions_json = [action.model_dump(mode="json") for action in command.actions]
        fingerprint = canonical_request_fingerprint(
            source=command.source,
            expected_revision=command.expected_revision,
            actions=actions_json,
        )
        campaign = await _get_locked_campaign(session, campaign_id, market_id)
        existing = await _find_by_request_id(session, campaign.id, campaign.market_id, command.client_request_id)
        if existing is not None:
            if existing.request_fingerprint != fingerprint:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="client_request_id was already used for a different revision request.",
                )
            return RevisionApplication(existing, campaign.draft_revision, idempotent=True)
        _assert_mutable(campaign)
        _assert_expected_revision(campaign, command.expected_revision)

        before = capture_campaign_draft_state(campaign)
        for action in command.actions:
            await _apply_action(session, campaign, action)
        _normalize_sort_order(campaign.items)
        recalculate_campaign_counts(campaign)
        _clear_applied_intelligence(campaign)
        if campaign.status in {"preview_ready", "waiting_approval", "revision_requested"}:
            campaign.status = "waiting_approval"
        after = capture_campaign_draft_state(campaign)
        revision = advance_draft_revision(
            session,
            campaign,
            actor_id=actor_id,
            source=command.source,
            request_id=command.client_request_id,
            request_fingerprint=fingerprint,
            actions=actions_json,
            before_snapshot=before,
            after_snapshot=after,
        )
        await session.commit()
        await session.refresh(revision)
        return RevisionApplication(revision, campaign.draft_revision)
    except IntegrityError as exc:
        await session.rollback()
        # The campaign row lock handles ordinary concurrency; this is a final
        # database-level guard for an idempotency or sequence race.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Revision request conflicts with current draft.") from exc
    except HTTPException:
        await session.rollback()
        raise
    except Exception:
        await session.rollback()
        raise


async def undo_latest_revision(
    session: AsyncSession,
    campaign_id: UUID,
    request: UndoRevisionRequest,
    market_id: UUID,
    *,
    actor_id: UUID | None,
) -> RevisionApplication:
    """Restore the immediately preceding mutation and record the undo itself."""
    try:
        campaign = await _get_locked_campaign(session, campaign_id, market_id)
        undo_actions = [{"type": "undo"}]
        fingerprint = canonical_request_fingerprint(
            source=request.source,
            expected_revision=request.expected_revision,
            actions=undo_actions,
        )
        existing = await _find_by_request_id(session, campaign.id, campaign.market_id, request.client_request_id)
        if existing is not None:
            if existing.request_fingerprint != fingerprint:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="client_request_id was already used for a different undo request.",
                )
            return RevisionApplication(existing, campaign.draft_revision, idempotent=True)
        _assert_mutable(campaign)
        _assert_expected_revision(campaign, request.expected_revision)
        latest = await session.scalar(
            select(CampaignRevision)
            .where(CampaignRevision.campaign_id == campaign.id, CampaignRevision.market_id == campaign.market_id)
            .order_by(CampaignRevision.sequence.desc())
            .with_for_update()
            .limit(1)
        )
        if latest is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="There is no revision to undo.")
        if latest.status == "undone" or latest.source == "system":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The latest effective draft mutation cannot be undone again.",
            )

        before = capture_campaign_draft_state(campaign)
        _restore_draft_state(campaign, latest.before_snapshot_json)
        recalculate_campaign_counts(campaign)
        _clear_applied_intelligence(campaign)
        after = capture_campaign_draft_state(campaign)
        applied_undo_actions = [{"type": "undo", "target_revision_id": str(latest.id)}]
        revision = advance_draft_revision(
            session,
            campaign,
            actor_id=actor_id,
            source=request.source,
            request_id=request.client_request_id,
            request_fingerprint=fingerprint,
            actions=applied_undo_actions,
            before_snapshot=before,
            after_snapshot=after,
            status_value="undone",
            reverts_revision_id=latest.id,
        )
        await session.commit()
        await session.refresh(revision)
        return RevisionApplication(revision, campaign.draft_revision)
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Undo conflicts with current draft.") from exc
    except HTTPException:
        await session.rollback()
        raise
    except Exception:
        await session.rollback()
        raise


async def list_revisions(session: AsyncSession, campaign_id: UUID, market_id: UUID) -> list[CampaignRevision]:
    """Return only the requesting market's revision ledger."""
    campaign = await session.scalar(
        select(Campaign.id).where(Campaign.id == campaign_id, Campaign.market_id == market_id)
    )
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found.")
    rows = await session.scalars(
        select(CampaignRevision)
        .where(CampaignRevision.campaign_id == campaign_id, CampaignRevision.market_id == market_id)
        .order_by(CampaignRevision.sequence.desc())
    )
    return list(rows)


async def _get_locked_campaign(session: AsyncSession, campaign_id: UUID, market_id: UUID) -> Campaign:
    campaign = await session.scalar(
        select(Campaign)
        .options(
            selectinload(Campaign.template),
            selectinload(Campaign.items).selectinload(CampaignItem.image_override),
        )
        .where(Campaign.id == campaign_id, Campaign.market_id == market_id)
        .with_for_update()
    )
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found.")
    return campaign


async def _find_by_request_id(
    session: AsyncSession, campaign_id: UUID, market_id: UUID, request_id: str
) -> CampaignRevision | None:
    return await session.scalar(
        select(CampaignRevision).where(
            CampaignRevision.campaign_id == campaign_id,
            CampaignRevision.market_id == market_id,
            CampaignRevision.request_id == request_id,
        )
    )


def _assert_mutable(campaign: Campaign) -> None:
    if campaign.frozen_at is not None or campaign.finalized_at is not None or campaign.status in {
        "approved", "generating_files", "completed", "cancelled"
    }:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Approved campaigns are immutable; create a new revision cycle first.",
        )


def _assert_expected_revision(campaign: Campaign, expected_revision: int) -> None:
    if campaign.draft_revision != expected_revision:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "Draft revision is stale.", "current_revision": campaign.draft_revision},
        )


async def _apply_action(session: AsyncSession, campaign: Campaign, action: RevisionAction) -> None:
    item = _item(campaign.items, action.item_id)
    if isinstance(action, MoveItemAction):
        visible = [candidate for candidate in _ordered(campaign.items) if not bool(candidate.is_hidden)]
        if item.is_hidden or action.target_position > len(visible):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid target position.")
        visible.remove(item)
        visible.insert(action.target_position - 1, item)
        hidden = [candidate for candidate in _ordered(campaign.items) if bool(candidate.is_hidden)]
        for position, candidate in enumerate(visible):
            candidate.sort_order = position
        for position, candidate in enumerate(hidden, start=len(visible)):
            candidate.sort_order = position
    elif isinstance(action, RemoveItemAction):
        item.is_hidden = True
        item.is_hero = False
        if item.emphasis == "hero":
            item.emphasis = "normal"
    elif isinstance(action, RestoreItemAction):
        item.is_hidden = False
    elif isinstance(action, UpdatePriceAction):
        item.price = action.price
        if "old_price" in action.model_fields_set:
            item.old_price = action.old_price
    elif isinstance(action, UpdateDisplayNameAction):
        item.display_name = action.display_name
    elif isinstance(action, SetHeroAction):
        _set_hero(campaign, item, action.is_hero)
    elif isinstance(action, SetItemEmphasisAction):
        item.emphasis = action.emphasis
        _set_hero(campaign, item, action.emphasis == "hero")
    elif isinstance(action, ReplaceImageAction):
        image = await _visible_image(session, item, action.image_id)
        item.image_override_product_image_id = image.id
    else:  # Pydantic's discriminated union makes this defensive branch unreachable.
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported revision action.")


def _set_hero(campaign: Campaign, selected: CampaignItem, is_hero: bool) -> None:
    if is_hero:
        for item in campaign.items:
            item.is_hero = item.id == selected.id
            if item.id != selected.id and item.emphasis == "hero":
                item.emphasis = "normal"
        selected.emphasis = "hero"
    else:
        selected.is_hero = False
        if selected.emphasis == "hero":
            selected.emphasis = "normal"


async def _visible_image(session: AsyncSession, item: CampaignItem, image_id: UUID) -> ProductImage:
    if item.product_id is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="This item has no catalog product image.")
    image = await session.scalar(
        select(ProductImage).where(
            ProductImage.id == image_id,
            ProductImage.product_id == item.product_id,
            ProductImage.storage_key.is_not(None),
            ProductImage.quality_status.notin_(("missing", "rejected")),
        )
    )
    if image is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Image is not a safe asset for this item.")
    return image


def _item(items: Iterable[CampaignItem], item_id: UUID) -> CampaignItem:
    item = next((candidate for candidate in items if candidate.id == item_id), None)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign item not found.")
    return item


def _ordered(items: Iterable[CampaignItem]) -> list[CampaignItem]:
    return sorted(items, key=lambda item: (item.sort_order, str(item.id)))


def _normalize_sort_order(items: Iterable[CampaignItem]) -> None:
    for position, item in enumerate(_ordered(items)):
        item.sort_order = position


def _draft_state(campaign: Campaign) -> dict:
    return {
        "status": campaign.status,
        "builder_config": deepcopy(campaign.builder_config_json or {}),
        "items": [
            {
                "id": str(item.id),
                "display_name": item.display_name,
                "price": str(item.price) if item.price is not None else None,
                "old_price": str(item.old_price) if item.old_price is not None else None,
                "sort_order": item.sort_order,
                "is_hidden": item.is_hidden,
                "is_hero": item.is_hero,
                "emphasis": item.emphasis,
                "image_override_product_image_id": str(item.image_override_product_image_id)
                if item.image_override_product_image_id
                else None,
            }
            for item in _ordered(campaign.items)
        ],
    }


def _restore_draft_state(campaign: Campaign, state: dict) -> None:
    by_id = {str(item.id): item for item in campaign.items}
    for saved in state.get("items", []):
        item = by_id.get(str(saved.get("id")))
        if item is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot safely restore missing campaign item.")
        item.display_name = saved.get("display_name")
        item.price = Decimal(saved["price"]) if saved.get("price") is not None else None
        item.old_price = Decimal(saved["old_price"]) if saved.get("old_price") is not None else None
        item.sort_order = int(saved.get("sort_order", 0))
        item.is_hidden = bool(saved.get("is_hidden", False))
        item.is_hero = bool(saved.get("is_hero", False))
        item.emphasis = str(saved.get("emphasis") or "normal")
        image_id = saved.get("image_override_product_image_id")
        item.image_override_product_image_id = UUID(image_id) if image_id else None
    campaign.builder_config_json = deepcopy(state.get("builder_config") or {})
    campaign.status = str(state.get("status") or campaign.status)
    _normalize_sort_order(campaign.items)




async def list_item_image_options(
    session: AsyncSession,
    campaign_id: UUID,
    item_id: UUID,
    market_id: UUID,
) -> tuple[CampaignItem, list[ProductImage]]:
    """List only safe catalog assets belonging to this campaign item product."""
    campaign = await session.scalar(
        select(Campaign)
        .options(selectinload(Campaign.items))
        .where(Campaign.id == campaign_id, Campaign.market_id == market_id)
    )
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found.")
    item = _item(campaign.items, item_id)
    if item.product_id is None:
        return item, []
    rows = await session.scalars(
        select(ProductImage)
        .where(
            ProductImage.product_id == item.product_id,
            ProductImage.storage_key.is_not(None),
            ProductImage.quality_status.notin_(("missing", "rejected")),
        )
        .order_by(ProductImage.is_primary.desc(), ProductImage.created_at.asc())
    )
    return item, list(rows)
