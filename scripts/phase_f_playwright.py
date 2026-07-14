"""Phase F browser acceptance for a disposable local PostgreSQL environment."""

from __future__ import annotations

import json
import asyncio
import os
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
ARTIFACTS = Path(os.environ.get("PHASE_F_ARTIFACTS", ROOT / "artifacts" / "phase-f-browser-acceptance"))
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


async def mutate_phase_f_sources(database_url: str) -> None:
    sys.path.insert(0, str(BACKEND))
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from app.models import MarketProduct, Product, Template

    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
        async with session_factory() as session:
            product = await session.scalar(select(Product).where(Product.barcode == "PHASE-F-001"))
            market_product = await session.scalar(select(MarketProduct).where(MarketProduct.product_id == product.id))
            template = await session.scalar(select(Template).where(Template.slug == "phase-f-global-v2"))
            product.name = "Phase F MUTATED Product"
            product.regular_price = 99
            product.promo_price = 88
            market_product.display_name_override = "Phase F MUTATED Display"
            market_product.category_override_id = None
            market_product.image_url = "https://example.com/mutated-image.png"
            market_product.regular_price = 77
            market_product.promo_price = 66
            template.config_json = {**(template.config_json or {}), "accent_color": "#dc2626", "footer_note": "MUTATED TEMPLATE V2"}
            await session.commit()
    finally:
        await engine.dispose()


async def fill_starter_export_quota(database_url: str, campaign_id: str, market_id: str) -> None:
    sys.path.insert(0, str(BACKEND))
    from datetime import UTC, datetime
    from uuid import UUID
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from app.models import ExportJob

    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
        async with session_factory() as session:
            now = datetime.now(UTC)
            session.add_all([
                ExportJob(campaign_id=UUID(campaign_id), market_id=UUID(market_id), job_type="final_export", status="completed", requested_formats=["pdf"], completed_at=now)
                for _ in range(10)
            ])
            await session.commit()
    finally:
        await engine.dispose()


