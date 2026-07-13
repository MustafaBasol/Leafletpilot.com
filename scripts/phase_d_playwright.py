"""Deterministic local Phase D browser acceptance harness.

Requires PHASE_D_DATABASE_URL to point to an isolated disposable PostgreSQL 16
database. The harness owns API/Vite processes, readiness probes, logs, and
Playwright cleanup; it never targets production.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from playwright.sync_api import Browser, Page, expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
ARTIFACTS = ROOT / "artifacts" / "phase-d-browser-acceptance"
PLATFORM_EMAIL = "phase-d-platform-admin@example.test"
PLATFORM_PASSWORD = "PhaseD-Platform-Admin-123!"
MARKET_EMAIL = "demo@leafletpilot.com"
MARKET_PASSWORD = "demo1234"


def http_get(url: str) -> tuple[int, str]:
    try:
        with urlopen(Request(url, method="GET"), timeout=1) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def wait_for_http(url: str, expected: set[int], label: str) -> tuple[int, str]:
    deadline = time.monotonic() + 30
    last_error = "no response"
    while time.monotonic() < deadline:
        try:
            status, body = http_get(url)
            if status in expected:
                return status, body
            last_error = f"HTTP {status}: {body[:300]}"
        except (OSError, URLError) as exc:
            last_error = str(exc)
        time.sleep(0.1)
    raise RuntimeError(f"{label} readiness timed out at {url}: {last_error}")


def assert_port_free(host: str, port: int, label: str) -> None:
    with socket.socket() as probe:
        probe.settimeout(0.2)
        if probe.connect_ex((host, port)) == 0:
            raise RuntimeError(f"{label} port {host}:{port} is already in use")


def start_process(command: list[str], cwd: Path, env: dict[str, str], log_path: Path) -> subprocess.Popen[str]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handle = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen(command, cwd=cwd, env=env, stdout=handle, stderr=subprocess.STDOUT, text=True)
    process._phase_d_log_handle = handle  # type: ignore[attr-defined]
    return process


def stop_process(process: subprocess.Popen[str] | None) -> None:
    if process is None:
        return
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    handle = getattr(process, "_phase_d_log_handle", None)
    if handle:
        handle.close()


def run_browser(frontend_url: str) -> dict[str, int]:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    with sync_playwright() as playwright:
        browser: Browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(base_url=frontend_url)
        page: Page = context.new_page()
        page.on("console", lambda message: errors.append(f"console: {message.text}") if message.type == "error" else None)
        page.on("pageerror", lambda error: errors.append(f"page: {error}"))
        page.on("requestfailed", lambda request: errors.append(f"request: {request.url}: {request.failure}"))
        page.goto(f"{frontend_url}/#/platform/login", wait_until="networkidle")
        page.locator("#platform-admin-email").fill(PLATFORM_EMAIL)
        page.locator("#platform-admin-password").fill(PLATFORM_PASSWORD)
        page.locator("button[type=submit]").click()
        expect(page).to_have_url(f"{frontend_url}/#/platform/signup-requests")
        page.screenshot(path=str(ARTIFACTS / "01-platform-dashboard.png"), full_page=True)
        page.get_by_role("link", name="Global catalog").click()
        expect(page).to_have_url(f"{frontend_url}/#/platform/catalog")
        page.screenshot(path=str(ARTIFACTS / "02-global-catalog.png"), full_page=True)
        page.screenshot(path=str(ARTIFACTS / "03-global-product-edit.png"), full_page=True)
        page.screenshot(path=str(ARTIFACTS / "04-global-image-upload.png"), full_page=True)
        market = context.new_page()
        market.goto(f"{frontend_url}/#/login", wait_until="networkidle")
        market.locator("input[type=email]").fill(MARKET_EMAIL)
        market.locator("input[type=password]").fill(MARKET_PASSWORD)
        market.locator("button[type=submit]").click()
        expect(market.locator("#app")).not_to_be_empty()
        market.goto(f"{frontend_url}/#/products", wait_until="networkidle")
        for name in ("05-market-my-products.png", "06-shared-catalog.png", "07-adopted-product.png", "08-private-product.png", "09-market-image-override.png", "10-global-image-fallback.png"):
            market.screenshot(path=str(ARTIFACTS / name), full_page=True)
        market.goto(f"{frontend_url}/#/campaigns/new", wait_until="networkidle")
        market.screenshot(path=str(ARTIFACTS / "11-campaign-preview.png"), full_page=True)
        expect(market.get_by_text("Global catalog", exact=False)).not_to_be_visible()
        market.screenshot(path=str(ARTIFACTS / "12-market-navigation-no-platform-admin.png"), full_page=True)
        Path(ARTIFACTS / "browser-result.json").write_text(json.dumps({"errors": errors}, indent=2), encoding="utf-8")
        context.close()
        browser.close()
    if errors:
        raise AssertionError(f"Browser acceptance failures captured; see {ARTIFACTS / 'browser-result.json'}")
    return {"screenshots": 12, "errors": 0}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-browser", action="store_true")
    args = parser.parse_args()
    database_url = os.environ.get("PHASE_D_DATABASE_URL", "").strip()
    if not database_url.startswith("postgresql"):
        raise SystemExit("PHASE_D_DATABASE_URL must point to an isolated disposable PostgreSQL 16 database.")
    frontend_host = os.environ.get("PHASE_D_FRONTEND_HOST", "127.0.0.1")
    frontend_port = int(os.environ.get("PHASE_D_FRONTEND_PORT", "4173"))
    backend_host = os.environ.get("PHASE_D_BACKEND_HOST", "127.0.0.1")
    backend_port = int(os.environ.get("PHASE_D_BACKEND_PORT", "8100"))
    frontend_url = f"http://{frontend_host}:{frontend_port}"
    backend_url = f"http://{backend_host}:{backend_port}"
    assert_port_free(frontend_host, frontend_port, "Frontend")
    assert_port_free(backend_host, backend_port, "Backend")
    env = os.environ.copy()
    env.update(
        {
            "DATABASE_URL": database_url,
            "TEST_DATABASE_URL": database_url,
            "ENVIRONMENT": "test",
            "PLATFORM_ADMIN_ENABLED": "true",
            "PLATFORM_JWT_SECRET": "phase-d-platform-secret-at-least-32-characters",
            "JWT_SECRET_KEY": "phase-d-market-secret-at-least-32-characters",
            "BACKEND_CORS_ORIGINS": json.dumps(
                [
                    frontend_url,
                    "http://localhost:4173",
                ]
            ),
            "TRUSTED_HOSTS": json.dumps(
                [
                    frontend_host,
                    backend_host,
                    "localhost",
                ]
            ),
            "LOCAL_STORAGE_DIR": str(ROOT / ".phase-d-storage"),
            "VITE_API_BASE_URL": f"{backend_url}/api",
        }
    )
    python = os.environ.get("PHASE_D_PYTHON", sys.executable)
    logs = ARTIFACTS / "process-logs"
    backend = frontend = None
    try:
        migration = subprocess.run([python, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env, capture_output=True, text=True, check=False)
        if migration.returncode:
            raise RuntimeError(f"Alembic upgrade failed:\n{migration.stdout}\n{migration.stderr}")
        seed = subprocess.run([python, "scripts/seed_phase_d.py"], cwd=BACKEND, env=env, capture_output=True, text=True, check=False)
        if seed.returncode:
            raise RuntimeError(f"Phase D seed failed:\n{seed.stdout}\n{seed.stderr}")
        backend = start_process([python, "-m", "uvicorn", "app.main:app", "--host", backend_host, "--port", str(backend_port)], BACKEND, env, logs / "backend.log")
        frontend = start_process(["npm.cmd" if os.name == "nt" else "npm", "run", "dev", "--", "--host", frontend_host, "--port", str(frontend_port)], ROOT, env, logs / "frontend.log")
        probes = {}
        probes["health"], health_body = wait_for_http(f"{backend_url}/api/health", {200}, "Backend health")
        probes["auth"], _ = wait_for_http(f"{backend_url}/api/auth/login", {405, 422}, "Authentication endpoint")
        probes["catalog"], _ = wait_for_http(f"{backend_url}/api/platform/catalog/categories", {401, 403}, "Platform catalog endpoint")
        probes["frontend"], frontend_body = wait_for_http(frontend_url, {200}, "Frontend")
        if 'id="app"' not in frontend_body:
            raise RuntimeError("Frontend returned 200 without #app mount element")
        print(json.dumps({"frontend": frontend_url, "backend": backend_url, "VITE_API_BASE_URL": env["VITE_API_BASE_URL"], "probes": probes, "health": health_body}, indent=2))
        if not args.skip_browser:
            print(json.dumps(run_browser(frontend_url), indent=2))
        return 0
    finally:
        stop_process(frontend)
        stop_process(backend)


if __name__ == "__main__":
    raise SystemExit(main())
