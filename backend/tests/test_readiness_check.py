"""Phase 30C: readiness_check.py must run its blocking Chromium/render probes
off the asyncio event-loop thread.

Playwright's Sync API raises immediately if invoked on a thread that already
has an asyncio event loop running (playwright.sync_api.Error: "It looks like
you are using Playwright Sync API inside the asyncio loop. Please use the
Async API instead."). run_checks() is itself an async coroutine, so calling
_check_chromium()/_check_render() directly reproduced that error even though
Chromium and the renderer both work fine outside of run_checks - a false
"Chromium is not available." / "PDF/PNG render failed." readiness report.
These tests pin the asyncio.to_thread boundary that fixes it, independent of
whether real Chromium is installed in the test environment.
"""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from typing import Self

import pytest

from scripts import readiness_check


def _stub_cheap_checks(monkeypatch) -> None:
    """Stub the DB/storage/telegram/template/security checks so tests only
    exercise the chromium/render async-boundary behavior under test."""
    monkeypatch.setattr(readiness_check, "_check_database", _ok_async)
    monkeypatch.setattr(readiness_check, "_check_storage", lambda: {"ok": True})
    monkeypatch.setattr(readiness_check, "_check_telegram_config", lambda: {"ok": True, "enabled": False})
    monkeypatch.setattr(readiness_check, "_check_supermarket_templates", _ok_async)
    monkeypatch.setattr(readiness_check, "_check_security_config", lambda: {"ok": True})


async def _ok_async() -> dict[str, object]:
    return {"ok": True}


class _FakePage:
    def set_content(self, html, wait_until=None) -> None:
        pass

    def pdf(self, *, path, **kwargs) -> None:
        Path(path).write_bytes(b"%PDF-1.4\n%fake-pdf\n%%EOF")

    def screenshot(self, *, path, **kwargs) -> None:
        # Keep the fake PNG under 24 bytes so validate_rendered_file's
        # signature-only compatibility path applies (real 2480x3508 dimension
        # checking is covered by the browser acceptance suite, not here).
        Path(path).write_bytes(b"\x89PNG\r\n\x1a\n")

    def close(self) -> None:
        pass


class _FakeBrowser:
    def new_page(self, viewport=None, device_scale_factor=None) -> _FakePage:
        return _FakePage()

    def close(self) -> None:
        pass


class _FakeChromium:
    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail

    def launch(self) -> _FakeBrowser:
        if self._fail:
            raise RuntimeError("chromium launch failed")
        return _FakeBrowser()


class _FakePlaywrightContext:
    def __init__(self, *, fail: bool = False) -> None:
        self.chromium = _FakeChromium(fail=fail)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info) -> bool:
        return False


def _patch_fake_playwright(monkeypatch, *, fail: bool = False) -> None:
    monkeypatch.setattr(
        "playwright.sync_api.sync_playwright",
        lambda: _FakePlaywrightContext(fail=fail),
    )


async def test_run_checks_executes_while_an_event_loop_is_active(monkeypatch) -> None:
    """run_checks() is itself a coroutine - asyncio.get_running_loop() must
    succeed for the whole call, proving the checks below run under a live loop
    rather than in some pre-loop synchronous setup path."""
    _stub_cheap_checks(monkeypatch)
    _patch_fake_playwright(monkeypatch)

    assert asyncio.get_running_loop() is not None
    report = await readiness_check.run_checks()

    assert report["status"] == "ok"


async def test_chromium_and_render_checks_do_not_run_on_the_event_loop_thread(monkeypatch) -> None:
    _stub_cheap_checks(monkeypatch)
    loop_thread_id = threading.get_ident()
    seen_thread_ids: dict[str, int] = {}

    def fake_chromium() -> dict[str, object]:
        seen_thread_ids["chromium"] = threading.get_ident()
        return {"ok": True}

    def fake_render() -> dict[str, object]:
        seen_thread_ids["render"] = threading.get_ident()
        return {"ok": True, "pdf": True, "png": True}

    monkeypatch.setattr(readiness_check, "_check_chromium", fake_chromium)
    monkeypatch.setattr(readiness_check, "_check_render", fake_render)

    report = await readiness_check.run_checks()

    assert report["status"] == "ok"
    assert seen_thread_ids["chromium"] != loop_thread_id
    assert seen_thread_ids["render"] != loop_thread_id


