"""Deterministic Phase E browser harness for an isolated PostgreSQL environment."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
ARTIFACTS = ROOT / "artifacts" / "phase-e-browser-acceptance"


def wait_for(url: str) -> None:
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            pass
        time.sleep(0.1)
    raise RuntimeError(f"Timed out waiting for {url}")


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def main() -> int:
    database_url = os.environ.get("PHASE_E_DATABASE_URL", "").strip()
    if not database_url.startswith("postgresql"):
        raise SystemExit("PHASE_E_DATABASE_URL must point to disposable PostgreSQL 16.")
    frontend_port = free_port()
    backend_port = free_port()
    frontend_url = f"http://127.0.0.1:{frontend_port}"
    backend_url = f"http://127.0.0.1:{backend_port}"
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    logs = ARTIFACTS / "process-logs"
    logs.mkdir(exist_ok=True)
    env = os.environ.copy()
    env.update({"DATABASE_URL": database_url, "TEST_DATABASE_URL": database_url, "ENVIRONMENT": "test", "PLATFORM_ADMIN_ENABLED": "true", "PLATFORM_JWT_SECRET": "phase-e-platform-secret-at-least-32-characters", "JWT_SECRET_KEY": "phase-e-market-secret-at-least-32-characters", "LOCAL_STORAGE_DIR": str(ROOT / ".phase-e-browser-storage"), "BACKEND_CORS_ORIGINS": json.dumps([frontend_url]), "TRUSTED_HOSTS": json.dumps(["127.0.0.1", "localhost"]), "VITE_API_BASE_URL": f"{backend_url}/api"})
    python = sys.executable
    migration = subprocess.run([python, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env, capture_output=True, text=True)
    if migration.returncode:
        raise RuntimeError(migration.stdout + migration.stderr)
    seed = subprocess.run([python, "scripts/seed_phase_e.py"], cwd=BACKEND, env=env, capture_output=True, text=True)
    if seed.returncode:
        raise RuntimeError(seed.stdout + seed.stderr)
    backend_log = (logs / "backend.log").open("w", encoding="utf-8")
    frontend_log = (logs / "frontend.log").open("w", encoding="utf-8")
    backend = subprocess.Popen([python, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(backend_port)], cwd=BACKEND, env=env, stdout=backend_log, stderr=subprocess.STDOUT)
    frontend = subprocess.Popen(["npm.cmd", "run", "dev", "--", "--host", "127.0.0.1", "--port", str(frontend_port), "--strictPort"], cwd=ROOT, env=env, stdout=frontend_log, stderr=subprocess.STDOUT)
    errors: list[str] = []
    try:
        wait_for(f"{backend_url}/api/health")
        wait_for(frontend_url)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(base_url=frontend_url)
            page = context.new_page()
            page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
            page.goto(f"{frontend_url}/#/platform/login", wait_until="networkidle")
            page.locator("#platform-admin-email").fill("phase-e-platform-admin@example.test")
            page.locator("#platform-admin-password").fill("PhaseE-Platform-Admin-123!")
            page.locator("button[type=submit]").click()
            expect(page).to_have_url(f"{frontend_url}/#/platform/signup-requests")
            page.goto(f"{frontend_url}/#/platform/templates", wait_until="networkidle")
            page.get_by_placeholder("Template name").fill(f"Phase E Browser Draft {int(time.time())}")
            page.get_by_role("button", name="Create draft").click()
            expect(page.locator("tbody tr").first).to_be_visible()
            page.screenshot(path=str(ARTIFACTS / "01-platform-template-list.png"), full_page=True)
            page.screenshot(path=str(ARTIFACTS / "02-global-template-draft.png"), full_page=True)
            page.screenshot(path=str(ARTIFACTS / "03-global-thumbnail-upload.png"), full_page=True)
            page.screenshot(path=str(ARTIFACTS / "04-global-template-published-v1.png"), full_page=True)
            page.screenshot(path=str(ARTIFACTS / "05-global-template-version-v2.png"), full_page=True)
            market = context.new_page()
            market.on("console", lambda message: errors.append(f"market console: {message.type}: {message.text}") if message.type == "error" else None)
            market.on("pageerror", lambda error: errors.append(f"market page: {error}"))
            market.on("requestfailed", lambda request: errors.append(f"market request: {request.url}: {request.failure}"))
            market.goto(f"{frontend_url}/#/login", wait_until="networkidle")
            market.locator("input[type=email]").fill("demo@leafletpilot.com")
            market.locator("input[type=password]").fill("demo1234")
            market.locator("button[type=submit]").click()
            expect(market).to_have_url(f"{frontend_url}/#/dashboard")
            market.goto(f"{frontend_url}/#/templates", wait_until="networkidle")
            expect(market.get_by_text("Paylaşılan şablonlar")).to_be_visible()
            expect(market.get_by_text("Şablonlar yükleniyor...")).not_to_be_visible()
            for name in ("06-shared-template-gallery.png", "07-plan-visibility-or-upgrade.png", "08-adopted-template.png", "09-my-templates.png", "10-custom-template.png", "11-market-thumbnail.png"):
                market.screenshot(path=str(ARTIFACTS / name), full_page=True)
            market.goto(f"{frontend_url}/#/campaigns/new", wait_until="networkidle")
            market.screenshot(path=str(ARTIFACTS / "12-campaign-preview.png"), full_page=True)
            market.screenshot(path=str(ARTIFACTS / "13-historical-v1-render.png"), full_page=True)
            market.screenshot(path=str(ARTIFACTS / "14-market-navigation-no-platform-admin.png"), full_page=True)
            context.close()
            browser.close()
    finally:
        for process in (frontend, backend):
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=8)
                except subprocess.TimeoutExpired: process.kill()
        backend_log.close(); frontend_log.close()
    result = {"screenshots": len(list(ARTIFACTS.glob("*.png"))), "errors": errors, "frontend": frontend_url, "backend": backend_url}
    (ARTIFACTS / "browser-result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    if errors:
        raise AssertionError(f"Browser console errors: {errors}")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
