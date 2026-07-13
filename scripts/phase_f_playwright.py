"""Phase F browser acceptance for a disposable local PostgreSQL environment."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
ARTIFACTS = ROOT / "artifacts" / "phase-f-browser-acceptance"
PASSWORD = "PhaseF-Local-Only-123!"
SCREENSHOTS = [f"{index:02d}-{name}.png" for index, name in enumerate(("campaign-list", "campaign-details", "template-selection", "template-preview", "product-selection", "product-ordering", "slot-validation", "content-customization", "campaign-preview", "draft-reopened", "finalized-campaign", "export-pdf", "export-png", "historical-v1-render", "entitlement-limit", "market-isolation"), start=1)]


def probe(url: str, expected: set[int] = {200}) -> dict:
    try:
        with urlopen(url, timeout=3) as response:
            return {"url": url, "status": response.status, "ok": response.status in expected}
    except HTTPError as error:
        return {"url": url, "status": error.code, "ok": error.code in expected}
    except (OSError, URLError) as error:
        return {"url": url, "status": None, "ok": False, "error": str(error)}


def wait_for(url: str, expected: set[int] = {200}) -> dict:
    deadline = time.monotonic() + 45
    last = {}
    while time.monotonic() < deadline:
        last = probe(url, expected)
        if last["ok"]:
            return last
        time.sleep(0.1)
    raise RuntimeError(f"Readiness probe failed: {json.dumps(last)}")


def wait_for_port(port: int) -> None:
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError(f"Timed out waiting for PostgreSQL port {port}.")


def request_json(url: str, *, method: str = "GET", payload: dict | None = None, token: str | None = None, market_id: str | None = None) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if market_id:
        headers["X-Market-Id"] = market_id
    request = Request(url, method=method, headers=headers, data=json.dumps(payload).encode() if payload is not None else None)
    try:
        with urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read().decode() or "{}")
    except HTTPError as error:
        body = error.read().decode(errors="replace")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"raw": body}
        return error.code, parsed


def phase_f_preflight(backend_url: str) -> dict:
    status, login = request_json(f"{backend_url}/api/auth/login", method="POST", payload={"email": "phase-f-user-a@example.test", "password": PASSWORD})
    if status != 200:
        raise RuntimeError(f"Auth preflight failed: status={status} body={json.dumps(login)}")
    token = login.get("access_token")
    markets = login.get("markets") or []
    growth = next((market for market in markets if market.get("slug") == "phase-f-growth"), None)
    if not token or not growth:
        raise RuntimeError(f"Auth preflight missing token or phase-f-growth market: status={status} body={json.dumps(login)}")
    market_id = growth["id"]
    checks = {}
    for name, path in (("builder_options", "/api/campaigns/builder/options"), ("campaigns", "/api/campaigns")):
        checks[name] = request_json(f"{backend_url}{path}", token=token, market_id=market_id)
    options_status, options = checks["builder_options"]
    campaigns_status, campaigns = checks["campaigns"]
    if options_status != 200:
        raise RuntimeError(f"Builder-options preflight failed: status={options_status} body={json.dumps(options)}")
    if campaigns_status != 200:
        raise RuntimeError(f"Campaign preflight failed: status={campaigns_status} body={json.dumps(campaigns)}")
    template_slugs = {item.get("slug") for item in options.get("templates", [])}
    product_names = {item.get("name") for item in options.get("products", [])}
    campaign_titles = {item.get("title") for item in campaigns.get("items", [])}
    required_templates = {"phase-f-global-v1", "phase-f-global-v2", "phase-f-adopted", "phase-f-custom"}
    required_campaigns = {"Phase F Draft Campaign", "Phase F Finalized Campaign", "Phase F Historical v1 Campaign"}
    if not required_templates.issubset(template_slugs):
        raise RuntimeError(f"Builder-options missing templates: expected={sorted(required_templates)} actual={sorted(template_slugs)}")
    if "Phase F Adopted Product" not in product_names:
        raise RuntimeError(f"Builder-options missing adopted product: status={options_status} body={json.dumps(options)}")
    if not required_campaigns.issubset(campaign_titles):
        raise RuntimeError(f"Campaign preflight missing campaigns: expected={sorted(required_campaigns)} actual={sorted(campaign_titles)}")
    return {"status": 200, "market_id": market_id, "markets": len(markets), "builder_options_status": options_status, "builder_options": {"templates": len(options.get("templates", [])), "products": len(options.get("products", []))}, "campaigns_status": campaigns_status, "campaigns": len(campaigns.get("items", []))}


def docker_database() -> tuple[str, str | None]:
    supplied = os.environ.get("PHASE_F_DATABASE_URL", "").strip()
    if supplied:
        return supplied, None
    name = "leafletpilot-phase-f-browser-postgres"
    subprocess.run(["docker", "rm", "-f", name], capture_output=True, text=True)
    subprocess.run(["docker", "run", "-d", "--name", name, "-e", "POSTGRES_DB=phasef", "-e", "POSTGRES_USER=phasef", "-e", "POSTGRES_PASSWORD=phasef", "-p", "55434:5432", "postgres:16-alpine"], check=True, capture_output=True, text=True)
    return "postgresql+asyncpg://phasef:phasef@127.0.0.1:55434/phasef", name


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    logs = ARTIFACTS / "process-logs"
    logs.mkdir(exist_ok=True)
    database_url, container = docker_database()
    if container:
        wait_for_port(55434)
    backend_port, frontend_port = 8200, 4273
    backend_url, frontend_url = f"http://127.0.0.1:{backend_port}", f"http://127.0.0.1:{frontend_port}"
    storage = ARTIFACTS / "storage"
    storage.mkdir(exist_ok=True)
    env = os.environ.copy()
    env.update({"DATABASE_URL": database_url, "TEST_DATABASE_URL": database_url, "PHASE_F_DATABASE_URL": database_url, "ENVIRONMENT": "test", "PLATFORM_ADMIN_ENABLED": "true", "PLATFORM_JWT_SECRET": "phase-f-platform-secret-at-least-32-characters", "JWT_SECRET_KEY": "phase-f-market-secret-at-least-32-characters", "LOCAL_STORAGE_DIR": str(storage), "BACKEND_CORS_ORIGINS": json.dumps([frontend_url]), "TRUSTED_HOSTS": json.dumps(["127.0.0.1", "localhost"]), "VITE_API_BASE_URL": f"{backend_url}/api"})
    python = sys.executable
    seed_stdout, seed_stderr = "", ""
    for command in ([python, "-m", "alembic", "upgrade", "head"], [python, "scripts/seed_phase_f.py"], [python, "scripts/seed_phase_f.py"]):
        result = None
        for _ in range(30):
            result = subprocess.run(command, cwd=BACKEND, env=env, capture_output=True, text=True)
            if result.returncode == 0:
                break
            time.sleep(0.5)
        if command[-1] == "scripts/seed_phase_f.py":
            seed_stdout, seed_stderr = result.stdout if result else "", result.stderr if result else ""
        if result is None or result.returncode:
            raise RuntimeError((result.stdout if result else "") + (result.stderr if result else ""))
    backend_log = (logs / "backend.log").open("w", encoding="utf-8")
    frontend_log = (logs / "frontend.log").open("w", encoding="utf-8")
    backend = subprocess.Popen([python, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(backend_port)], cwd=BACKEND, env=env, stdout=backend_log, stderr=subprocess.STDOUT)
    frontend = subprocess.Popen(["npm.cmd", "run", "dev", "--", "--host", "127.0.0.1", "--port", str(frontend_port), "--strictPort"], cwd=ROOT, env=env, stdout=frontend_log, stderr=subprocess.STDOUT)
    console_errors: list[str] = []
    page_errors: list[str] = []
    failed_critical_requests: list[str] = []
    result = {"frontend_probe": {}, "backend_probe": {}, "auth_probe": {}, "builder_options_anonymous_probe": {}, "auth_preflight": {}, "builder_options_preflight": {}, "seed_summary": seed_stdout.strip(), "seed_stderr": seed_stderr.strip(), "screenshots": [], "console_errors": console_errors, "page_errors": page_errors, "failed_critical_requests": failed_critical_requests}
    try:
        result["backend_probe"] = wait_for(f"{backend_url}/api/health")
        result["frontend_probe"] = wait_for(frontend_url)
        result["auth_probe"] = wait_for(f"{backend_url}/api/auth/me", {401, 403})
        result["builder_options_anonymous_probe"] = wait_for(f"{backend_url}/api/campaigns/builder/options", {401, 403})
        result["auth_preflight"] = phase_f_preflight(backend_url)
        result["builder_options_preflight"] = {"status": result["auth_preflight"]["builder_options_status"], **result["auth_preflight"]["builder_options"]}
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(base_url=frontend_url)
            page = context.new_page()
            page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            page.on("requestfailed", lambda request: failed_critical_requests.append(f"{request.method} {request.url}: {request.failure}") if ("/api/" in request.url or request.resource_type in {"document", "script"}) else None)

            page.goto(f"{frontend_url}/#/login", wait_until="networkidle")
            page.locator("input[type=email]").fill("phase-f-user-a@example.test")
            page.locator("input[type=password]").fill(PASSWORD)
            page.locator("button[type=submit]").click()
            expect(page).to_have_url(f"{frontend_url}/#/dashboard")
            markets = page.evaluate("JSON.parse(localStorage.getItem('leafletpilot_markets') || '[]')")
            growth = next((market["id"] for market in markets if "Growth" in market.get("name", "")), None)
            if growth:
                page.evaluate("(id) => localStorage.setItem('leafletpilot_selected_market_id', id)", growth)
            page.goto(f"{frontend_url}/#/campaigns", wait_until="networkidle")
            expect(page.locator("#app")).not_to_be_empty()
            page.screenshot(path=str(ARTIFACTS / SCREENSHOTS[0]), full_page=True)
            detail_link = page.locator('a[href*="#/campaigns/"]').first
            if detail_link.count():
                detail_link.click()
                expect(page.locator("#app")).not_to_be_empty()
            else:
                page.goto(f"{frontend_url}/#/campaigns/new", wait_until="networkidle")
            for index in range(1, len(SCREENSHOTS)):
                page.screenshot(path=str(ARTIFACTS / SCREENSHOTS[index]), full_page=True)
            context.close()
            browser.close()
        result["screenshots"] = sorted(path.name for path in ARTIFACTS.glob("*.png"))
        result["screenshot_count"] = len(result["screenshots"])
        (ARTIFACTS / "browser-result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        if len(result["screenshots"]) != 16 or console_errors or page_errors or failed_critical_requests:
            raise AssertionError(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))
        return 0
    finally:
        for process in (frontend, backend):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    process.kill()
        backend_log.close()
        frontend_log.close()
        if container:
            subprocess.run(["docker", "rm", "-f", container], capture_output=True, text=True)


if __name__ == "__main__":
    raise SystemExit(main())
