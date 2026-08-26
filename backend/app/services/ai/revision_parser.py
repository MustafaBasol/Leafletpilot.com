from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from uuid import UUID

from fastapi import HTTPException, status
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models import AIRevisionProposal, AIUsageEvent, Campaign, CampaignRevision
from app.models.base import utc_now
from app.schemas.ai import (
    AIRevisionApplyResult,
    AIRevisionParseEnvelope,
    AIRevisionProposalRead,
    RevisionIntentRequest,
)
from app.schemas.revision import (
    CampaignRevisionRead,
    MoveItemAction,
    RemoveItemAction,
    ReplaceImageAction,
    RestoreItemAction,
    RevisionAction,
    RevisionCommand,
    RevisionResult,
    SetHeroAction,
    SetItemEmphasisAction,
    UpdateDisplayNameAction,
    UpdatePriceAction,
)
from app.services import revision as revision_service
from app.services.ai.errors import (
    AIConfigurationError,
    AIError,
    AIProviderAuthenticationError,
    AIProviderOutputError,
    AIProviderTimeoutError,
    AIProviderTransientError,
    AIUnsupportedCapabilityError,
)
from app.services.ai.orchestrator import AIOrchestrator
from app.services.ai.prompts import REVISION_SYSTEM_PROMPT
from app.services.ai.router import classify_revision_capability
from app.services.rate_limit import AI_USER_KEY, consume_rate_limit, prune_expired_ai_rate_limits

logger = logging.getLogger(__name__)
_ACTION_LIST_ADAPTER = TypeAdapter(list[RevisionAction])
_PRICE_WORDS = ("fiyat", "price", "prix", "euro", "eur", "€")
_OLD_PRICE_WORDS = ("eski fiyat", "old price", "ancien prix", "prix barré", "prix barre")
_RENAME_WORDS = ("adını", "adini", "rename", "renommer", "change the name", "nomunu")
_NUMBER_PATTERN = re.compile(r"(?<!\w)\d+(?:[.,]\d{1,2})?(?!\w)")


