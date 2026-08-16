"""Phase 29A acceptance tests: public plans, campaign quota, admin plan management."""

from uuid import uuid4

import httpx
import pytest
from app.core.database import AsyncSessionLocal
from app.core.security import create_access_token, create_platform_access_token, hash_password
from app.main import app
from app.models import Market, MarketUser, PlatformAdmin, User
from app.schemas.platform import ProvisionMarketRequest


def test_provision_request_accepts_canonical_and_legacy_plan_codes_and_rejects_unknown() -> None:
    base = {"final_market_name": "Test Market", "country_code": "FR"}
    for code in ("starter", "standard", "growth", "pro"):
        request = ProvisionMarketRequest(**base, subscription_plan=code)
        assert request.subscription_plan == code
    with pytest.raises(Exception):
        ProvisionMarketRequest(**base, subscription_plan="enterprise")


def test_provision_request_defaults_to_starter_plan() -> None:
    request = ProvisionMarketRequest(final_market_name="Test Market", country_code="FR")
    assert request.subscription_plan == "starter"


@pytest.mark.asyncio
async def test_public_plans_endpoint_returns_three_plans_with_standard_recommended():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/api/public/plans")
        assert response.status_code == 200
        body = response.json()
        assert [item["code"] for item in body] == ["starter", "standard", "pro"]
        assert [item["monthly_price"] for item in body] == [59, 119, 199]
        assert [item["is_recommended"] for item in body] == [False, True, False]
        # Internal-only fields must not leak to the public contract.
        assert "monthly_exports_limit" not in body[0]
        assert "global_catalog_access" not in body[0]


@pytest.mark.asyncio
async def test_when_test_database_url_is_configured_phase_29a_plan_acceptance():
    if AsyncSessionLocal is None:
        pytest.skip("TEST_DATABASE_URL is not configured.")
    prefix = f"phase29a-{uuid4().hex[:10]}"
    async with AsyncSessionLocal() as session:
        admin = PlatformAdmin(email=f"{prefix}-admin@example.test", full_name="Phase 29A Admin", password_hash=hash_password("phase-29a-password"))
        starter_market = Market(name=f"{prefix}-starter", slug=f"{prefix}-starter", subscription_plan="starter")
        pro_market = Market(name=f"{prefix}-pro", slug=f"{prefix}-pro", subscription_plan="pro")
        user_starter = User(email=f"{prefix}-starter@example.test", full_name="Starter Owner", password_hash=hash_password("phase-29a-password"))
        user_pro = User(email=f"{prefix}-pro@example.test", full_name="Pro Owner", password_hash=hash_password("phase-29a-password"))
        session.add_all([admin, starter_market, pro_market, user_starter, user_pro])
        await session.flush()
        session.add_all([
            MarketUser(market_id=starter_market.id, user_id=user_starter.id, role="market_admin"),
            MarketUser(market_id=pro_market.id, user_id=user_pro.id, role="market_admin"),
        ])
        await session.commit()
        admin_token = create_platform_access_token(str(admin.id))
        starter_token = create_access_token(str(user_starter.id))
        pro_token = create_access_token(str(user_pro.id))
        starter_market_id = str(starter_market.id)
        pro_market_id = str(pro_market.id)

    platform_headers = {"Authorization": f"Bearer {admin_token}"}
    starter_headers = {"Authorization": f"Bearer {starter_token}", "X-Market-Id": starter_market_id}
    pro_headers = {"Authorization": f"Bearer {pro_token}", "X-Market-Id": pro_market_id}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        # --- Campaign quota: starter allows exactly 4/month, 5th is blocked ---
        for _ in range(4):
            created = await client.post("/api/campaigns", headers=starter_headers, json={"title": "Kampanya"})
            assert created.status_code == 201
        blocked = await client.post("/api/campaigns", headers=starter_headers, json={"title": "Kampanya 5"})
        assert blocked.status_code == 403

        # --- Pro plan is unlimited: keep creating past the starter cap ---
        for index in range(5):
            created = await client.post("/api/campaigns", headers=pro_headers, json={"title": f"Pro kampanya {index}"})
            assert created.status_code == 201

        # --- Market-scoped: pro market's usage never touched the starter market's quota ---
        my_plan = await client.get("/api/market/plan", headers=starter_headers)
        assert my_plan.status_code == 200
        assert my_plan.json()["code"] == "starter"
        assert my_plan.json()["monthly_campaigns_used"] == 4
        assert my_plan.json()["monthly_campaigns_limit"] == 4

        pro_plan = await client.get("/api/market/plan", headers=pro_headers)
        assert pro_plan.json()["monthly_campaigns_limit"] is None
        assert pro_plan.json()["monthly_campaigns_used"] == 5

        # --- Export formats: only real render formats (pdf/png) are ever accepted ---
        # Uses the (unlimited) pro market so this doesn't consume the starter
        # market's already-exhausted campaign quota above.
        format_campaign = await client.post(
            "/api/campaigns",
            headers=pro_headers,
            json={"title": "Format testi"},
        )
        assert format_campaign.status_code == 201
        campaign_id = format_campaign.json()["id"]
        bad_export = await client.post(
            f"/api/campaigns/{campaign_id}/export-jobs",
            headers=pro_headers,
            json={"requested_formats": ["instagram"]},
        )
        assert bad_export.status_code == 422

        # --- Platform admin plan management ---
        detail_before = await client.get(f"/api/platform/markets/{starter_market_id}", headers=platform_headers)
        assert detail_before.status_code == 200
        assert detail_before.json()["subscription_plan"] == "starter"
        assert detail_before.json()["plan_quota"]["monthly_campaigns_limit"] == 4

        changed = await client.patch(
            f"/api/platform/markets/{starter_market_id}/plan",
            headers=platform_headers,
            json={"subscription_plan": "standard", "reason": "Upsell"},
        )
        assert changed.status_code == 200
        assert changed.json()["subscription_plan"] == "standard"
        assert changed.json()["plan_quota"]["monthly_campaigns_limit"] == 10
        # Historical usage is not reset/altered by a plan change.
        assert changed.json()["plan_quota"]["monthly_campaigns_used"] == 4

        legacy_growth = await client.patch(
            f"/api/platform/markets/{starter_market_id}/plan",
            headers=platform_headers,
            json={"subscription_plan": "growth"},
        )
        assert legacy_growth.status_code == 200
        assert legacy_growth.json()["subscription_plan"] == "growth"
        assert legacy_growth.json()["subscription_plan_display"] == "Plus"

        invalid_plan = await client.patch(
            f"/api/platform/markets/{starter_market_id}/plan",
            headers=platform_headers,
            json={"subscription_plan": "enterprise"},
        )
        assert invalid_plan.status_code == 422

        forbidden = await client.patch(
            f"/api/platform/markets/{starter_market_id}/plan",
            headers=starter_headers,
            json={"subscription_plan": "pro"},
        )
        assert forbidden.status_code == 401

        audit = await client.get("/api/platform/audit", headers=platform_headers, params={"target_type": "market"})
        assert audit.status_code == 200
        actions = [item["action"] for item in audit.json()["items"]]
        assert "market_plan_changed" in actions