def run_async_outside_playwright(coro_factory, *args) -> None:
    """Run an async database assertion/mutation without colliding with sync Playwright's loop."""
    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(asyncio.run, coro_factory(*args)).result()


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
    frontend = subprocess.Popen(["npm.cmd", "run", "dev", "--", "--configLoader", "runner", "--host", "127.0.0.1", "--port", str(frontend_port), "--strictPort"], cwd=ROOT, env=env, stdout=frontend_log, stderr=subprocess.STDOUT)
    console_errors: list[str] = []
    expected_policy_console_errors: list[str] = []
    page_errors: list[str] = []
    failed_critical_requests: list[str] = []
    result = {"frontend_probe": {}, "backend_probe": {}, "auth_probe": {}, "builder_options_anonymous_probe": {}, "auth_preflight": {}, "builder_options_preflight": {}, "seed_summary": seed_stdout.strip(), "seed_stderr": seed_stderr.strip(), "screenshots": [], "console_errors": console_errors, "expected_policy_console_errors": expected_policy_console_errors, "page_errors": page_errors, "failed_critical_requests": failed_critical_requests}
    try:
        result["backend_probe"] = wait_for(f"{backend_url}/api/health")
        result["frontend_probe"] = wait_for(frontend_url)
        result["auth_probe"] = wait_for(f"{backend_url}/api/auth/me", {401, 403})
        result["builder_options_anonymous_probe"] = wait_for(f"{backend_url}/api/campaigns/builder/options", {401, 403})
        result["auth_preflight"] = phase_f_preflight(backend_url)
        result["builder_options_preflight"] = {"status": result["auth_preflight"]["builder_options_status"], **result["auth_preflight"]["builder_options"]}
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--disable-gpu", "--disable-dev-shm-usage"])
            context = browser.new_context(base_url=frontend_url)
            page = context.new_page()
            expected_policy_messages = {"Failed to load resource: the server responded with a status of 403 (Forbidden)", "Failed to load resource: the server responded with a status of 404 (Not Found)"}
            page.on("console", lambda message: (expected_policy_console_errors if message.text in expected_policy_messages else console_errors).append(message.text) if message.type == "error" else None)
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            page.on("requestfailed", lambda request: failed_critical_requests.append(f"{request.method} {request.url}: {request.failure}") if ("/api/" in request.url or request.resource_type in {"document", "script"}) else None)

            def page_api(path, method="GET", body=None, market_id=None):
                return page.evaluate(
                    """async ({baseUrl, path, method, body, marketId}) => {
                      const token = localStorage.getItem('leafletpilot_access_token');
                      const response = await fetch(`${baseUrl}${path}`, {method, headers: {'Content-Type': 'application/json', 'Authorization': `Bearer ${token}`, 'X-Market-Id': marketId}, body: body ? JSON.stringify(body) : undefined});
                      const text = await response.text();
                      let parsed; try { parsed = text ? JSON.parse(text) : {}; } catch { parsed = {raw: text}; }
                      return {status: response.status, body: parsed};
                    }""",
                    {"baseUrl": backend_url + "/api", "path": path, "method": method, "body": body, "marketId": market_id or result["auth_preflight"]["market_id"]},
                )

            page.goto(f"{frontend_url}/#/login", wait_until="domcontentloaded")
            page.locator("input[type=email]").fill("phase-f-user-a@example.test")
            page.locator("input[type=password]").fill(PASSWORD)
            page.locator("button[type=submit]").click()
            expect(page).to_have_url(f"{frontend_url}/#/dashboard")
            markets = page.evaluate("JSON.parse(localStorage.getItem('leafletpilot_markets') || '[]')")
            growth = next((market["id"] for market in markets if "Growth" in market.get("name", "")), None)
            if growth:
                page.evaluate("(id) => localStorage.setItem('leafletpilot_selected_market_id', id)", growth)
            market_id = result["auth_preflight"]["market_id"]
            stored_markets = page.evaluate("JSON.parse(localStorage.getItem('leafletpilot_markets') || '[]')")
            starter = next(market for market in stored_markets if "Starter" in market.get("name", ""))
            options_for_assertions = page_api("/campaigns/builder/options", market_id=market_id)
            global_v1 = next(template for template in options_for_assertions["body"]["templates"] if template["slug"] == "phase-f-global-v1")
            campaigns_response = page_api("/campaigns", market_id=market_id)
            assert campaigns_response["status"] == 200
            draft = next(item for item in campaigns_response["body"]["items"] if item["title"] == "Phase F Draft Campaign")
            frozen = next(item for item in campaigns_response["body"]["items"] if item["title"] == "Phase F Finalized Campaign")
            historical = next(item for item in campaigns_response["body"]["items"] if item["title"] == "Phase F Historical v1 Campaign")

            page.goto(f"{frontend_url}/#/campaigns", wait_until="domcontentloaded")
            expect(page.get_by_text("Phase F Draft Campaign")).to_be_visible()
            page.screenshot(path=str(ARTIFACTS / SCREENSHOTS[0]), full_page=True)
            page.get_by_text("Phase F Draft Campaign").click()
            page.wait_for_load_state("networkidle")
            page.screenshot(path=str(ARTIFACTS / SCREENSHOTS[1]), full_page=True)

            page.goto(f"{frontend_url}/#/campaigns/new", wait_until="domcontentloaded")
            page.screenshot(path=str(ARTIFACTS / SCREENSHOTS[2]), full_page=True)
            page.get_by_role("button", name="İleri").click()
            expect(page.get_by_text("Phase F Adopted Product")).to_be_visible()
            page.screenshot(path=str(ARTIFACTS / SCREENSHOTS[4]), full_page=True)
            page.get_by_role("button", name="İleri").click()
            page.get_by_role("button", name="İleri").click()
            page.get_by_role("button", name="Phase F Custom Template").click()
            page.screenshot(path=str(ARTIFACTS / SCREENSHOTS[3]), full_page=True)
            page.get_by_role("button", name="İleri").click()
            page.get_by_role("button", name="Geri").click()
            page.get_by_role("button", name="Geri").click()
            page.get_by_role("button", name="Geri").click()
            expect(page.get_by_test_id("slot-validation")).to_be_visible()
            page.screenshot(path=str(ARTIFACTS / SCREENSHOTS[6]), full_page=True)
            checked_products = page.locator('input[type="checkbox"]:checked')
            while checked_products.count() > 2:
                checked_products.nth(2).uncheck()
            expect(page.get_by_test_id("slot-validation")).not_to_be_visible()
            page.get_by_role("button", name="İleri").click()
            page.get_by_role("button", name="İleri").click()
            page.get_by_role("button", name="İleri").click()
            page.get_by_role("textbox", name="Başlık", exact=True).fill("Phase F Frozen Headline")
            page.get_by_role("textbox", name="Alt başlık", exact=True).fill("Phase F Frozen Subtitle")
            page.get_by_role("textbox", name="Alt bilgi", exact=True).fill("Phase F Frozen Footer")
            page.screenshot(path=str(ARTIFACTS / SCREENSHOTS[7]), full_page=True)
            page.get_by_role("button", name="Geri").click()
            page.get_by_role("button", name="Geri").click()
            page.get_by_role("button", name="Geri").click()

            page.goto(f"{frontend_url}/#/campaigns/{draft['id']}", wait_until="domcontentloaded")
            rows = page.locator("table tbody tr")
            expect(rows).to_have_count(3)
            original_order = [row.locator("td").nth(1).inner_text().splitlines()[0] for row in rows.all()]
            rows.nth(0).get_by_role("button", name="↓").click()
            expect(page.get_by_text("Ürün sırası kaydedildi.")).to_be_visible()
            reordered = [row.locator("td").nth(1).inner_text().splitlines()[0] for row in page.locator("table tbody tr").all()]
            assert reordered == [original_order[1], original_order[0], original_order[2]]
            detail = page_api(f"/campaigns/{draft['id']}", market_id=market_id)
            assert detail["status"] == 200
            assert [item["sort_order"] for item in detail["body"]["items"]] == [0, 1, 2]
            assert [item["incoming_name"] for item in sorted(detail["body"]["items"], key=lambda item: item["sort_order"])] == reordered
            page.screenshot(path=str(ARTIFACTS / SCREENSHOTS[5]), full_page=True)
            page.goto(f"{frontend_url}/#/campaigns", wait_until="domcontentloaded")
            page.locator(f'a[href="#/campaigns/{draft["id"]}"]').click()
            expect(page.locator("table tbody tr").nth(0).locator("td").nth(1)).to_contain_text(reordered[0])
            page.screenshot(path=str(ARTIFACTS / SCREENSHOTS[9]), full_page=True)

            page.get_by_role("button", name="Kampanyayı Dondur").click()
            expect(page.get_by_text("Kampanya donduruldu ve sürümü sabitlendi.")).to_be_visible()
            frozen_detail = page_api(f"/campaigns/{draft['id']}", market_id=market_id)
            assert frozen_detail["body"]["snapshot_json"]
            snapshot = frozen_detail["body"]["snapshot_json"]
            expect(page.get_by_role("button", name="Kampanyayı Dondur")).not_to_be_visible()
            page.screenshot(path=str(ARTIFACTS / SCREENSHOTS[10]), full_page=True)

            run_async_outside_playwright(mutate_phase_f_sources, database_url)
            page.reload(wait_until="domcontentloaded")
            after_mutation = page_api(f"/campaigns/{draft['id']}", market_id=market_id)
            assert after_mutation["body"]["snapshot_json"] == snapshot
            preview_response = page_api(f"/campaigns/{draft['id']}/preview-html", market_id=market_id)
            assert preview_response["status"] == 200
            assert "MUTATED" not in preview_response["body"]["html"]
            page.screenshot(path=str(ARTIFACTS / SCREENSHOTS[8]), full_page=True)

            page.get_by_role("button", name="PDF Üret").click()
            expect(page.get_by_text("PDF dosyası üretildi.")).to_be_visible(timeout=30000)
            page.screenshot(path=str(ARTIFACTS / SCREENSHOTS[11]), full_page=True)
            pdf_job = page_api(f"/campaigns/{draft['id']}/export-jobs", "GET", market_id=market_id)
            assert pdf_job["status"] == 200
            pdf_repeat = page_api(f"/campaigns/{draft['id']}/export-jobs", "POST", {"job_type": "final_export", "requested_formats": ["pdf"]}, market_id)
            assert pdf_repeat["status"] == 201 and pdf_repeat["body"]["id"] == pdf_job["body"][-1]["id"]
            expect(page.get_by_role("button", name="PDF Üret")).to_be_enabled(timeout=30000)
            page.get_by_role("button", name="PNG Üret").click()
            expect(page.get_by_text("PNG dosyası üretildi.")).to_be_visible(timeout=30000)
            page.screenshot(path=str(ARTIFACTS / SCREENSHOTS[12]), full_page=True)
            png_repeat = page_api(f"/campaigns/{draft['id']}/export-jobs", "POST", {"job_type": "final_export", "requested_formats": ["png"]}, market_id)
            assert png_repeat["status"] == 201
            preview_after_export = page_api(f"/campaigns/{draft['id']}/preview-html", market_id=market_id)
            frozen_payload = after_mutation["body"]["snapshot_json"]
            for item in frozen_payload["items"]:
                assert item["name"] in preview_after_export["body"]["html"]
            files_after_export = page_api(f"/campaigns/{draft['id']}/files", market_id=market_id)
            formats = {file["format"] for file in files_after_export["body"]}
            assert {"pdf", "png"}.issubset(formats)

            page.goto(f"{frontend_url}/#/campaigns/{historical['id']}", wait_until="domcontentloaded")
            expect(page.get_by_text("Phase F Global v1", exact=True)).to_be_visible()
            historical_detail = page_api(f"/campaigns/{historical['id']}", market_id=market_id)
            assert historical_detail["body"]["snapshot_json"]["template_version"] == 1
            page.screenshot(path=str(ARTIFACTS / SCREENSHOTS[13]), full_page=True)

            starter_campaign = page_api("/campaigns", "POST", {"title": "Phase F Starter Entitlement Campaign", "template_id": str(global_v1["id"]), "items": [{"raw_line": "Starter Product", "incoming_name": "Starter Product", "price": "1.00", "old_price": "2.00"}]}, starter["id"])
            assert starter_campaign["status"] == 201
            run_async_outside_playwright(fill_starter_export_quota, database_url, starter_campaign["body"]["id"], starter["id"])
            page.evaluate("(id) => localStorage.setItem('leafletpilot_selected_market_id', id)", starter["id"])
            page.goto(f"{frontend_url}/#/campaigns/{starter_campaign['body']['id']}", wait_until="domcontentloaded")
            page.get_by_role("button", name="Dosya Üret").last.click()
            denied_export = page_api(f"/campaigns/{starter_campaign['body']['id']}/export-jobs", "POST", {"job_type": "final_export", "requested_formats": ["png"]}, starter["id"])
            assert denied_export["status"] == 403
            expect(page.get_by_text("Bu işlem için yetkiniz bulunmuyor.")).to_be_visible(timeout=10000)
            page.screenshot(path=str(ARTIFACTS / SCREENSHOTS[14]), full_page=True)
            forbidden = page_api(f"/campaigns/{draft['id']}", market_id=starter["id"])
            assert forbidden["status"] == 404
            page.screenshot(path=str(ARTIFACTS / SCREENSHOTS[15]), full_page=True)
            page.screenshot(path=str(ARTIFACTS / SCREENSHOTS[15]), full_page=True)
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