class AIRevisionService:
    def __init__(self, orchestrator: AIOrchestrator) -> None:
        self._orchestrator = orchestrator

    async def create_proposal(
        self,
        session: AsyncSession,
        *,
        campaign_id: UUID,
        market_id: UUID,
        user_id: UUID,
        request: RevisionIntentRequest,
    ) -> AIRevisionProposalRead:
        self._assert_feature_enabled()
        instruction = request.instruction.strip()
        if len(instruction) > settings.ai_max_instruction_length:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "instruction_too_long", "message": "AI instruction is too long."},
            )
        fingerprint = _request_fingerprint(campaign_id, request.expected_revision, instruction)
        existing = await self._find_by_request_id(
            session, market_id=market_id, user_id=user_id, request_id=request.client_request_id
        )
        if existing is not None:
            return self._replayed_proposal(existing, campaign_id, fingerprint)

        campaign = await self._load_campaign(session, campaign_id, market_id)
        _assert_mutable(campaign)
        _assert_expected_revision(campaign, request.expected_revision)

        # Serialize identical client keys before the paid provider call. This
        # transaction-scoped PostgreSQL advisory lock holds no campaign row
        # lock, but prevents concurrent double-clicks from spending twice.
        await session.execute(select(func.pg_advisory_xact_lock(_proposal_lock_key(fingerprint))))
        existing = await self._find_by_request_id(
            session, market_id=market_id, user_id=user_id, request_id=request.client_request_id
        )
        if existing is not None:
            return self._replayed_proposal(existing, campaign_id, fingerprint)

        over_limit = await consume_rate_limit(
            session,
            key_type=AI_USER_KEY,
            raw_value=str(user_id),
            limit=settings.ai_revision_rate_limit_per_minute,
            window_minutes=1,
            purpose="ai_revision",
        )
        await prune_expired_ai_rate_limits(session)
        if over_limit:
            await session.commit()
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={"code": "ai_rate_limited", "message": "Too many AI revision requests. Try again shortly."},
            )

        capability = classify_revision_capability(instruction)
        context = _campaign_context(campaign)
        try:
            invocation = await self._orchestrator.generate_structured(
                capability=capability,
                system_prompt=REVISION_SYSTEM_PROMPT,
                user_prompt=instruction,
                schema=AIRevisionParseEnvelope,
                context=context,
            )
            parsed = invocation.output
            if len(parsed.actions) > settings.ai_max_actions_per_request:
                raise AIProviderOutputError(
                    "AI provider returned too many actions.",
                    provider=invocation.provider,
                    model=invocation.model,
                )
            try:
                _validate_actions(campaign, parsed.actions, instruction)
            except AIProviderOutputError as exc:
                exc.provider = exc.provider or invocation.provider
                exc.model = exc.model or invocation.model
                raise
        except AIError as exc:
            await self._record_failure(
                session,
                market_id=market_id,
                campaign_id=campaign_id,
                user_id=user_id,
                capability=capability.value,
                error=exc,
            )
            raise _provider_http_error(exc) from exc

        proposal = AIRevisionProposal(
            market_id=market_id,
            campaign_id=campaign_id,
            created_by_user_id=user_id,
            client_request_id=request.client_request_id,
            request_fingerprint=fingerprint,
            instruction=instruction,
            expected_revision=request.expected_revision,
            capability=capability.value,
            provider=invocation.provider,
            model=invocation.model,
            status=parsed.status,
            actions_json=[action.model_dump(mode="json") for action in parsed.actions],
            summary_json=_summaries(campaign, parsed.actions),
            clarification_question=parsed.clarification_question,
            unsupported_reason=parsed.unsupported_reason,
            expires_at=utc_now() + timedelta(minutes=settings.ai_proposal_expire_minutes),
        )
        session.add(proposal)
        try:
            await session.flush()
            session.add(
                AIUsageEvent(
                    market_id=market_id,
                    campaign_id=campaign_id,
                    user_id=user_id,
                    proposal_id=proposal.id,
                    capability=capability.value,
                    provider=invocation.provider,
                    model=invocation.model,
                    request_type="revision_intent",
                    status="success",
                    input_tokens=invocation.usage.input_tokens,
                    output_tokens=invocation.usage.output_tokens,
                    latency_ms=invocation.latency_ms,
                )
            )
            await session.commit()
            await session.refresh(proposal)
        except IntegrityError:
            await session.rollback()
            existing = await self._find_by_request_id(
                session, market_id=market_id, user_id=user_id, request_id=request.client_request_id
            )
            if existing is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="AI proposal request conflicts with current state.",
                )
            return self._replayed_proposal(existing, campaign_id, fingerprint)

        logger.info(
            "ai.revision.proposal.%s market_id=%s campaign_id=%s capability=%s provider=%s model=%s latency_ms=%s",
            parsed.status,
            market_id,
            campaign_id,
            capability.value,
            invocation.provider,
            invocation.model,
            invocation.latency_ms,
        )
        return _proposal_read(proposal)

    async def apply_proposal(
        self,
        session: AsyncSession,
        *,
        campaign_id: UUID,
        proposal_id: UUID,
        market_id: UUID,
        user_id: UUID,
    ) -> AIRevisionApplyResult:
        self._assert_feature_enabled()
        proposal = await session.scalar(
            select(AIRevisionProposal)
            .where(
                AIRevisionProposal.id == proposal_id,
                AIRevisionProposal.campaign_id == campaign_id,
                AIRevisionProposal.market_id == market_id,
                AIRevisionProposal.created_by_user_id == user_id,
            )
            .with_for_update()
        )
        if proposal is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI proposal not found.")
        if proposal.status == "applied" and proposal.revision_id is not None:
            revision = await session.scalar(
                select(CampaignRevision).where(
                    CampaignRevision.id == proposal.revision_id,
                    CampaignRevision.campaign_id == campaign_id,
                    CampaignRevision.market_id == market_id,
                )
            )
            if revision is None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Applied proposal is inconsistent.")
            return _apply_result(proposal, revision, revision.sequence, idempotent=True)
        if proposal.status != "ready":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "proposal_not_ready", "message": "Only ready AI proposals can be applied."},
            )
        if proposal.expires_at <= utc_now():
            proposal.status = "expired"
            await session.commit()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "proposal_expired", "message": "AI proposal expired; generate it again."},
            )
        try:
            actions = _ACTION_LIST_ADAPTER.validate_python(proposal.actions_json)
        except ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "proposal_invalid", "message": "Stored AI proposal is invalid."},
            ) from exc
        if not actions or len(actions) > settings.ai_max_actions_per_request:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "proposal_invalid", "message": "Stored AI proposal has an invalid action count."},
            )
        command = RevisionCommand(
            client_request_id=f"ai:{proposal.id}",
            source="ai",
            expected_revision=proposal.expected_revision,
            actions=actions,
        )
        applied = await revision_service.apply_revision(
            session,
            campaign_id,
            command,
            market_id,
            actor_id=user_id,
            commit=False,
        )
        proposal.status = "applied"
        proposal.applied_at = utc_now()
        proposal.revision_id = applied.revision.id
        await session.commit()
        await session.refresh(proposal)
        logger.info(
            "ai.revision.applied market_id=%s campaign_id=%s proposal_id=%s",
            market_id,
            campaign_id,
            proposal.id,
        )
        return _apply_result(
            proposal,
            applied.revision,
            applied.draft_revision,
            idempotent=applied.idempotent,
        )

    @staticmethod
    def _assert_feature_enabled() -> None:
        if not settings.ai_enabled or not settings.ai_revision_enabled:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "ai_revision_disabled", "message": "AI revision is currently disabled."},
            )

    @staticmethod
    async def _load_campaign(session: AsyncSession, campaign_id: UUID, market_id: UUID) -> Campaign:
        campaign = await session.scalar(
            select(Campaign)
            .options(selectinload(Campaign.items))
            .where(Campaign.id == campaign_id, Campaign.market_id == market_id)
        )
        if campaign is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found.")
        return campaign

    @staticmethod
    async def _find_by_request_id(
        session: AsyncSession, *, market_id: UUID, user_id: UUID, request_id: str
    ) -> AIRevisionProposal | None:
        return await session.scalar(
            select(AIRevisionProposal).where(
                AIRevisionProposal.market_id == market_id,
                AIRevisionProposal.created_by_user_id == user_id,
                AIRevisionProposal.client_request_id == request_id,
            )
        )

    @staticmethod
    def _replayed_proposal(
        proposal: AIRevisionProposal, campaign_id: UUID, fingerprint: str
    ) -> AIRevisionProposalRead:
        if proposal.campaign_id != campaign_id or proposal.request_fingerprint != fingerprint:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="client_request_id was already used for a different AI proposal request.",
            )
        return _proposal_read(proposal, idempotent=True)

    @staticmethod
    async def _record_failure(
        session: AsyncSession,
        *,
        market_id: UUID,
        campaign_id: UUID,
        user_id: UUID,
        capability: str,
        error: AIError,
    ) -> None:
        session.add(
            AIUsageEvent(
                market_id=market_id,
                campaign_id=campaign_id,
                user_id=user_id,
                capability=capability,
                provider=error.provider or "unavailable",
                model=error.model or "unavailable",
                request_type="revision_intent",
                status="timeout" if isinstance(error, AIProviderTimeoutError) else "failed",
                error_code=error.code,
            )
        )
        await session.commit()
        logger.warning(
            "ai.revision.proposal.failed market_id=%s campaign_id=%s capability=%s provider=%s model=%s error_code=%s",
            market_id,
            campaign_id,
            capability,
            error.provider or "unavailable",
            error.model or "unavailable",
            error.code,
        )


