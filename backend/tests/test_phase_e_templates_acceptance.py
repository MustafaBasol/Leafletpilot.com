"""Phase E HTTP acceptance for isolated PostgreSQL and template storage."""

from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.security import create_access_token, create_platform_access_token, hash_password
from app.main import app
from app.models import Market, MarketUser, PlatformAdmin, Template, User


PNG = b"\x89PNG\r\n\x1a\nphase-e-thumbnail"


@pytest.mark.asyncio
async def test_when_test_database_url_is_configured_phase_e_template_and_thumbnail_acceptance():
    if AsyncSessionLocal is None:
        pytest.skip("TEST_DATABASE_URL is not configured.")
    prefix = f"phasee-{uuid4().hex[:10]}"
    async with AsyncSessionLocal() as session:
        admin = PlatformAdmin(email=f"{prefix}-admin@example.test", full_name="Phase E Admin", password_hash=hash_password("phase-e-password"))
        markets = [Market(name=f"{prefix}-{plan}", slug=f"{prefix}-{plan}", subscription_plan=plan) for plan in ("starter", "growth", "pro")]
        users = [User(email=f"{prefix}-{idx}@example.test", full_name=f"Phase E User {idx}", password_hash=hash_password("phase-e-password")) for idx in range(3)]
        session.add_all([admin, *markets, *users])
        await session.flush()
        session.add_all([MarketUser(market_id=market.id, user_id=user.id, role="market_admin") for market, user in zip(markets, users)])
        await session.commit()
        admin_token = create_platform_access_token(str(admin.id))
        market_tokens = [create_access_token(str(user.id)) for user in users]
        market_ids = [str(market.id) for market in markets]

    platform_headers = {"Authorization": f"Bearer {admin_token}"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        created = await client.post("/api/platform/templates", headers=platform_headers, json={"name": f"{prefix} Global", "template_type": "flyer", "config_json": {"layout": "premium-market", "slot_count": 4}})
        assert created.status_code == 201
        global_id = created.json()["id"]
        assert created.json()["status"] == "draft"
        assert (await client.get("/api/platform/templates", headers=platform_headers, params={"search": prefix})).json()["total"] == 1
        thumbnail = await client.post(f"/api/platform/templates/{global_id}/thumbnail", headers={**platform_headers, "Content-Type": "image/png"}, content=PNG)
        assert thumbnail.status_code == 200
        thumbnail_path = Path(settings.local_storage_path) / Path(thumbnail.json()["thumbnail_key"])
        assert thumbnail_path.is_file() and "global" in thumbnail.json()["thumbnail_key"]
        assert (await client.post(f"/api/platform/templates/{global_id}/thumbnail", headers={**platform_headers, "Content-Type": "image/gif"}, content=b"GIF89a")).status_code == 415
        assert (await client.post(f"/api/platform/templates/{global_id}/publish", headers=platform_headers)).status_code == 200
        assert (await client.post(f"/api/platform/templates/{global_id}/thumbnail", headers={**platform_headers, "Content-Type": "image/png"}, content=PNG)).status_code == 403
        duplicate = await client.post(f"/api/platform/templates/{global_id}/duplicate", headers=platform_headers)
        assert duplicate.status_code == 201
        v2_id = duplicate.json()["id"]
        assert duplicate.json()["version"] == 2
        assert (await client.post(f"/api/platform/templates/{v2_id}/publish", headers=platform_headers)).status_code == 200

        growth_headers = {"Authorization": f"Bearer {market_tokens[1]}", "X-Market-Id": market_ids[1]}
        starter_headers = {"Authorization": f"Bearer {market_tokens[0]}", "X-Market-Id": market_ids[0]}
        pro_headers = {"Authorization": f"Bearer {market_tokens[2]}", "X-Market-Id": market_ids[2]}
        assert (await client.get("/api/templates/shared", headers=starter_headers)).status_code == 200
        adopted = await client.post(f"/api/templates/shared/{global_id}/adopt", headers=growth_headers)
        assert adopted.status_code == 201
        adopted_body = adopted.json()
        assert adopted_body["source_template_id"] == global_id and adopted_body["source_version"] == 1
        assert "markets" in adopted_body["thumbnail_key"]
        assert (await client.post(f"/api/templates/shared/{global_id}/adopt", headers=growth_headers)).status_code == 409
        assert (await client.patch(f"/api/templates/{global_id}", headers=growth_headers, json={"name": "forbidden"})).status_code == 403
        assert (await client.get(f"/api/templates/{adopted_body['id']}", headers=pro_headers)).status_code == 404
        assert (await client.post("/api/templates/custom", headers=starter_headers, json={"name": "blocked", "template_type": "flyer"})).status_code == 403
        custom = await client.post("/api/templates/custom", headers=pro_headers, json={"name": f"{prefix} Custom", "template_type": "flyer"})
        assert custom.status_code == 201
        custom_id = custom.json()["id"]
        own_thumbnail = await client.post(f"/api/templates/{custom_id}/thumbnail", headers={**pro_headers, "Content-Type": "image/png"}, content=PNG)
        assert own_thumbnail.status_code == 200 and f"markets/{market_ids[2]}" in own_thumbnail.json()["thumbnail_key"]
        assert (await client.get(f"/api/templates/{custom_id}/thumbnail", headers=growth_headers)).status_code == 404
        assert (await client.delete(f"/api/templates/{custom_id}/thumbnail", headers=pro_headers)).status_code == 204
        assert (await client.get(f"/api/templates/{custom_id}/thumbnail", headers=pro_headers)).status_code == 404
        assert (await client.get(f"/api/templates/{global_id}/preview-html", headers=growth_headers)).status_code == 200

