"""First-customer readiness check (Phase 29 / section L).

Verifies the dependencies the automated Telegram flow needs before letting a
real customer send a product list: DB, local storage, Telegram config
presence, published supermarket presets, Chromium availability, and an
actual PDF + PNG render/validate round trip.

Never prints secret values (tokens/webhook secrets) - only booleans.

Run with: python -m scripts.readiness_check
Exit code 0 = ready, 1 = not ready.
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.routes.health import (
    _check_database,
    _check_security_config,
    _check_storage,
    _check_supermarket_templates,
    _check_telegram_config,
)
from app.core.database import engine
from app.services.rendering import (
    render_html_to_pdf_sync,
    render_html_to_png_sync,
    validate_rendered_file,
)


def _check_chromium() -> dict[str, object]:
    """Blocking Chromium launch probe.

    Must never be awaited directly - it uses Playwright's Sync API, which
    raises immediately if called on a thread already running an asyncio event
    loop. Callers run this via asyncio.to_thread (see run_checks).
    """
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            browser.close()
    except Exception as exc:
        return {
            "ok": False,
            "stage": "chromium_launch",
            "error_type": type(exc).__name__,
            "detail": "Chromium launch failed.",
        }
    return {"ok": True}


def _check_render() -> dict[str, object]:
    """Blocking PDF/PNG render probe - same Sync API / event-loop constraint
    as _check_chromium; run via asyncio.to_thread (see run_checks)."""
    from app.services.preview_renderer import render_render_payload_html

    payload = {
        "contract_version": 2,
        "template_slug": "supermarket-promo-4",
        "title": "Readiness check",
        "market_name": "Readiness",
        "items": [
            {"name": f"Readiness product {i + 1}", "price": f"{i + 1}.99", "currency": "EUR"}
            for i in range(4)
        ],
    }
    try:
        html = render_render_payload_html(payload, generated_at=datetime.now(UTC))
        with tempfile.TemporaryDirectory(prefix="leafletpilot-readiness-") as tmp:
            pdf_path = Path(tmp) / "readiness.pdf"
            png_path = Path(tmp) / "readiness.png"
            render_html_to_pdf_sync(html, pdf_path)
            render_html_to_png_sync(html, png_path)
            validate_rendered_file(pdf_path, "pdf")
            validate_rendered_file(png_path, "png")
    except Exception as exc:
        return {
            "ok": False,
            "stage": "render",
            "error_type": type(exc).__name__,
            "detail": "PDF/PNG render failed.",
        }
    return {"ok": True, "pdf": True, "png": True}


async def run_checks() -> dict[str, object]:
    checks: dict[str, object] = {
        "database": await _check_database(),
        "storage": _check_storage(),
        "telegram_config": _check_telegram_config(),
        "supermarket_templates": await _check_supermarket_templates(),
        "security_config": _check_security_config(),
    }
    # _check_chromium/_check_render use Playwright's Sync API, which refuses
    # to run on a thread that already has an asyncio event loop active. Run
    # them off-thread (sequentially, to avoid two Chromium processes at once)
    # rather than awaiting them directly on this coroutine's thread.
    checks["chromium"] = await asyncio.to_thread(_check_chromium)
    checks["render"] = await asyncio.to_thread(_check_render)
    all_ok = all(check["ok"] for check in checks.values())  # type: ignore[index]
    return {"status": "ok" if all_ok else "not_ready", "checks": checks}


async def main() -> int:
    try:
        report = await run_checks()
    finally:
        if engine is not None:
            await engine.dispose()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