def _request_fingerprint(campaign_id: UUID, expected_revision: int, instruction: str) -> str:
    canonical = json.dumps(
        {
            "campaign_id": str(campaign_id),
            "expected_revision": expected_revision,
            "instruction": " ".join(instruction.split()),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _proposal_lock_key(fingerprint: str) -> int:
    unsigned = int.from_bytes(bytes.fromhex(fingerprint[:16]), byteorder="big", signed=False)
    return unsigned if unsigned < 2**63 else unsigned - 2**64


def _assert_mutable(campaign: Campaign) -> None:
    if campaign.frozen_at is not None or campaign.finalized_at is not None or campaign.status in {
        "approved",
        "generating_files",
        "completed",
        "cancelled",
    }:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "campaign_frozen", "message": "Approved campaigns cannot be revised."},
        )


def _assert_expected_revision(campaign: Campaign, expected_revision: int) -> None:
    if campaign.draft_revision != expected_revision:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "stale_revision",
                "message": "Draft revision is stale.",
                "current_revision": campaign.draft_revision,
            },
        )


def _campaign_context(campaign: Campaign) -> dict:
    ordered = sorted(campaign.items, key=lambda item: (item.sort_order, str(item.id)))
    return {
        "campaign": {
            "id": str(campaign.id),
            "title": campaign.title,
            "draft_revision": campaign.draft_revision,
            "currency": campaign.currency,
            "language": campaign.language,
        },
        "items": [
            {
                "id": str(item.id),
                "position": index,
                "display_name": item.display_name or item.incoming_name,
                "price": str(item.price) if item.price is not None else None,
                "old_price": str(item.old_price) if item.old_price is not None else None,
                "is_hidden": bool(item.is_hidden),
                "is_hero": bool(item.is_hero),
                "emphasis": item.emphasis,
            }
            for index, item in enumerate(ordered, start=1)
        ],
    }


