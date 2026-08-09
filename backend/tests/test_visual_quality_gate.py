"""Phase 28B: pure-Python tests for the visual quality gate (no Chromium needed).

Real-browser acceptance coverage lives in test_flyer_visual_acceptance.py.
These tests exercise score_from_metrics/_choose_refinement/_pick_winner
directly against synthetic LayoutMetrics/QualityScore, plus a few
run_visual_quality_gate orchestration tests with Playwright faked out.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Self
from uuid import uuid4

import pytest

from app.services.template_presets import FILL_BOOST_CONFIG_KEY
from app.services.visual_quality_gate import (
    QualityGateResult,
    _choose_refinement,
    _pick_winner,
    run_visual_quality_gate,
)
from app.services.visual_quality_scoring import (
    LayoutMetrics,
    QualityScore,
    ScoreContext,
    score_from_metrics,
)


def _metrics(**overrides) -> LayoutMetrics:
    base = {
        "viewport_width": 1240.0,
        "viewport_height": 1754.0,
        "card_count": 3,
        "cards_inside": True,
        "grid_inside": True,
        "no_card_overflow": True,
        "no_collisions": True,
        "no_stage_text_collision": True,
        "badges_inside": True,
        "prices_inside": True,
        "grid_area": 1_000_000.0,
        "total_card_area": 900_000.0,
        "bottom_gap_ratio": 0.02,
        "non_featured_card_areas": [300_000.0, 300_000.0, 300_000.0],
        "has_featured": False,
        "featured_area": None,
        "max_support_area": None,
        "featured_image_area": None,
        "max_support_image_area": None,
        "featured_price_size": None,
        "max_support_price_size": None,
        "price_width_ratios": [0.6, 0.6, 0.6],
        "price_clipped": False,
        "image_area_ratios": [0.35, 0.35, 0.35],
        "fallback_count": 0,
    }
    base.update(overrides)
    return LayoutMetrics(**base)


def _context(**overrides) -> ScoreContext:
    base = {"item_count": 3, "has_explicit_hero": False, "layout_name": "balanced-trio", "visual_mode": "default"}
    base.update(overrides)
    return ScoreContext(**base)


def _score(**overrides) -> QualityScore:
    base = {
        "overall_score": 80.0,
        "page_fill_score": 80.0,
        "whitespace_score": 80.0,
        "card_balance_score": 80.0,
        "hero_dominance_score": 100.0,
        "hero_dominance_applicable": False,
        "price_legibility_score": 80.0,
        "image_coverage_score": 80.0,
        "collision_score": 100.0,
        "overflow_score": 100.0,
        "issues": (),
    }
    base.update(overrides)
    return QualityScore(**base)


def _payload(**overrides) -> dict:
    base = {
        "template_slug": "supermarket-promo-4",
        "items": [
            {"id": "1", "name": "Coca Cola", "price": "29.90", "is_hero": True},
            {"id": "2", "name": "Eti Burcak", "price": "44.90", "is_hero": False},
            {"id": "3", "name": "Sutas Yogurt", "price": "74.90", "is_hero": False},
        ],
        "template_config": {},
        "builder_config": {"visual_density": "simple", "smart_composition": False},
    }
    base.update(overrides)
    return base


# --- score_from_metrics -------------------------------------------------

def test_healthy_layout_scores_high_with_no_issues() -> None:
    score = score_from_metrics(_metrics(), context=_context())
    assert score.overall_score >= 80.0
    assert score.issues == ()


def test_sparse_layout_flags_page_fill_and_whitespace() -> None:
    metrics = _metrics(total_card_area=350_000.0, bottom_gap_ratio=0.30, non_featured_card_areas=[300_000.0, 300_000.0])
    score = score_from_metrics(metrics, context=_context())
    assert score.page_fill_score < 65.0
    assert score.whitespace_score < 65.0
    assert "page_fill_low" in score.issues
    assert "whitespace_excessive" in score.issues


def test_overflow_detected_zeroes_overflow_score_and_penalizes_overall() -> None:
    healthy = score_from_metrics(_metrics(), context=_context())
    broken = score_from_metrics(_metrics(cards_inside=False), context=_context())
    assert broken.overflow_score == 0.0
    assert not broken.overflow_ok
    assert "overflow_detected" in broken.issues
    assert broken.overall_score < healthy.overall_score


def test_collision_detected_zeroes_collision_score() -> None:
    score = score_from_metrics(_metrics(no_collisions=False), context=_context())
    assert score.collision_score == 0.0
    assert not score.collision_ok
    assert "collision_detected" in score.issues


def test_hero_dominance_weak_when_hero_requested_but_flat() -> None:
    metrics = _metrics(
        has_featured=True,
        featured_area=300_000.0,
        max_support_area=300_000.0,
        featured_image_area=100_000.0,
        max_support_image_area=100_000.0,
        featured_price_size=30.0,
        max_support_price_size=30.0,
    )
    score = score_from_metrics(metrics, context=_context(has_explicit_hero=True))
    assert score.hero_dominance_applicable
    assert score.hero_dominance_score < 65.0
    assert "hero_dominance_weak" in score.issues


def test_hero_dominance_not_penalized_when_no_hero_requested() -> None:
    metrics = _metrics(has_featured=True, featured_area=300_000.0, max_support_area=300_000.0)
    score = score_from_metrics(metrics, context=_context(has_explicit_hero=False))
    assert not score.hero_dominance_applicable
    assert score.hero_dominance_score == 100.0
    assert "hero_dominance_weak" not in score.issues


def test_tiny_clipped_price_scores_low_and_flags_both_issues() -> None:
    metrics = _metrics(price_width_ratios=[0.10, 0.10, 0.10], price_clipped=True)
    score = score_from_metrics(metrics, context=_context())
    assert score.price_legibility_score <= 20.0
    assert "price_legibility_low" in score.issues
    assert "price_text_clipped" in score.issues


def test_fallback_images_are_capped_not_inflated() -> None:
    real_image = score_from_metrics(_metrics(image_area_ratios=[0.35, 0.35, 0.35], fallback_count=0), context=_context())
    all_fallback = score_from_metrics(_metrics(image_area_ratios=[], fallback_count=3), context=_context())
    assert "image_fallback_present" in all_fallback.issues
    assert "image_fallback_present" not in real_image.issues
    # A fallback card is capped at a fixed neutral score regardless of geometry -
    # it must never score as well as a genuinely healthy resolved-image card.
    assert all_fallback.image_coverage_score < real_image.image_coverage_score


# --- _choose_refinement --------------------------------------------------

def test_choose_refinement_bumps_price_prominence_when_absent() -> None:
    score = _score(overall_score=40.0, price_legibility_score=40.0, issues=("price_legibility_low",))
    choice = _choose_refinement(score, _payload())
    assert choice is not None
    refined_payload, action = choice
    assert refined_payload["template_config"]["price_prominence"] == "high"
    assert action == "price_prominence_high"


def test_choose_refinement_skips_price_bump_when_already_set() -> None:
    score = _score(overall_score=40.0, price_legibility_score=40.0, issues=("price_legibility_low",))
    payload = _payload(builder_config={"visual_density": "simple", "price_prominence": "medium"})
    assert _choose_refinement(score, payload) is None


def test_choose_refinement_applies_fill_boost_when_safe() -> None:
    score = _score(overall_score=40.0, page_fill_score=40.0, issues=("page_fill_low",))
    choice = _choose_refinement(score, _payload())
    assert choice is not None
    refined_payload, action = choice
    assert refined_payload["template_config"][FILL_BOOST_CONFIG_KEY] is True
    assert action == "fill_boost"


def test_choose_refinement_never_boosts_fill_on_already_broken_layout() -> None:
    score = _score(
        overall_score=20.0,
        page_fill_score=20.0,
        overflow_score=0.0,
        issues=("page_fill_low", "overflow_detected"),
    )
    assert _choose_refinement(score, _payload()) is None


def test_choose_refinement_returns_none_when_no_mapped_issue() -> None:
    score = _score(overall_score=40.0, card_balance_score=40.0, issues=("card_balance_uneven",))
    assert _choose_refinement(score, _payload()) is None


def test_choose_refinement_never_touches_items_hero_order_or_style_intent() -> None:
    payload = _payload(template_config={"header_style": "minimal"})
    score = _score(overall_score=40.0, price_legibility_score=40.0, page_fill_score=40.0, issues=("price_legibility_low", "page_fill_low"))
    refined_payload, _ = _choose_refinement(score, payload)
    assert refined_payload["items"] == payload["items"]
    assert refined_payload["builder_config"] == payload["builder_config"]
    assert refined_payload["template_config"]["header_style"] == "minimal"
    # Original input must never be mutated.
    assert payload["template_config"] == {"header_style": "minimal"}


# --- _pick_winner ---------------------------------------------------------

def test_pick_winner_refined_when_strictly_better_and_still_safe() -> None:
    initial = _score(overall_score=50.0)
    refined = _score(overall_score=70.0)
    assert _pick_winner(initial, refined) == "refined"


def test_pick_winner_vetoes_new_overflow() -> None:
    initial = _score(overall_score=50.0, overflow_score=100.0)
    refined = _score(overall_score=90.0, overflow_score=0.0)
    assert _pick_winner(initial, refined) == "initial"


def test_pick_winner_vetoes_new_collision() -> None:
    initial = _score(overall_score=50.0, collision_score=100.0)
    refined = _score(overall_score=90.0, collision_score=0.0)
    assert _pick_winner(initial, refined) == "initial"


def test_pick_winner_allows_refined_when_overflow_already_broken_and_not_worsened() -> None:
    initial = _score(overall_score=50.0, overflow_score=0.0)
    refined = _score(overall_score=70.0, overflow_score=0.0)
    assert _pick_winner(initial, refined) == "refined"


def test_pick_winner_initial_when_refined_is_none() -> None:
    assert _pick_winner(_score(), None) == "initial"


def test_pick_winner_ties_go_to_initial() -> None:
    initial = _score(overall_score=60.0)
    refined = _score(overall_score=60.0)
    assert _pick_winner(initial, refined) == "initial"


# --- run_visual_quality_gate orchestration -------------------------------

_FIXED_TIME = datetime(2026, 8, 9, tzinfo=UTC)


def test_gate_skips_scoring_for_non_supermarket_template(monkeypatch) -> None:
    def _boom(*_args, **_kwargs):
        raise AssertionError("scoring must not run for legacy templates")

    monkeypatch.setattr("app.services.visual_quality_gate.evaluate_layout_metrics_sync", _boom)
    payload = {"template_slug": "promo-4", "items": [{"id": "1", "name": "A", "price": "1.00"}]}
    result = run_visual_quality_gate(
        payload,
        generated_at=_FIXED_TIME,
        market_id=uuid4(),
        campaign_id=uuid4(),
        export_job_id=uuid4(),
    )
    assert result.applied is False
    assert result.skipped_reason == "non_supermarket_template"
    assert result.initial_score is None


class _FakePage:
    def set_content(self, html, wait_until=None) -> None:
        pass

    def close(self) -> None:
        pass


class _FakeBrowser:
    def __init__(self) -> None:
        self.closed = False

    def new_page(self, viewport=None) -> _FakePage:
        return _FakePage()

    def close(self) -> None:
        self.closed = True


class _FakeChromium:
    def __init__(self, browsers: list, launches: list) -> None:
        self._browsers = browsers
        self._launches = launches

    def launch(self) -> _FakeBrowser:
        self._launches.append(1)
        browser = _FakeBrowser()
        self._browsers.append(browser)
        return browser


class _FakePlaywrightContext:
    def __init__(self, browsers: list, launches: list) -> None:
        self.chromium = _FakeChromium(browsers, launches)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info) -> bool:
        return False


def _patch_fake_playwright(monkeypatch) -> tuple[list, list]:
    browsers: list = []
    launches: list = []
    monkeypatch.setattr(
        "playwright.sync_api.sync_playwright",
        lambda: _FakePlaywrightContext(browsers, launches),
    )
    return browsers, launches


def test_gate_launches_chromium_exactly_once_when_no_refinement_needed(monkeypatch) -> None:
    browsers, launches = _patch_fake_playwright(monkeypatch)
    monkeypatch.setattr(
        "app.services.visual_quality_gate.evaluate_layout_metrics_sync",
        lambda page: _metrics(),
    )
    payload = _payload(builder_config={})
    result = run_visual_quality_gate(
        payload,
        generated_at=_FIXED_TIME,
        market_id=uuid4(),
        campaign_id=uuid4(),
        export_job_id=uuid4(),
    )
    assert result.applied is False
    assert len(launches) == 1
    assert browsers[0].closed is True


def test_gate_launches_chromium_exactly_once_when_refinement_triggers(monkeypatch) -> None:
    browsers, launches = _patch_fake_playwright(monkeypatch)
    calls = {"count": 0}
    poor_metrics = _metrics(
        total_card_area=500_000.0,
        bottom_gap_ratio=0.15,
        price_width_ratios=[0.1, 0.1, 0.1],
        price_clipped=True,
    )

    def _fake_evaluate(page):
        calls["count"] += 1
        return poor_metrics if calls["count"] == 1 else _metrics()

    monkeypatch.setattr("app.services.visual_quality_gate.evaluate_layout_metrics_sync", _fake_evaluate)
    payload = _payload(builder_config={})
    result = run_visual_quality_gate(
        payload,
        generated_at=_FIXED_TIME,
        market_id=uuid4(),
        campaign_id=uuid4(),
        export_job_id=uuid4(),
    )
    assert calls["count"] == 2
    assert "price_prominence_high" in result.refinement_action.split("+")
    assert result.applied is True
    assert len(launches) == 1
    assert browsers[0].closed is True


def test_gate_closes_browser_even_when_evaluation_raises(monkeypatch) -> None:
    browsers, launches = _patch_fake_playwright(monkeypatch)

    def _boom(page):
        raise RuntimeError("chromium hiccup")

    monkeypatch.setattr("app.services.visual_quality_gate.evaluate_layout_metrics_sync", _boom)
    payload = _payload(builder_config={})
    with pytest.raises(RuntimeError):
        run_visual_quality_gate(
            payload,
            generated_at=_FIXED_TIME,
            market_id=uuid4(),
            campaign_id=uuid4(),
            export_job_id=uuid4(),
        )
    assert len(launches) == 1
    assert browsers[0].closed is True


def test_gate_falls_back_to_initial_when_refined_pass_raises(monkeypatch) -> None:
    _patch_fake_playwright(monkeypatch)
    calls = {"count": 0}
    poor_metrics = _metrics(
        total_card_area=500_000.0,
        bottom_gap_ratio=0.15,
        price_width_ratios=[0.1, 0.1, 0.1],
        price_clipped=True,
    )

    def _fake_evaluate(page):
        calls["count"] += 1
        if calls["count"] == 1:
            return poor_metrics
        raise RuntimeError("refined render failed")

    monkeypatch.setattr("app.services.visual_quality_gate.evaluate_layout_metrics_sync", _fake_evaluate)
    payload = _payload(builder_config={})
    result = run_visual_quality_gate(
        payload,
        generated_at=_FIXED_TIME,
        market_id=uuid4(),
        campaign_id=uuid4(),
        export_job_id=uuid4(),
    )
    assert result.applied is False
    assert result.refined_score is None
    assert isinstance(result, QualityGateResult)
