"""Phase 30B: shared-browser lifecycle tests for _render_campaign_assets_sync.

Real-browser output/geometry acceptance coverage stays in
test_flyer_visual_acceptance.py; these tests fake Playwright out (same
pattern as test_visual_quality_gate.py) to assert the *lifecycle* contract:
gate + refinement + PDF + PNG share exactly one Chromium launch per export,
the browser always closes (success or failure), and independent renders
never share browser state.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Self
from uuid import uuid4

import pytest

from app.services.rendering import _render_campaign_assets_sync
from app.services.visual_quality_scoring import LayoutMetrics

_FIXED_TIME = datetime(2026, 8, 9, tzinfo=UTC)

_GOOD_METRICS = {
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


def _metrics(**overrides) -> LayoutMetrics:
    base = dict(_GOOD_METRICS)
    base.update(overrides)
    return LayoutMetrics(**base)


def _poor_metrics() -> LayoutMetrics:
    return _metrics(
        total_card_area=500_000.0,
        bottom_gap_ratio=0.15,
        price_width_ratios=[0.1, 0.1, 0.1],
        price_clipped=True,
    )


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


class _FakePage:
    def __init__(self, log: list[str]) -> None:
        self._log = log
        self.closed = False

    def set_content(self, html, wait_until=None) -> None:
        self._log.append("set_content")

    def pdf(self, *, path, **kwargs) -> None:
        Path(path).write_bytes(b"%PDF-1.4\n%fake-pdf\n%%EOF")
        self._log.append("pdf")

    def screenshot(self, *, path, **kwargs) -> None:
        Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
        self._log.append("screenshot")

    def close(self) -> None:
        self.closed = True
        self._log.append("close")


class _FakeBrowser:
    def __init__(self) -> None:
        self.closed = False
        self.pages: list[_FakePage] = []
        self.page_log: list[str] = []

    def new_page(self, viewport=None, device_scale_factor=None) -> _FakePage:
        page = _FakePage(self.page_log)
        self.pages.append(page)
        return page

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


def _run(tmp_path: Path, *, formats: tuple[str, ...] = ("pdf", "png"), **kwargs) -> dict[str, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    output_paths = {fmt: tmp_path / f"out.{fmt}" for fmt in formats}
    _render_campaign_assets_sync(
        kwargs.pop("payload", _payload()),
        generated_at=_FIXED_TIME,
        market_id=uuid4(),
        campaign_id=uuid4(),
        export_job_id=uuid4(),
        apply_output_format=True,
        output_paths=output_paths,
        **kwargs,
    )
    return output_paths


def test_no_refinement_path_launches_chromium_exactly_once(tmp_path, monkeypatch) -> None:
    browsers, launches = _patch_fake_playwright(monkeypatch)
    monkeypatch.setattr("app.services.visual_quality_gate.evaluate_layout_metrics_sync", lambda page: _metrics())

    output_paths = _run(tmp_path)

    assert len(launches) == 1
    assert len(browsers) == 1
    assert browsers[0].closed is True
    assert output_paths["pdf"].read_bytes().startswith(b"%PDF-")
    assert output_paths["png"].read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_refinement_path_still_launches_chromium_exactly_once(tmp_path, monkeypatch) -> None:
    browsers, launches = _patch_fake_playwright(monkeypatch)
    calls = {"count": 0}

    def _fake_evaluate(page):
        calls["count"] += 1
        return _poor_metrics() if calls["count"] == 1 else _metrics()

    monkeypatch.setattr("app.services.visual_quality_gate.evaluate_layout_metrics_sync", _fake_evaluate)

    output_paths = _run(tmp_path)

    assert calls["count"] == 2
    assert len(launches) == 1
    assert browsers[0].closed is True
    # 2 gate scoring pages (initial + refined) + 1 pdf + 1 png, all on one browser.
    assert len(browsers[0].pages) == 4
    assert output_paths["pdf"].read_bytes().startswith(b"%PDF-")
    assert output_paths["png"].read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_only_requested_formats_are_rendered(tmp_path, monkeypatch) -> None:
    browsers, launches = _patch_fake_playwright(monkeypatch)
    monkeypatch.setattr("app.services.visual_quality_gate.evaluate_layout_metrics_sync", lambda page: _metrics())

    output_paths = _run(tmp_path, formats=("pdf",))

    assert len(launches) == 1
    assert output_paths["pdf"].exists()
    # One gate scoring page + one pdf page; no png page ever opened.
    assert len(browsers[0].pages) == 2


def test_browser_closes_when_gate_evaluation_raises(tmp_path, monkeypatch) -> None:
    browsers, launches = _patch_fake_playwright(monkeypatch)

    def _boom(page):
        raise RuntimeError("chromium hiccup")

    monkeypatch.setattr("app.services.visual_quality_gate.evaluate_layout_metrics_sync", _boom)

    with pytest.raises(RuntimeError, match="chromium hiccup"):
        _run(tmp_path)

    assert len(launches) == 1
    assert browsers[0].closed is True


def test_browser_closes_when_png_render_raises(tmp_path, monkeypatch) -> None:
    browsers, launches = _patch_fake_playwright(monkeypatch)
    monkeypatch.setattr("app.services.visual_quality_gate.evaluate_layout_metrics_sync", lambda page: _metrics())
    monkeypatch.setattr(
        "app.services.rendering._render_png_page",
        lambda browser, html, output_path: (_ for _ in ()).throw(RuntimeError("png render failed")),
    )

    with pytest.raises(RuntimeError, match="png render failed"):
        _run(tmp_path)

    assert len(launches) == 1
    assert browsers[0].closed is True


def test_subsequent_render_after_failure_succeeds_independently(tmp_path, monkeypatch) -> None:
    browsers, launches = _patch_fake_playwright(monkeypatch)
    state = {"fail": True}

    def _flaky_evaluate(page):
        if state["fail"]:
            raise RuntimeError("first render is broken")
        return _metrics()

    monkeypatch.setattr("app.services.visual_quality_gate.evaluate_layout_metrics_sync", _flaky_evaluate)

    with pytest.raises(RuntimeError, match="first render is broken"):
        _run(tmp_path / "attempt-1")

    assert len(launches) == 1
    assert browsers[0].closed is True

    state["fail"] = False
    output_paths = _run(tmp_path / "attempt-2")

    assert len(launches) == 2
    assert browsers[1] is not browsers[0]
    assert browsers[1].closed is True
    assert output_paths["pdf"].exists()
    assert output_paths["png"].exists()


@pytest.mark.asyncio
async def test_simultaneous_independent_renders_do_not_leak_browser_state(tmp_path, monkeypatch) -> None:
    browsers, launches = _patch_fake_playwright(monkeypatch)
    monkeypatch.setattr("app.services.visual_quality_gate.evaluate_layout_metrics_sync", lambda page: _metrics())

    dir_a = tmp_path / "campaign-a"
    dir_b = tmp_path / "campaign-b"
    dir_a.mkdir()
    dir_b.mkdir()

    results = await asyncio.gather(
        asyncio.to_thread(_run, dir_a, payload=_payload(items=[{"id": "a", "name": "A", "price": "1.00"}])),
        asyncio.to_thread(_run, dir_b, payload=_payload(items=[{"id": "b", "name": "B", "price": "2.00"}])),
    )

    assert len(launches) == 2
    assert len(browsers) == 2
    assert browsers[0] is not browsers[1]
    assert browsers[0].closed is True
    assert browsers[1].closed is True

    paths_a, paths_b = results
    assert paths_a["pdf"].exists() and paths_a["png"].exists()
    assert paths_b["pdf"].exists() and paths_b["png"].exists()
    # Each render wrote into its own campaign directory only.
    assert set(dir_a.iterdir()) == {paths_a["pdf"], paths_a["png"]}
    assert set(dir_b.iterdir()) == {paths_b["pdf"], paths_b["png"]}
