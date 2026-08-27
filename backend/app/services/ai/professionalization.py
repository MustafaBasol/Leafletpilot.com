"""AI-3: explicit, versioned visual professionalization for approved campaigns."""
from __future__ import annotations

import hashlib
import json
import logging
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import AIProfessionalizationRun, AIUsageEvent, Campaign
from app.models.base import utc_now
from app.schemas.ai import (
    AIProfessionalizationPlanEnvelope,
    ProfessionalizationApplyResult,
    ProfessionalizationHistoryRead,
    ProfessionalizationRequest,
    ProfessionalizationRunRead,
)
from app.services.ai.errors import AIError, AIProviderTimeoutError
from app.services.ai.orchestrator import AIOrchestrator
from app.services.ai.prompts import PROFESSIONALIZATION_SYSTEM_PROMPT
from app.services.ai.types import AICapability
from app.services.rate_limit import AI_USER_KEY, consume_rate_limit, prune_expired_ai_rate_limits

logger = logging.getLogger(__name__)


def frozen_snapshot_hash(snapshot: dict) -> str:
    """Hash frozen input independently of any visual plan or hash marker."""
    material = {key: value for key, value in snapshot.items() if key != "snapshot_sha256"}
    canonical = json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class AIProfessionalizationService:
    def __init__(self, orchestrator: AIOrchestrator) -> None:
        self._orchestrator = orchestrator

    async def create_run(
        self, session: AsyncSession, *, campaign_id: UUID, market_id: UUID, user_id: UUID,
        request: ProfessionalizationRequest,
    ) -> ProfessionalizationRunRead:
        self._assert_enabled()
        design_goal = (request.design_goal or "").strip() or None
        fingerprint = self._fingerprint(campaign_id, design_goal)
        existing = await self._find_request(session, market_id, user_id, request.client_request_id)
        if existing:
            return self._replay(existing, campaign_id, fingerprint)
        campaign = await self._load_campaign(session, campaign_id, market_id)
        snapshot = self._assert_frozen_snapshot(campaign)
        snapshot_hash = frozen_snapshot_hash(snapshot)
        await session.execute(select(func.pg_advisory_xact_lock(self._lock_key(fingerprint))))
        existing = await self._find_request(session, market_id, user_id, request.client_request_id)
        if existing:
            return self._replay(existing, campaign_id, fingerprint)
        run_count = await session.scalar(
            select(func.count(AIProfessionalizationRun.id)).where(
                AIProfessionalizationRun.campaign_id == campaign_id,
                AIProfessionalizationRun.market_id == market_id,
            )
        )
        if (run_count or 0) >= settings.ai_professionalization_max_runs_per_campaign:
            raise HTTPException(status_code=429, detail={"code": "professionalization_run_limit", "message": "Professionalization run limit reached for this campaign."})
        over_limit = await consume_rate_limit(
            session, key_type=AI_USER_KEY, raw_value=str(user_id),
            limit=settings.ai_professionalization_rate_limit_per_minute, window_minutes=1,
            purpose="ai_professionalization",
        )
        await prune_expired_ai_rate_limits(session)
        if over_limit:
            await session.commit()
            raise HTTPException(status_code=429, detail={"code": "ai_rate_limited", "message": "Too many AI requests. Try again shortly."})
        capability = AICapability.COMPLEX_DESIGN_ANALYSIS
        try:
            invocation = await self._orchestrator.generate_structured(
                capability=capability,
                system_prompt=PROFESSIONALIZATION_SYSTEM_PROMPT,
                user_prompt=design_goal or "Create a restrained professional retail treatment.",
                schema=AIProfessionalizationPlanEnvelope,
                context=self._privacy_safe_context(snapshot),
            )
            plan = invocation.output
            self._validate_plan(plan, snapshot)
        except AIError as exc:
            await self._record_failure(session, market_id, campaign_id, user_id, capability.value, exc)
            raise self._provider_error(exc) from exc
        if plan.status != "ready":
            raise HTTPException(status_code=422, detail={"code": "professionalization_unsupported", "message": plan.unsupported_reason or "No safe visual plan is available."})
        run = AIProfessionalizationRun(
            market_id=market_id, campaign_id=campaign_id, created_by_user_id=user_id,
            client_request_id=request.client_request_id, request_fingerprint=fingerprint,
            snapshot_hash=snapshot_hash, capability=capability.value, provider=invocation.provider,
            model=invocation.model, status="ready", design_goal=design_goal,
            plan_json=plan.model_dump(mode="json"), summary_json=list(plan.rationale),
        )
        session.add(run)
        try:
            await session.flush()
            session.add(AIUsageEvent(
                market_id=market_id, campaign_id=campaign_id, user_id=user_id,
                capability=capability.value, provider=invocation.provider, model=invocation.model,
                request_type="professionalization", status="success",
                input_tokens=invocation.usage.input_tokens, output_tokens=invocation.usage.output_tokens,
                latency_ms=invocation.latency_ms,
            ))
            await session.commit()
            await session.refresh(run)
        except IntegrityError:
            await session.rollback()
            existing = await self._find_request(session, market_id, user_id, request.client_request_id)
            if not existing:
                raise HTTPException(status_code=409, detail="Professionalization request conflicts with current state.")
            return self._replay(existing, campaign_id, fingerprint)
        logger.info("ai.professionalization.created market_id=%s campaign_id=%s run_id=%s provider=%s model=%s latency_ms=%s", market_id, campaign_id, run.id, invocation.provider, invocation.model, invocation.latency_ms)
        return self._read(run)

    async def apply_run(self, session: AsyncSession, *, campaign_id: UUID, run_id: UUID, market_id: UUID, user_id: UUID) -> ProfessionalizationApplyResult:
        self._assert_enabled()
        campaign = await self._load_campaign(session, campaign_id, market_id, for_update=True)
        snapshot = self._assert_frozen_snapshot(campaign)
        run = await session.scalar(select(AIProfessionalizationRun).where(
            AIProfessionalizationRun.id == run_id, AIProfessionalizationRun.campaign_id == campaign_id,
            AIProfessionalizationRun.market_id == market_id, AIProfessionalizationRun.created_by_user_id == user_id,
        ).with_for_update())
        if not run:
            raise HTTPException(status_code=404, detail="Professionalization run not found.")
        if run.snapshot_hash != frozen_snapshot_hash(snapshot):
            raise HTTPException(status_code=409, detail={"code": "snapshot_integrity_failed", "message": "Frozen campaign snapshot changed; original design remains available."})
        self._validate_plan(AIProfessionalizationPlanEnvelope.model_validate(run.plan_json), snapshot)
        await session.execute(update(AIProfessionalizationRun).where(
            AIProfessionalizationRun.campaign_id == campaign_id,
            AIProfessionalizationRun.market_id == market_id,
            AIProfessionalizationRun.is_active.is_(True),
            AIProfessionalizationRun.id != run.id,
        ).values(is_active=False, status="superseded"))
        run.is_active = True
        run.status = "applied"
        run.applied_at = utc_now()
        await session.commit()
        await session.refresh(run)
        logger.info("ai.professionalization.applied market_id=%s campaign_id=%s run_id=%s", market_id, campaign_id, run.id)
        return ProfessionalizationApplyResult(run=self._read(run))

    async def restore_original(self, session: AsyncSession, *, campaign_id: UUID, market_id: UUID) -> ProfessionalizationHistoryRead:
        campaign = await self._load_campaign(session, campaign_id, market_id, for_update=True)
        self._assert_frozen_snapshot(campaign)
        await session.execute(update(AIProfessionalizationRun).where(
            AIProfessionalizationRun.campaign_id == campaign_id,
            AIProfessionalizationRun.market_id == market_id,
            AIProfessionalizationRun.is_active.is_(True),
        ).values(is_active=False, status="superseded"))
        await session.commit()
        return await self.history(session, campaign_id=campaign_id, market_id=market_id)

    async def history(self, session: AsyncSession, *, campaign_id: UUID, market_id: UUID) -> ProfessionalizationHistoryRead:
        await self._load_campaign(session, campaign_id, market_id)
        rows = list((await session.scalars(select(AIProfessionalizationRun).where(
            AIProfessionalizationRun.campaign_id == campaign_id,
            AIProfessionalizationRun.market_id == market_id,
        ).order_by(AIProfessionalizationRun.created_at.desc()))).all())
        active = next((row.id for row in rows if row.is_active), None)
        return ProfessionalizationHistoryRead(active_run_id=active, runs=[self._read(row) for row in rows])

    @staticmethod
    async def _load_campaign(session, campaign_id, market_id, for_update=False):
        statement = select(Campaign).where(Campaign.id == campaign_id, Campaign.market_id == market_id)
        if for_update:
            statement = statement.with_for_update()
        campaign = await session.scalar(statement)
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found.")
        return campaign

    @staticmethod
    def _assert_enabled():
        if not settings.ai_enabled or not settings.ai_professionalization_enabled:
            raise HTTPException(status_code=503, detail={"code": "ai_professionalization_disabled", "message": "Professionalization is currently disabled."})

    @staticmethod
    def _assert_frozen_snapshot(campaign):
        snapshot = campaign.snapshot_json
        if (
            campaign.frozen_at is None
            or campaign.finalized_at is None
            or campaign.approved_revision is None
            or not isinstance(snapshot, dict)
            or snapshot.get("approved_revision") != campaign.approved_revision
        ):
            raise HTTPException(status_code=409, detail={"code": "campaign_not_approved", "message": "Approve the campaign before professionalizing it."})
        return snapshot

    @staticmethod
    def _privacy_safe_context(snapshot):
        items = list(snapshot.get("items") or [])
        return {
            "campaign": {"language": snapshot.get("language"), "item_count": len(items), "template_slug": snapshot.get("template_slug")},
            "visual_inventory": [{"position": index, "has_image": bool(item.get("image_key")), "has_badge": bool(item.get("badge"))} for index, item in enumerate(items, start=1)],
            "constraints": {"no_html_css": True, "preserve_order": True, "preserve_commercial_facts": True},
        }

    @staticmethod
    def _validate_plan(plan, snapshot):
        count = len(snapshot.get("items") or [])
        if any(entry.position > count for entry in plan.emphasis):
            raise HTTPException(status_code=502, detail={"code": "schema_invalid", "message": "AI returned an out-of-range visual treatment."})

    @staticmethod
    async def _find_request(session, market_id, user_id, request_id):
        return await session.scalar(select(AIProfessionalizationRun).where(
            AIProfessionalizationRun.market_id == market_id,
            AIProfessionalizationRun.created_by_user_id == user_id,
            AIProfessionalizationRun.client_request_id == request_id,
        ))

    @staticmethod
    def _fingerprint(campaign_id, design_goal):
        return hashlib.sha256(json.dumps({"campaign_id": str(campaign_id), "design_goal": design_goal or ""}, sort_keys=True).encode()).hexdigest()

    @staticmethod
    def _lock_key(fingerprint):
        value = int.from_bytes(bytes.fromhex(fingerprint[:16]), "big", signed=False)
        return value if value < 2**63 else value - 2**64

    @staticmethod
    def _replay(run, campaign_id, fingerprint):
        if run.campaign_id != campaign_id or run.request_fingerprint != fingerprint:
            raise HTTPException(status_code=409, detail="client_request_id was already used for a different professionalization request.")
        return AIProfessionalizationService._read(run, idempotent=True)

    @staticmethod
    def _read(run, idempotent=False):
        return ProfessionalizationRunRead(
            id=run.id, campaign_id=run.campaign_id, snapshot_hash=run.snapshot_hash,
            provider=run.provider, model=run.model, status=run.status, is_active=run.is_active,
            plan=AIProfessionalizationPlanEnvelope.model_validate(run.plan_json), summary=list(run.summary_json or []),
            applied_at=run.applied_at, created_at=run.created_at, idempotent=idempotent,
        )

    @staticmethod
    async def _record_failure(session, market_id, campaign_id, user_id, capability, error):
        session.add(AIUsageEvent(market_id=market_id, campaign_id=campaign_id, user_id=user_id, capability=capability, provider=error.provider or "unavailable", model=error.model or "unavailable", request_type="professionalization", status="timeout" if isinstance(error, AIProviderTimeoutError) else "failed", error_code=error.code))
        await session.commit()
        logger.warning("ai.professionalization.failed market_id=%s campaign_id=%s capability=%s provider=%s model=%s error_code=%s", market_id, campaign_id, capability, error.provider or "unavailable", error.model or "unavailable", error.code)

    @staticmethod
    def _provider_error(error):
        return HTTPException(status_code=503, detail={"code": error.code, "message": "AI professionalization is temporarily unavailable; original export remains available."})