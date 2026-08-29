"""AI-3: explicit, versioned visual professionalization for approved campaigns."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

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
    ProfessionalizationRetryRequest,
    ProfessionalizationRunRead,
)
from app.services.ai.errors import (
    AIError,
    AIProviderTimeoutError,
    AIProviderTransientError,
)
from app.services.ai.orchestrator import AIOrchestrator
from app.services.ai.prompts import (
    BROCHURE_IMAGE_SYSTEM_PROMPT,
    PROFESSIONALIZATION_SYSTEM_PROMPT,
)
from app.services.ai.types import AICapability
from app.services.rate_limit import AI_USER_KEY, consume_rate_limit, prune_expired_ai_rate_limits

logger = logging.getLogger(__name__)

TRANSIENT_RETRY_ALLOWANCE = 3
TRANSIENT_FAILURE_CODES = {"provider_timeout", "provider_unavailable"}
IN_FLIGHT_STATUSES = ("pending", "generating", "validating")


def frozen_snapshot_hash(snapshot: dict) -> str:
    """Hash frozen input independently of any visual plan or hash marker."""
    material = {key: value for key, value in snapshot.items() if key != "snapshot_sha256"}
    canonical = json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def frozen_market_profile(snapshot: dict) -> dict:
    """Read the frozen profile, retaining legacy snapshot header identity."""
    profile = dict(snapshot.get("market_profile") or {})
    if profile:
        return profile
    header = dict(snapshot.get("header") or {})
    logo_key = header.get("market_logo")
    return {
        "name": snapshot.get("market_name"),
        "visibility": {"logo": bool(logo_key)},
        "logo_key": logo_key,
    }


def immutable_brochure_facts(snapshot: dict) -> dict:
    """Build the privacy-safe frozen fact payload for final-image generation."""
    profile = frozen_market_profile(snapshot)
    visibility = dict(profile.get("visibility") or {})
    market = {"name": profile.get("name") or snapshot.get("market_name")}
    for key in ("address", "phone", "website", "instagram", "facebook"):
        if visibility.get(key) and profile.get(key):
            market[key] = profile[key]
    if visibility.get("logo") and profile.get("logo_key"):
        market["logo_reference"] = profile["logo_key"]
    return {
        "campaign_title": snapshot.get("title"),
        "market": market,
        "header": snapshot.get("header") or {},
        "products": [
            {
                key: item.get(key)
                for key in (
                    "name",
                    "price",
                    "old_price",
                    "currency",
                    "unit_label",
                    "quantity_label",
                    "sort_order",
                )
            }
            for item in snapshot.get("items") or []
        ],
    }


def is_exportable_ai_run(run: AIProfessionalizationRun, snapshot_hash: str) -> bool:
    report = run.validation_report_json or {}
    return bool(
        run.is_active
        and run.status == "applied"
        and run.snapshot_hash == snapshot_hash
        and run.generated_image_storage_key
        and run.generated_image_file_id
        and report.get("accepted") is True
        and report.get("evidence_status") == "verified"
    )


def _is_accepted_source(run: AIProfessionalizationRun | None, snapshot_hash: str) -> bool:
    if run is None or run.snapshot_hash != snapshot_hash:
        return False
    report = run.validation_report_json or {}
    return bool(
        run.status in {"ready", "applied"}
        and run.generated_image_storage_key
        and run.generated_image_file_id
        and report.get("accepted") is True
        and report.get("evidence_status") == "verified"
    )


class AIProfessionalizationService:
    def __init__(self, orchestrator: AIOrchestrator) -> None:
        self._orchestrator = orchestrator

    async def create_run(
        self,
        session: AsyncSession,
        *,
        campaign_id: UUID,
        market_id: UUID,
        user_id: UUID,
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
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "professionalization_run_limit",
                    "message": "Professionalization run limit reached for this campaign.",
                },
            )
        over_limit = await consume_rate_limit(
            session,
            key_type=AI_USER_KEY,
            raw_value=str(user_id),
            limit=settings.ai_professionalization_rate_limit_per_minute,
            window_minutes=1,
            purpose="ai_professionalization",
        )
        await prune_expired_ai_rate_limits(session)
        if over_limit:
            await session.commit()
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "ai_rate_limited",
                    "message": "Too many AI requests. Try again shortly.",
                },
            )
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
            await self._record_failure(
                session, market_id, campaign_id, user_id, capability.value, exc
            )
            raise self._provider_error(exc) from exc
        if plan.status != "ready":
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "professionalization_unsupported",
                    "message": plan.unsupported_reason or "No safe visual plan is available.",
                },
            )
        run = AIProfessionalizationRun(
            market_id=market_id,
            campaign_id=campaign_id,
            created_by_user_id=user_id,
            client_request_id=request.client_request_id,
            request_fingerprint=fingerprint,
            snapshot_hash=snapshot_hash,
            capability=capability.value,
            provider=invocation.provider,
            model=invocation.model,
            status="ready",
            design_goal=design_goal,
            plan_json=plan.model_dump(mode="json"),
            summary_json=list(plan.rationale),
        )
        session.add(run)
        try:
            await session.flush()
            session.add(
                AIUsageEvent(
                    market_id=market_id,
                    campaign_id=campaign_id,
                    user_id=user_id,
                    capability=capability.value,
                    provider=invocation.provider,
                    model=invocation.model,
                    request_type="professionalization",
                    status="success",
                    input_tokens=invocation.usage.input_tokens,
                    output_tokens=invocation.usage.output_tokens,
                    latency_ms=invocation.latency_ms,
                )
            )
            await session.commit()
            await session.refresh(run)
        except IntegrityError:
            await session.rollback()
            existing = await self._find_request(
                session, market_id, user_id, request.client_request_id
            )
            if not existing:
                raise HTTPException(
                    status_code=409,
                    detail="Professionalization request conflicts with current state.",
                )
            return self._replay(existing, campaign_id, fingerprint)
        logger.info(
            "ai.professionalization.created market_id=%s campaign_id=%s run_id=%s provider=%s model=%s latency_ms=%s",
            market_id,
            campaign_id,
            run.id,
            invocation.provider,
            invocation.model,
            invocation.latency_ms,
        )
        return self._read(run)

    async def retry_run(
        self,
        session: AsyncSession,
        *,
        campaign_id: UUID,
        market_id: UUID,
        user_id: UUID,
        request: ProfessionalizationRetryRequest,
    ) -> ProfessionalizationRunRead:
        """Queue a new image attempt without mutating a prior run or frozen fact."""
        self._assert_enabled()
        instruction = (request.instruction or "").strip() or None
        campaign = await self._load_campaign(session, campaign_id, market_id)
        snapshot = self._assert_frozen_snapshot(campaign)
        snapshot_hash = frozen_snapshot_hash(snapshot)
        lock_fingerprint = hashlib.sha256(
            f"professionalization:{campaign_id}:{snapshot_hash}".encode()
        ).hexdigest()
        await session.execute(select(func.pg_advisory_xact_lock(self._lock_key(lock_fingerprint))))

        request_id = request.client_request_id or f"retry-{uuid4()}"
        existing = await self._find_request(session, market_id, user_id, request_id)
        if existing is not None:
            if (
                existing.campaign_id != campaign_id
                or (existing.user_instruction or None) != instruction
                or (
                    request.source_run_id is not None
                    and existing.source_run_id != request.source_run_id
                )
            ):
                raise HTTPException(
                    status_code=409,
                    detail="client_request_id was already used for a different professionalization request.",
                )
            return self._read(
                existing,
                version_number=await self._version_number(session, existing),
                idempotent=True,
            )

        in_flight = await session.scalar(
            select(AIProfessionalizationRun).where(
                AIProfessionalizationRun.campaign_id == campaign_id,
                AIProfessionalizationRun.market_id == market_id,
                AIProfessionalizationRun.snapshot_hash == snapshot_hash,
                AIProfessionalizationRun.status.in_(IN_FLIGHT_STATUSES),
            )
        )
        if in_flight is not None:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "professionalization_in_progress",
                    "message": "A professionalization run is already in progress.",
                },
            )

        over_limit = await consume_rate_limit(
            session,
            key_type=AI_USER_KEY,
            raw_value=str(user_id),
            limit=settings.ai_professionalization_rate_limit_per_minute,
            window_minutes=1,
            purpose="ai_professionalization",
        )
        await prune_expired_ai_rate_limits(session)
        if over_limit:
            await session.commit()
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "ai_rate_limited",
                    "message": "Too many AI requests. Try again shortly.",
                },
            )

        rows = list(
            (
                await session.scalars(
                    select(AIProfessionalizationRun).where(
                        AIProfessionalizationRun.campaign_id == campaign_id,
                        AIProfessionalizationRun.market_id == market_id,
                    )
                )
            ).all()
        )
        self._assert_retry_quota(rows)
        source_run = await self._select_source_run(
            session,
            campaign_id=campaign_id,
            market_id=market_id,
            snapshot_hash=snapshot_hash,
            instruction=instruction,
            requested_source_run_id=request.source_run_id,
            history=rows,
        )
        source_type = "previous_ai_output" if source_run is not None else "approved_original"
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "campaign_id": str(campaign_id),
                    "snapshot_hash": snapshot_hash,
                    "instruction": instruction or "",
                    "source_run_id": str(source_run.id) if source_run else None,
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        provider = settings.ai_professionalization_provider or settings.ai_revision_provider
        model = settings.ai_professionalization_model or settings.ai_revision_model
        run = AIProfessionalizationRun(
            market_id=market_id,
            campaign_id=campaign_id,
            created_by_user_id=user_id,
            client_request_id=request_id,
            request_fingerprint=fingerprint,
            snapshot_hash=snapshot_hash,
            capability=AICapability.BROCHURE_IMAGE_PROFESSIONALIZATION.value,
            provider=provider or "unavailable",
            model=model or "unavailable",
            status="pending",
            request_mode="revision" if instruction else "retry",
            source_type=source_type,
            source_run_id=source_run.id if source_run else None,
            user_instruction=instruction,
            plan_json={
                "status": "unsupported",
                "unsupported_reason": "Final image generation does not use a renderer plan.",
            },
            summary_json=[],
        )
        session.add(run)
        try:
            await session.commit()
            await session.refresh(run)
        except IntegrityError:
            await session.rollback()
            existing = await self._find_request(session, market_id, user_id, request_id)
            if existing is None:
                raise HTTPException(
                    status_code=409,
                    detail="Professionalization request conflicts with current state.",
                )
            return self._read(
                existing,
                version_number=await self._version_number(session, existing),
                idempotent=True,
            )

        instruction_hash = (
            hashlib.sha256(instruction.encode()).hexdigest()[:12] if instruction else None
        )
        event_name = (
            "professionalization.revision_requested"
            if instruction
            else "professionalization.retry_requested"
        )
        logger.info(
            "%s market_id=%s campaign_id=%s run_id=%s source_run_id=%s source_type=%s instruction_present=%s instruction_length=%s instruction_hash=%s",
            event_name,
            market_id,
            campaign_id,
            run.id,
            run.source_run_id,
            source_type,
            bool(instruction),
            len(instruction or ""),
            instruction_hash,
        )
        logger.info(
            "professionalization.requested market_id=%s campaign_id=%s run_id=%s source_run_id=%s source_type=%s provider=%s model=%s",
            market_id,
            campaign_id,
            run.id,
            run.source_run_id,
            source_type,
            run.provider,
            run.model,
        )
        return self._read(run, version_number=len(rows) + 1)

    @staticmethod
    def _assert_retry_quota(rows: list[AIProfessionalizationRun]) -> None:
        transient = sum(
            row.status == "failed" and row.failure_category == "transient_provider" for row in rows
        )
        normal = len(rows) - transient
        normal_limit = settings.ai_professionalization_max_runs_per_campaign
        if len(rows) >= normal_limit + TRANSIENT_RETRY_ALLOWANCE:
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "professionalization_hard_limit",
                    "message": "Professionalization safety limit reached.",
                },
            )
        if normal >= normal_limit:
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "professionalization_run_limit",
                    "message": "Professionalization run limit reached for this campaign.",
                },
            )

    @staticmethod
    async def _select_source_run(
        session: AsyncSession,
        *,
        campaign_id: UUID,
        market_id: UUID,
        snapshot_hash: str,
        instruction: str | None,
        requested_source_run_id: UUID | None,
        history: list[AIProfessionalizationRun],
    ) -> AIProfessionalizationRun | None:
        source_id = requested_source_run_id
        if source_id is None and instruction:
            accepted = [row for row in history if _is_accepted_source(row, snapshot_hash)]
            active = next((row for row in accepted if row.is_active), None)
            newest = max(accepted, key=lambda row: row.created_at, default=None)
            source_id = (active or newest).id if active or newest else None
        if source_id is None and not instruction and history:
            latest = max(history, key=lambda row: row.created_at)
            if (
                latest.status in {"failed", "rejected"}
                and latest.source_type == "previous_ai_output"
            ):
                source_id = latest.source_run_id
        if source_id is None:
            return None
        source = await session.scalar(
            select(AIProfessionalizationRun).where(
                AIProfessionalizationRun.id == source_id,
                AIProfessionalizationRun.campaign_id == campaign_id,
                AIProfessionalizationRun.market_id == market_id,
            )
        )
        if source is None:
            raise HTTPException(status_code=404, detail="Professionalization source not found.")
        if not _is_accepted_source(source, snapshot_hash):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "invalid_professionalization_source",
                    "message": "Only a verified AI version for the current approved snapshot can be revised.",
                },
            )
        return source

    @staticmethod
    async def _version_number(session: AsyncSession, run: AIProfessionalizationRun) -> int:
        count = await session.scalar(
            select(func.count(AIProfessionalizationRun.id)).where(
                AIProfessionalizationRun.campaign_id == run.campaign_id,
                AIProfessionalizationRun.market_id == run.market_id,
                AIProfessionalizationRun.created_at <= run.created_at,
            )
        )
        return max(1, int(count or 1))

    async def apply_run(
        self,
        session: AsyncSession,
        *,
        campaign_id: UUID,
        run_id: UUID,
        market_id: UUID,
        user_id: UUID,
    ) -> ProfessionalizationApplyResult:
        self._assert_enabled()
        campaign = await self._load_campaign(session, campaign_id, market_id, for_update=True)
        snapshot = self._assert_frozen_snapshot(campaign)
        snapshot_hash = frozen_snapshot_hash(snapshot)
        run = await session.scalar(
            select(AIProfessionalizationRun)
            .where(
                AIProfessionalizationRun.id == run_id,
                AIProfessionalizationRun.campaign_id == campaign_id,
                AIProfessionalizationRun.market_id == market_id,
            )
            .with_for_update()
        )
        if run is None:
            raise HTTPException(status_code=404, detail="Professionalization run not found.")
        if run.snapshot_hash != snapshot_hash:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "snapshot_integrity_failed",
                    "message": "Frozen campaign snapshot changed; original design remains available.",
                },
            )
        image_run = run.capability == AICapability.BROCHURE_IMAGE_PROFESSIONALIZATION.value
        if image_run and not _is_accepted_source(run, snapshot_hash):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "professionalization_not_ready",
                    "message": "Only a verified professionalization version can be selected.",
                },
            )
        if not image_run:
            self._validate_plan(
                AIProfessionalizationPlanEnvelope.model_validate(run.plan_json), snapshot
            )
        await session.execute(
            update(AIProfessionalizationRun)
            .where(
                AIProfessionalizationRun.campaign_id == campaign_id,
                AIProfessionalizationRun.market_id == market_id,
                AIProfessionalizationRun.is_active.is_(True),
                AIProfessionalizationRun.id != run.id,
            )
            .values(is_active=False, status="ready")
        )
        run.is_active = True
        run.status = "applied"
        run.applied_at = utc_now()
        await session.commit()
        await session.refresh(run)
        logger.info(
            "professionalization.completed market_id=%s campaign_id=%s run_id=%s source_run_id=%s source_type=%s",
            market_id,
            campaign_id,
            run.id,
            run.source_run_id,
            run.source_type,
        )
        return ProfessionalizationApplyResult(
            run=self._read(run, version_number=await self._version_number(session, run))
        )

    async def restore_original(
        self,
        session: AsyncSession,
        *,
        campaign_id: UUID,
        market_id: UUID,
    ) -> ProfessionalizationHistoryRead:
        campaign = await self._load_campaign(session, campaign_id, market_id, for_update=True)
        self._assert_frozen_snapshot(campaign)
        await session.execute(
            update(AIProfessionalizationRun)
            .where(
                AIProfessionalizationRun.campaign_id == campaign_id,
                AIProfessionalizationRun.market_id == market_id,
                AIProfessionalizationRun.is_active.is_(True),
            )
            .values(is_active=False, status="ready")
        )
        await session.commit()
        return await self.history(session, campaign_id=campaign_id, market_id=market_id)

    async def history(
        self,
        session: AsyncSession,
        *,
        campaign_id: UUID,
        market_id: UUID,
    ) -> ProfessionalizationHistoryRead:
        campaign = await self._load_campaign(session, campaign_id, market_id)
        snapshot = self._assert_frozen_snapshot(campaign)
        snapshot_hash = frozen_snapshot_hash(snapshot)
        rows = list(
            (
                await session.scalars(
                    select(AIProfessionalizationRun)
                    .where(
                        AIProfessionalizationRun.campaign_id == campaign_id,
                        AIProfessionalizationRun.market_id == market_id,
                    )
                    .order_by(AIProfessionalizationRun.created_at.asc())
                )
            ).all()
        )
        current_rows = [row for row in rows if row.snapshot_hash == snapshot_hash]
        active = next(
            (row for row in current_rows if is_exportable_ai_run(row, snapshot_hash)), None
        )
        latest = current_rows[-1] if current_rows else None
        accepted = [row for row in current_rows if _is_accepted_source(row, snapshot_hash)]
        quota_available = True
        try:
            self._assert_retry_quota(rows)
        except HTTPException:
            quota_available = False
        reads = [self._read(row, version_number=index) for index, row in enumerate(rows, start=1)]
        reads.reverse()
        return ProfessionalizationHistoryRead(
            active_run_id=active.id if active else None,
            latest_run_id=latest.id if latest else None,
            current_status=latest.status if latest else None,
            active_source="ai" if active else "original",
            retry_allowed=(
                settings.ai_enabled
                and settings.ai_professionalization_enabled
                and quota_available
                and not (latest and latest.status in IN_FLIGHT_STATUSES)
            ),
            revise_allowed=bool(accepted) and quota_available,
            runs=reads,
        )

    @staticmethod
    async def _load_campaign(session, campaign_id, market_id, for_update=False):
        statement = select(Campaign).where(
            Campaign.id == campaign_id, Campaign.market_id == market_id
        )
        if for_update:
            statement = statement.with_for_update()
        campaign = await session.scalar(statement)
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found.")
        return campaign

    @staticmethod
    def _assert_enabled():
        if not settings.ai_enabled or not settings.ai_professionalization_enabled:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "ai_professionalization_disabled",
                    "message": "Professionalization is currently disabled.",
                },
            )

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
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "campaign_not_approved",
                    "message": "Approve the campaign before professionalizing it.",
                },
            )
        return snapshot

    @staticmethod
    def _privacy_safe_context(snapshot):
        items = list(snapshot.get("items") or [])
        return {
            "campaign": {
                "language": snapshot.get("language"),
                "item_count": len(items),
                "template_slug": snapshot.get("template_slug"),
            },
            "visual_inventory": [
                {
                    "position": index,
                    "has_image": bool(item.get("image_key")),
                    "has_badge": bool(item.get("badge")),
                }
                for index, item in enumerate(items, start=1)
            ],
            "constraints": {
                "no_html_css": True,
                "preserve_order": True,
                "preserve_commercial_facts": True,
            },
        }

    @staticmethod
    def _validate_plan(plan, snapshot):
        count = len(snapshot.get("items") or [])
        if any(entry.position > count for entry in plan.emphasis):
            raise HTTPException(
                status_code=502,
                detail={
                    "code": "schema_invalid",
                    "message": "AI returned an out-of-range visual treatment.",
                },
            )

    @staticmethod
    async def _find_request(session, market_id, user_id, request_id):
        return await session.scalar(
            select(AIProfessionalizationRun).where(
                AIProfessionalizationRun.market_id == market_id,
                AIProfessionalizationRun.created_by_user_id == user_id,
                AIProfessionalizationRun.client_request_id == request_id,
            )
        )

    @staticmethod
    def _fingerprint(campaign_id, design_goal):
        return hashlib.sha256(
            json.dumps(
                {"campaign_id": str(campaign_id), "design_goal": design_goal or ""}, sort_keys=True
            ).encode()
        ).hexdigest()

    @staticmethod
    def _lock_key(fingerprint):
        value = int.from_bytes(bytes.fromhex(fingerprint[:16]), "big", signed=False)
        return value if value < 2**63 else value - 2**64

    @staticmethod
    def _replay(run, campaign_id, fingerprint):
        if run.campaign_id != campaign_id or run.request_fingerprint != fingerprint:
            raise HTTPException(
                status_code=409,
                detail="client_request_id was already used for a different professionalization request.",
            )
        return AIProfessionalizationService._read(run, idempotent=True)

    @staticmethod
    def _read(run, version_number=1, idempotent=False):
        report = run.validation_report_json or {}
        reason = run.error_code
        safe_reasons = {
            "provider_timeout",
            "provider_unavailable",
            "provider_authentication",
            "provider_error",
            "schema_invalid",
            "snapshot_integrity_failed",
            "image_unreadable",
            "unsupported_dimensions",
            "unsupported_aspect_ratio",
            "image_empty",
            "ocr_unavailable",
            "ocr_low_confidence",
            "critical_facts_unverifiable",
            "commercial_fact_mismatch",
            "logo_identity_unverifiable",
            "validation_error",
        }
        if reason and reason not in safe_reasons:
            reason = "generation_failed"
        try:
            plan = AIProfessionalizationPlanEnvelope.model_validate(run.plan_json)
        except Exception:  # noqa: BLE001 - legacy rows must remain readable
            plan = AIProfessionalizationPlanEnvelope(
                status="unsupported", unsupported_reason="Legacy image run."
            )
        return ProfessionalizationRunRead(
            id=run.id,
            campaign_id=run.campaign_id,
            snapshot_hash=run.snapshot_hash,
            provider=run.provider,
            model=run.model,
            status=run.status,
            is_active=run.is_active,
            version_number=version_number,
            source_type=getattr(run, "source_type", None) or "approved_original",
            source_run_id=getattr(run, "source_run_id", None),
            request_mode=getattr(run, "request_mode", None) or "legacy",
            user_instruction=getattr(run, "user_instruction", None),
            plan=plan,
            summary=list(run.summary_json or []),
            applied_at=run.applied_at,
            completed_at=getattr(run, "completed_at", None),
            generated_image_file_id=getattr(run, "generated_image_file_id", None),
            failure_category=getattr(run, "failure_category", None),
            failure_reason=reason,
            validation_outcome=report.get("evidence_status"),
            created_at=run.created_at,
            idempotent=idempotent,
        )

    @staticmethod
    async def _record_failure(session, market_id, campaign_id, user_id, capability, error):
        session.add(
            AIUsageEvent(
                market_id=market_id,
                campaign_id=campaign_id,
                user_id=user_id,
                capability=capability,
                provider=error.provider or "unavailable",
                model=error.model or "unavailable",
                request_type="professionalization",
                status="timeout" if isinstance(error, AIProviderTimeoutError) else "failed",
                error_code=error.code,
            )
        )
        await session.commit()
        logger.warning(
            "ai.professionalization.failed market_id=%s campaign_id=%s capability=%s provider=%s model=%s error_code=%s",
            market_id,
            campaign_id,
            capability,
            error.provider or "unavailable",
            error.model or "unavailable",
            error.code,
        )

    @staticmethod
    def _provider_error(error):
        return HTTPException(
            status_code=503,
            detail={
                "code": error.code,
                "message": "AI professionalization is temporarily unavailable; original export remains available.",
            },
        )


async def queue_automatic_professionalization(
    session: AsyncSession,
    *,
    campaign_id: UUID,
    market_id: UUID,
    user_id: UUID | None,
) -> AIProfessionalizationRun | None:
    """Create exactly one pending run for an immutable approved snapshot."""
    if not settings.ai_enabled or not settings.ai_professionalization_enabled:
        return None
    campaign = await session.scalar(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.market_id == market_id)
    )
    if (
        campaign is None
        or campaign.frozen_at is None
        or not isinstance(campaign.snapshot_json, dict)
    ):
        return None
    snapshot_hash = frozen_snapshot_hash(campaign.snapshot_json)
    lock_hash = hashlib.sha256(f"automatic:{campaign_id}:{snapshot_hash}".encode()).hexdigest()
    await session.execute(
        select(func.pg_advisory_xact_lock(AIProfessionalizationService._lock_key(lock_hash)))
    )
    existing = await session.scalar(
        select(AIProfessionalizationRun).where(
            AIProfessionalizationRun.campaign_id == campaign_id,
            AIProfessionalizationRun.market_id == market_id,
            AIProfessionalizationRun.snapshot_hash == snapshot_hash,
            AIProfessionalizationRun.status.in_(
                ("pending", "generating", "validating", "ready", "applied")
            ),
        )
    )
    if existing is not None:
        return existing
    provider = settings.ai_professionalization_provider or settings.ai_revision_provider
    model = settings.ai_professionalization_model or settings.ai_revision_model
    run = AIProfessionalizationRun(
        market_id=market_id,
        campaign_id=campaign_id,
        created_by_user_id=user_id,
        client_request_id=f"automatic-{campaign_id}-{snapshot_hash[:16]}",
        request_fingerprint=snapshot_hash,
        snapshot_hash=snapshot_hash,
        capability=AICapability.BROCHURE_IMAGE_PROFESSIONALIZATION.value,
        provider=provider or "unavailable",
        model=model or "unavailable",
        status="pending",
        request_mode="automatic",
        source_type="approved_original",
        plan_json={
            "status": "unsupported",
            "unsupported_reason": "Final image generation does not use a renderer plan.",
        },
        summary_json=[],
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    logger.info(
        "professionalization.requested market_id=%s campaign_id=%s run_id=%s source_run_id=%s source_type=%s provider=%s model=%s",
        market_id,
        campaign_id,
        run.id,
        None,
        run.source_type,
        run.provider,
        run.model,
    )
    return run


async def process_automatic_professionalization(
    session: AsyncSession,
    *,
    run_id: UUID,
    service: AIProfessionalizationService,
) -> None:
    """Generate and validate a candidate; selection remains an explicit user action."""
    from app.models import CampaignFile
    from app.services.ai.brochure_validation import validate_generated_brochure
    from app.services.campaign_rendering import (
        get_campaign_for_render,
        render_campaign_snapshot_html,
    )
    from app.services.rendering import render_html_to_png, storage_path_for_key

    run = await session.scalar(
        select(AIProfessionalizationRun)
        .where(AIProfessionalizationRun.id == run_id)
        .with_for_update()
    )
    if run is None or run.status != "pending":
        return
    campaign = await get_campaign_for_render(session, run.campaign_id, run.market_id)
    if (
        campaign is None
        or not isinstance(campaign.snapshot_json, dict)
        or frozen_snapshot_hash(campaign.snapshot_json) != run.snapshot_hash
    ):
        run.status = "rejected"
        run.error_code = "snapshot_integrity_failed"
        run.failure_category = "integrity"
        run.completed_at = datetime.now(UTC)
        await session.commit()
        logger.warning(
            "professionalization.failed market_id=%s campaign_id=%s run_id=%s source_run_id=%s source_type=%s validation_reason=%s",
            run.market_id,
            run.campaign_id,
            run.id,
            run.source_run_id,
            run.source_type,
            run.error_code,
        )
        return

    run.status = "generating"
    await session.commit()
    logger.info(
        "professionalization.started market_id=%s campaign_id=%s run_id=%s source_run_id=%s source_type=%s provider=%s model=%s timeout_seconds=%s",
        run.market_id,
        run.campaign_id,
        run.id,
        run.source_run_id,
        run.source_type,
        run.provider,
        run.model,
        settings.ai_image_http_timeout_seconds,
    )
    snapshot = campaign.snapshot_json

    try:
        if run.source_type == "previous_ai_output":
            source_run = await session.scalar(
                select(AIProfessionalizationRun).where(
                    AIProfessionalizationRun.id == run.source_run_id,
                    AIProfessionalizationRun.campaign_id == run.campaign_id,
                    AIProfessionalizationRun.market_id == run.market_id,
                )
            )
            if not _is_accepted_source(source_run, run.snapshot_hash):
                raise ValueError("invalid_professionalization_source")
            source_key = source_run.generated_image_storage_key
            if not source_key.startswith(f"markets/{run.market_id}/"):
                raise ValueError("invalid_professionalization_source")
            source_path = storage_path_for_key(source_key)
            if not source_path.is_file():
                raise ValueError("invalid_professionalization_source")
        else:
            source_key = (
                f"markets/{run.market_id}/campaigns/{run.campaign_id}/"
                f"professionalization/{run.id}/approved-source.png"
            )
            source_path = storage_path_for_key(source_key)
            source_path.parent.mkdir(parents=True, exist_ok=True)
            await render_html_to_png(
                render_campaign_snapshot_html(snapshot, generated_at=datetime.now(UTC)),
                source_path,
            )
        run.source_image_storage_key = source_key
        await session.commit()

        profile = frozen_market_profile(snapshot)
        visibility = dict(profile.get("visibility") or {})
        logo_bytes = None
        logo_mime = None
        logo_key = profile.get("logo_key") if visibility.get("logo") else None
        if logo_key and str(logo_key).startswith(f"markets/{run.market_id}/"):
            logo_path = storage_path_for_key(str(logo_key))
            if logo_path.is_file():
                logo_bytes = logo_path.read_bytes()
                logo_mime = profile.get("logo_mime_type") or "image/png"
                run.logo_storage_key = str(logo_key)

        facts = immutable_brochure_facts(snapshot)
        invocation = await service._orchestrator.professionalize_brochure_image(
            capability=AICapability.BROCHURE_IMAGE_PROFESSIONALIZATION,
            system_prompt=BROCHURE_IMAGE_SYSTEM_PROMPT,
            immutable_facts=facts,
            source_image=source_path.read_bytes(),
            source_mime_type="image/png",
            logo_image=logo_bytes,
            logo_mime_type=logo_mime,
            visual_instruction=run.user_instruction,
        )
        candidate_key = (
            f"markets/{run.market_id}/campaigns/{run.campaign_id}/"
            f"professionalization/{run.id}/candidate.png"
        )
        candidate_path = storage_path_for_key(candidate_key)
        candidate_path.parent.mkdir(parents=True, exist_ok=True)
        candidate_path.write_bytes(invocation.output)
        run.candidate_image_storage_key = candidate_key
        run.provider = invocation.provider
        run.model = invocation.model
        run.status = "validating"
        session.add(
            AIUsageEvent(
                market_id=run.market_id,
                campaign_id=run.campaign_id,
                user_id=run.created_by_user_id,
                capability=run.capability,
                provider=run.provider,
                model=run.model,
                request_type="brochure_image_professionalization",
                status="success",
                input_tokens=invocation.usage.input_tokens,
                output_tokens=invocation.usage.output_tokens,
                latency_ms=invocation.latency_ms,
            )
        )
        await session.commit()
        logger.info(
            "professionalization.generated market_id=%s campaign_id=%s run_id=%s source_run_id=%s source_type=%s provider=%s model=%s latency_ms=%s timeout_seconds=%s",
            run.market_id,
            run.campaign_id,
            run.id,
            run.source_run_id,
            run.source_type,
            invocation.provider,
            invocation.model,
            invocation.latency_ms,
            settings.ai_image_http_timeout_seconds,
        )
        logger.info(
            "professionalization.validation_started market_id=%s campaign_id=%s run_id=%s source_run_id=%s source_type=%s",
            run.market_id,
            run.campaign_id,
            run.id,
            run.source_run_id,
            run.source_type,
        )

        validation = validate_generated_brochure(
            invocation.output,
            snapshot,
            logo_required=bool(logo_key),
            logo_image=logo_bytes,
        )
        run.validation_report_json = validation.report
        if not validation.accepted:
            evidence = validation.report.get("evidence_status")
            run.status = "rejected"
            run.error_code = str(validation.report.get("reason") or "validation_error")
            run.failure_category = {
                "mismatch": "validation_mismatch",
                "unverifiable": "validation_unverifiable",
                "technical_failure": "validation_technical",
            }.get(str(evidence), "validation")
            run.completed_at = datetime.now(UTC)
            await session.commit()
            logger.warning(
                "professionalization.validation_failed market_id=%s campaign_id=%s run_id=%s source_run_id=%s source_type=%s validation_reason=%s validation_category=%s",
                run.market_id,
                run.campaign_id,
                run.id,
                run.source_run_id,
                run.source_type,
                run.error_code,
                run.failure_category,
            )
            logger.warning(
                "professionalization.failed market_id=%s campaign_id=%s run_id=%s source_run_id=%s source_type=%s validation_reason=%s validation_category=%s",
                run.market_id,
                run.campaign_id,
                run.id,
                run.source_run_id,
                run.source_type,
                run.error_code,
                run.failure_category,
            )
            return

        output_key = (
            f"markets/{run.market_id}/campaigns/{run.campaign_id}/"
            f"professionalization/{run.id}/professional.png"
        )
        output_path = storage_path_for_key(output_key)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(invocation.output)
        campaign_file = CampaignFile(
            campaign_id=run.campaign_id,
            market_id=run.market_id,
            file_type="brochure_png",
            format="png",
            status="ready",
            storage_key=output_key,
            size_bytes=output_path.stat().st_size,
        )
        session.add(campaign_file)
        await session.flush()
        run.generated_image_storage_key = output_key
        run.generated_image_file_id = campaign_file.id
        run.status = "ready"
        run.is_active = False
        run.failure_category = None
        run.error_code = None
        run.completed_at = datetime.now(UTC)
        await session.commit()
        logger.info(
            "professionalization.validation_passed market_id=%s campaign_id=%s run_id=%s source_run_id=%s source_type=%s",
            run.market_id,
            run.campaign_id,
            run.id,
            run.source_run_id,
            run.source_type,
        )
        logger.info(
            "professionalization.completed market_id=%s campaign_id=%s run_id=%s source_run_id=%s source_type=%s provider=%s model=%s latency_ms=%s",
            run.market_id,
            run.campaign_id,
            run.id,
            run.source_run_id,
            run.source_type,
            run.provider,
            run.model,
            invocation.latency_ms,
        )
    except Exception as exc:  # noqa: BLE001 - original/active selection must survive every failure
        await session.rollback()
        run = await session.scalar(
            select(AIProfessionalizationRun)
            .where(AIProfessionalizationRun.id == run_id)
            .with_for_update()
        )
        if run is None:
            return
        run.status = "failed"
        error_code = getattr(exc, "code", None)
        if str(exc) == "invalid_professionalization_source":
            error_code = "snapshot_integrity_failed"
        run.error_code = error_code or "provider_error"
        if isinstance(exc, AIProviderTransientError) or run.error_code in TRANSIENT_FAILURE_CODES:
            run.failure_category = "transient_provider"
        elif run.candidate_image_storage_key:
            run.failure_category = "validation"
            run.error_code = "validation_error"
        else:
            run.failure_category = "provider"
        run.completed_at = datetime.now(UTC)
        if not run.candidate_image_storage_key:
            session.add(
                AIUsageEvent(
                    market_id=run.market_id,
                    campaign_id=run.campaign_id,
                    user_id=run.created_by_user_id,
                    capability=run.capability,
                    provider=getattr(exc, "provider", None) or run.provider,
                    model=getattr(exc, "model", None) or run.model,
                    request_type="brochure_image_professionalization",
                    status="timeout" if isinstance(exc, AIProviderTimeoutError) else "failed",
                    error_code=run.error_code,
                )
            )
        await session.commit()
        logger.warning(
            "professionalization.failed market_id=%s campaign_id=%s run_id=%s source_run_id=%s source_type=%s provider=%s model=%s timeout_seconds=%s validation_reason=%s validation_category=%s",
            run.market_id,
            run.campaign_id,
            run.id,
            run.source_run_id,
            run.source_type,
            run.provider,
            run.model,
            settings.ai_image_http_timeout_seconds,
            run.error_code,
            run.failure_category,
        )