async def test_calling_sync_playwright_checks_directly_on_the_loop_thread_fails() -> None:
    """Documents the exact failure this hotfix avoids: Playwright's own guard
    rejects Sync API usage on a thread with a running asyncio event loop, even
    when Chromium itself is fully installed and otherwise launchable."""
    from playwright.sync_api import Error as PlaywrightSyncError
    from playwright.sync_api import sync_playwright

    with pytest.raises(PlaywrightSyncError, match="asyncio loop"), sync_playwright() as playwright:
        playwright.chromium.launch()


async def test_chromium_check_success_reports_ok_true(monkeypatch) -> None:
    _patch_fake_playwright(monkeypatch)

    result = await asyncio.to_thread(readiness_check._check_chromium)

    assert result == {"ok": True}


async def test_render_check_success_reports_pdf_and_png_true(monkeypatch) -> None:
    _patch_fake_playwright(monkeypatch)

    result = await asyncio.to_thread(readiness_check._check_render)

    assert result == {"ok": True, "pdf": True, "png": True}


async def test_chromium_check_failure_is_a_safe_structured_failure(monkeypatch) -> None:
    _patch_fake_playwright(monkeypatch, fail=True)

    result = await asyncio.to_thread(readiness_check._check_chromium)

    assert result["ok"] is False
    assert result["stage"] == "chromium_launch"
    assert result["error_type"] == "RuntimeError"
    assert result["detail"] == "Chromium launch failed."
    # No secret/internal exception text (e.g. the raw "chromium launch failed"
    # message) leaks into the reported detail.
    assert "chromium launch failed" not in str(result["detail"])


async def test_render_check_failure_is_a_safe_structured_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        readiness_check,
        "render_html_to_pdf_sync",
        lambda html, output_path: (_ for _ in ()).throw(RuntimeError("boom: /secret/path leaked")),
    )

    result = await asyncio.to_thread(readiness_check._check_render)

    assert result["ok"] is False
    assert result["stage"] == "render"
    assert result["error_type"] == "RuntimeError"
    assert result["detail"] == "PDF/PNG render failed."
    assert "/secret/path" not in str(result["detail"])


async def test_run_checks_reports_not_ready_when_chromium_check_fails(monkeypatch) -> None:
    _stub_cheap_checks(monkeypatch)
    _patch_fake_playwright(monkeypatch, fail=True)

    report = await readiness_check.run_checks()

    assert report["status"] == "not_ready"
    assert report["checks"]["chromium"]["ok"] is False
    assert report["checks"]["render"]["ok"] is False


async def test_run_checks_leaves_db_template_security_storage_telegram_checks_unchanged(monkeypatch) -> None:
    """Chromium/render is the only behavior this hotfix touches - the other
    five checks must still be produced by calling the exact same health.py
    functions readiness_check.py already imported before this change."""
    sentinel_calls: list[str] = []

    async def fake_database() -> dict[str, object]:
        sentinel_calls.append("database")
        return {"ok": True}

    def fake_storage() -> dict[str, object]:
        sentinel_calls.append("storage")
        return {"ok": True}

    def fake_telegram() -> dict[str, object]:
        sentinel_calls.append("telegram_config")
        return {"ok": True, "enabled": False}

    async def fake_templates() -> dict[str, object]:
        sentinel_calls.append("supermarket_templates")
        return {"ok": True, "published_presets": []}

    def fake_security() -> dict[str, object]:
        sentinel_calls.append("security_config")
        return {"ok": True}

    monkeypatch.setattr(readiness_check, "_check_database", fake_database)
    monkeypatch.setattr(readiness_check, "_check_storage", fake_storage)
    monkeypatch.setattr(readiness_check, "_check_telegram_config", fake_telegram)
    monkeypatch.setattr(readiness_check, "_check_supermarket_templates", fake_templates)
    monkeypatch.setattr(readiness_check, "_check_security_config", fake_security)
    _patch_fake_playwright(monkeypatch)

    report = await readiness_check.run_checks()

    assert set(sentinel_calls) == {
        "database",
        "storage",
        "telegram_config",
        "supermarket_templates",
        "security_config",
    }
    assert report["checks"]["database"] == {"ok": True}
    assert report["checks"]["storage"] == {"ok": True}
    assert report["checks"]["telegram_config"] == {"ok": True, "enabled": False}
    assert report["checks"]["supermarket_templates"] == {"ok": True, "published_presets": []}
    assert report["checks"]["security_config"] == {"ok": True}