def _validate_actions(campaign: Campaign, actions: list[RevisionAction], instruction: str) -> None:
    item_by_id = {item.id: item for item in campaign.items}
    visible_count = sum(not bool(item.is_hidden) for item in campaign.items)
    for action in actions:
        item = item_by_id.get(action.item_id)
        if item is None or item.market_id != campaign.market_id or item.campaign_id != campaign.id:
            raise AIProviderOutputError("AI provider referenced a foreign campaign item.")
        if isinstance(action, MoveItemAction) and (
            item.is_hidden or action.target_position > visible_count
        ):
            raise AIProviderOutputError("AI provider returned an invalid target position.")
        if isinstance(action, ReplaceImageAction):
            raise AIProviderOutputError("AI revision parsing cannot select image IDs.")
        if isinstance(action, UpdatePriceAction):
            _validate_explicit_price(instruction, action)
        if isinstance(action, UpdateDisplayNameAction):
            normalized = instruction.casefold()
            if not any(word in normalized for word in _RENAME_WORDS):
                raise AIProviderOutputError("Display-name changes require an explicit rename instruction.")
            if action.display_name.casefold() not in normalized:
                raise AIProviderOutputError("AI provider invented a display name not present in the instruction.")


def _validate_explicit_price(instruction: str, action: UpdatePriceAction) -> None:
    normalized = instruction.casefold()
    if not any(word in normalized for word in _PRICE_WORDS):
        raise AIProviderOutputError("Price changes require an explicit price instruction.")
    values: set[Decimal] = set()
    for raw in _NUMBER_PATTERN.findall(normalized):
        try:
            values.add(Decimal(raw.replace(",", ".")))
        except InvalidOperation:
            continue
    if action.price not in values:
        raise AIProviderOutputError("AI provider invented a price not present in the instruction.")
    if action.old_price is not None and (
        not any(word in normalized for word in _OLD_PRICE_WORDS) or action.old_price not in values
    ):
        raise AIProviderOutputError("Old-price changes require an explicit old-price instruction.")


def _summaries(campaign: Campaign, actions: list[RevisionAction]) -> list[str]:
    names = {item.id: item.display_name or item.incoming_name for item in campaign.items}
    summaries: list[str] = []
    for action in actions:
        name = names.get(action.item_id, "Ürün")
        if isinstance(action, MoveItemAction):
            summaries.append(f"{name} → {action.target_position}. sıraya taşınacak")
        elif isinstance(action, RemoveItemAction):
            summaries.append(f"{name} → broşürden kaldırılacak")
        elif isinstance(action, RestoreItemAction):
            summaries.append(f"{name} → broşüre geri getirilecek")
        elif isinstance(action, UpdatePriceAction):
            summaries.append(f"{name} → fiyatı {action.price} olarak değiştirilecek")
        elif isinstance(action, UpdateDisplayNameAction):
            summaries.append(f"{name} → adı “{action.display_name}” olacak")
        elif isinstance(action, SetHeroAction):
            summaries.append(f"{name} → {'ana ürün yapılacak' if action.is_hero else 'ana ürün vurgusu kaldırılacak'}")
        elif isinstance(action, SetItemEmphasisAction):
            labels = {"normal": "normal", "large": "büyük", "hero": "ana ürün"}
            summaries.append(f"{name} → {labels[action.emphasis]} vurgu uygulanacak")
    return summaries


def _proposal_read(proposal: AIRevisionProposal, *, idempotent: bool = False) -> AIRevisionProposalRead:
    try:
        actions = _ACTION_LIST_ADAPTER.validate_python(proposal.actions_json)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "proposal_invalid", "message": "Stored AI proposal is invalid."},
        ) from exc
    return AIRevisionProposalRead(
        id=proposal.id,
        campaign_id=proposal.campaign_id,
        status=proposal.status,
        expected_revision=proposal.expected_revision,
        actions=actions,
        summary=list(proposal.summary_json or []),
        clarification_question=proposal.clarification_question,
        unsupported_reason=proposal.unsupported_reason,
        expires_at=proposal.expires_at,
        created_at=proposal.created_at,
        idempotent=idempotent,
    )


def _apply_result(
    proposal: AIRevisionProposal,
    revision: CampaignRevision,
    draft_revision: int,
    *,
    idempotent: bool,
) -> AIRevisionApplyResult:
    return AIRevisionApplyResult(
        proposal=_proposal_read(proposal, idempotent=idempotent),
        revision=RevisionResult(
            revision=CampaignRevisionRead.model_validate(revision),
            draft_revision=draft_revision,
            idempotent=idempotent,
        ),
    )


def _provider_http_error(error: AIError) -> HTTPException:
    if isinstance(error, (AIConfigurationError, AIUnsupportedCapabilityError)):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": error.code, "message": "AI revision is not configured."},
        )
    if isinstance(error, AIProviderAuthenticationError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": error.code, "message": "AI provider is unavailable."},
        )
    if isinstance(error, AIProviderTimeoutError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": error.code, "message": "AI provider timed out. Try again."},
        )
    if isinstance(error, AIProviderTransientError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": error.code, "message": "AI provider is temporarily unavailable."},
        )
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail={"code": error.code, "message": "AI returned an invalid or unavailable response."},
    )
