"""One-pass deterministic visual-quality gate for the supermarket renderer (Phase 28B).

Orchestration only: renders a payload, scores it (visual_quality_scoring.py),
and - when the score is below threshold - renders exactly one bounded,
rule-based refinement candidate, scores that too, and keeps whichever is
safely better. Never touches campaign facts, item order, hero targeting, or
user-selected style intent (visual_density/header_style/card_style/
badge_style/image_treatment); `smart_composition` is deliberately excluded as
a lever because it reorders items via merchandising.create_composition_plan.

Legacy (non-supermarket) templates are a no-op passthrough: no scoring, no
Chromium launch, identical output to calling render_render_payload_html
directly.
"""

from __future__ import annotations

import logging
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from app.services.preview_renderer import (
    SUPERMARKET_LAYOUTS,
    _render_refinement_profile,
    render_render_payload_html,
)
from app.services.template_presets import FILL_BOOST_CONFIG_KEY
from app.services.visual_quality_scoring import (
    QualityScore,
    ScoreContext,
    evaluate_layout_metrics_sync,
    score_from_metrics,
)

logger = logging.getLogger(__name__)

QUALITY_THRESHOLD = 72.0
_VIEWPORT = {"width": 1240, "height": 1754}


@dataclass(frozen=True)
class QualityGateResult:
    html: str
    initial_score: QualityScore | None
    refined_score: QualityScore | None
    refinement_action: str | None
    applied: bool
    skipped_reason: str | None = None


def run_visual_quality_gate(
    payload: dict,
    *,
    generated_at: datetime,
    market_id: UUID,
    campaign_id: UUID,
    export_job_id: UUID,
) -> QualityGateResult:
    if payload.get("template_slug") not in SUPERMARKET_LAYOUTS:
        return _skip_gate(payload, generated_at=generated_at, market_id=market_id, campaign_id=campaign_id, export_job_id=export_job_id)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            return run_visual_quality_gate_with_browser(
                browser,
                payload,
                generated_at=generated_at,
                market_id=market_id,
                campaign_id=campaign_id,
                export_job_id=export_job_id,
            )
        finally:
            browser.close()


def run_visual_quality_gate_with_browser(
    browser: object,
    payload: dict,
    *,
    generated_at: datetime,
    market_id: UUID,
    campaign_id: UUID,
    export_job_id: UUID,
) -> QualityGateResult:
    """Run the gate against a caller-owned Chromium browser.

    Unlike run_visual_quality_gate, this never launches or closes `browser` -
    callers that already hold one open (e.g. the export pipeline sharing a
    single browser across gate + refinement + PDF + PNG) use this to avoid a
    second launch. The non-supermarket skip path still applies and never
    touches `browser`.
    """
    if payload.get("template_slug") not in SUPERMARKET_LAYOUTS:
        return _skip_gate(payload, generated_at=generated_at, market_id=market_id, campaign_id=campaign_id, export_job_id=export_job_id)

    context = _build_score_context(payload)
    result, winner = _run_gate_with_browser(browser, payload, context, generated_at=generated_at, market_id=market_id, campaign_id=campaign_id, export_job_id=export_job_id)
    _log_result(market_id, campaign_id, export_job_id, result, winner=winner)
    return result


def _skip_gate(
    payload: dict,
    *,
    generated_at: datetime,
    market_id: UUID,
    campaign_id: UUID,
    export_job_id: UUID,
) -> QualityGateResult:
    html = render_render_payload_html(payload, generated_at=generated_at)
    logger.debug(
        "Visual quality gate skipped for non-supermarket template.",
        extra={"market_id": str(market_id), "campaign_id": str(campaign_id), "export_job_id": str(export_job_id)},
    )
    return QualityGateResult(
        html=html,
        initial_score=None,
        refined_score=None,
        refinement_action=None,
        applied=False,
        skipped_reason="non_supermarket_template",
    )


def _run_gate_with_browser(
    browser: object,
    payload: dict,
    context: ScoreContext,
    *,
    generated_at: datetime,
    market_id: UUID,
    campaign_id: UUID,
    export_job_id: UUID,
) -> tuple[QualityGateResult, str]:
    html_initial = render_render_payload_html(payload, generated_at=generated_at)
    score_initial = _score_html(browser, html_initial, context)

    if score_initial.overall_score >= QUALITY_THRESHOLD:
        return (
            QualityGateResult(html=html_initial, initial_score=score_initial, refined_score=None, refinement_action=None, applied=False),
            "initial",
        )

    choice = _choose_refinement(score_initial, payload)
    if choice is None:
        return (
            QualityGateResult(html=html_initial, initial_score=score_initial, refined_score=None, refinement_action=None, applied=False),
            "initial",
        )

    refined_payload, action = choice
    try:
        html_refined = render_render_payload_html(refined_payload, generated_at=generated_at)
        score_refined = _score_html(browser, html_refined, context)
    except Exception:
        logger.warning(
            "Visual quality gate refinement pass failed; falling back to the original render.",
            exc_info=True,
            extra={"market_id": str(market_id), "campaign_id": str(campaign_id), "export_job_id": str(export_job_id)},
        )
        return (
            QualityGateResult(html=html_initial, initial_score=score_initial, refined_score=None, refinement_action=action, applied=False),
            "initial",
        )

    winner = _pick_winner(score_initial, score_refined)
    chosen_html = html_refined if winner == "refined" else html_initial
    return (
        QualityGateResult(html=chosen_html, initial_score=score_initial, refined_score=score_refined, refinement_action=action, applied=(winner == "refined")),
        winner,
    )


def _score_html(browser: object, html: str, context: ScoreContext) -> QualityScore:
    page = browser.new_page(viewport=_VIEWPORT)  # type: ignore[attr-defined]
    try:
        page.set_content(html, wait_until="networkidle")
        metrics = evaluate_layout_metrics_sync(page)
    finally:
        page.close()
    return score_from_metrics(metrics, context=context)


def _build_score_context(payload: dict) -> ScoreContext:
    items = list(payload.get("items") or [])
    refinement_config = {
        **dict(payload.get("template_config") or {}),
        **dict(payload.get("builder_config") or {}),
    }
    refinement = _render_refinement_profile(items, refinement_config)
    return ScoreContext(
        item_count=len(items),
        has_explicit_hero=any(bool(item.get("is_hero")) for item in items),
        layout_name=refinement["layout"],
        visual_mode=refinement["visual_mode"],
    )


def _choose_refinement(score: QualityScore, payload: dict) -> tuple[dict, str] | None:
    """Return (refined_payload, action_label) for one safe, additive-only lever, or None.

    Never mutates `payload`; the refined copy is used for a single extra
    render only and is never persisted back to campaign.builder_config_json,
    so the same input always re-derives the same decision.
    """
    template_config = dict(payload.get("template_config") or {})
    builder_config = dict(payload.get("builder_config") or {})
    issues = set(score.issues)
    overrides: dict[str, object] = {}
    actions: list[str] = []

    if (issues & {"price_legibility_low", "price_text_clipped"}) and (
        "price_prominence" not in template_config and "price_prominence" not in builder_config
    ):
        overrides["price_prominence"] = "high"
        actions.append("price_prominence_high")

    if (
        (issues & {"page_fill_low", "whitespace_excessive"})
        and score.overflow_ok
        and score.collision_ok
        and FILL_BOOST_CONFIG_KEY not in template_config
        and FILL_BOOST_CONFIG_KEY not in builder_config
    ):
        overrides[FILL_BOOST_CONFIG_KEY] = True
        actions.append("fill_boost")

    if not actions:
        return None

    refined_payload = deepcopy(payload)
    refined_template_config = dict(refined_payload.get("template_config") or {})
    refined_template_config.update(overrides)
    refined_payload["template_config"] = refined_template_config
    return refined_payload, "+".join(actions)


def _pick_winner(initial: QualityScore, refined: QualityScore | None) -> Literal["initial", "refined"]:
    if refined is None:
        return "initial"
    if initial.overflow_ok and not refined.overflow_ok:
        return "initial"
    if initial.collision_ok and not refined.collision_ok:
        return "initial"
    if refined.overall_score > initial.overall_score:
        return "refined"
    return "initial"


def _log_result(market_id: UUID, campaign_id: UUID, export_job_id: UUID, result: QualityGateResult, *, winner: str) -> None:
    logger.info(
        "Visual quality gate evaluated campaign render.",
        extra={
            "market_id": str(market_id),
            "campaign_id": str(campaign_id),
            "export_job_id": str(export_job_id),
            "initial_overall_score": result.initial_score.overall_score if result.initial_score else None,
            "initial_issues": list(result.initial_score.issues) if result.initial_score else [],
            "refinement_action": result.refinement_action,
            "refined_overall_score": result.refined_score.overall_score if result.refined_score else None,
            "winner": winner,
            "applied": result.applied,
        },
    )
