"""Phase 30A: production authentication and exposure hardening.

Covers the route surfaces not already exercised elsewhere: platform admin
route boundaries, market-token/platform-token confusion, CORS and trusted
host behavior, security response headers, anonymous access to
auth-gated/expensive endpoints, and cross-market tenant isolation beyond the
brands coverage already in test_auth_api.py.

DB-backed scenarios follow the project convention of naming the test
`..._when_test_database_url_is_configured` so conftest.py auto-skips them
when TEST_DATABASE_URL is not reachable.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models
from app.api.deps import get_catalog_session
from app.core.config import settings
from app.core.database import Base
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models import Market, MarketUser, User

client = TestClient(app)


# ---------------------------------------------------------------------------
# Platform admin route boundary (section C / N4): every admin route must
# reject anonymous callers, and must not accept a regular market-user token.
# ---------------------------------------------------------------------------

PLATFORM_ADMIN_ROUTES = [
    ("get", "/api/platform/auth/me"),
    ("get", "/api/platform/overview"),
    ("get", "/api/platform/audit"),
    ("get", "/api/platform/signup-requests"),
    ("get", "/api/platform/signup-requests/00000000-0000-0000-0000-000000000001"),
    ("patch", "/api/platform/signup-requests/00000000-0000-0000-0000-000000000001"),
    ("post", "/api/platform/signup-requests/00000000-0000-0000-0000-000000000001/provision"),
    ("get", "/api/platform/markets"),
    ("get", "/api/platform/markets/00000000-0000-0000-0000-000000000001"),
    ("patch", "/api/platform/markets/00000000-0000-0000-0000-000000000001/lifecycle"),
    ("post", "/api/platform/markets/00000000-0000-0000-0000-000000000001/owner-invitation"),
    ("post", "/api/platform/markets/00000000-0000-0000-0000-000000000001/owner-invitation/rotate"),
    ("post", "/api/platform/markets/00000000-0000-0000-0000-000000000001/owner-invitation/revoke"),
    ("post", "/api/platform/markets/00000000-0000-0000-0000-000000000001/owner-invitation/manual-link"),
    ("get", "/api/platform/templates"),
    ("post", "/api/platform/templates"),
    ("patch", "/api/platform/templates/00000000-0000-0000-0000-000000000001"),
    ("post", "/api/platform/templates/00000000-0000-0000-0000-000000000001/publish"),
    ("post", "/api/platform/templates/00000000-0000-0000-0000-000000000001/duplicate"),
    ("post", "/api/platform/templates/00000000-0000-0000-0000-000000000001/archive"),
    ("post", "/api/platform/templates/00000000-0000-0000-0000-000000000001/restore"),
]


@pytest.mark.parametrize("method,path", PLATFORM_ADMIN_ROUTES)
def test_platform_admin_routes_reject_anonymous_callers(method: str, path: str) -> None:
    kwargs = {"json": {}} if method in {"post", "patch"} else {}
    response = client.request(method.upper(), path, **kwargs)
    assert response.status_code == 401


def test_platform_admin_routes_reject_regular_market_user_token() -> None:
    market_token = create_access_token(str(uuid4()))
    headers = {"Authorization": f"Bearer {market_token}"}
    for method, path in PLATFORM_ADMIN_ROUTES:
        kwargs = {"json": {}} if method in {"post", "patch"} else {}
        response = client.request(method.upper(), path, headers=headers, **kwargs)
        assert response.status_code == 401, f"{method.upper()} {path} accepted a market-user token"


# ---------------------------------------------------------------------------
# CORS / trusted host (section H)
# ---------------------------------------------------------------------------


def test_cors_reflects_allowed_origin() -> None:
    allowed_origin = settings.backend_cors_origins[0]
    response = client.get("/api/health", headers={"Origin": allowed_origin})

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == allowed_origin
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_cors_does_not_reflect_untrusted_origin() -> None:
    response = client.get("/api/health", headers={"Origin": "https://evil.example.com"})

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") is None


def test_cors_preflight_rejects_untrusted_origin() -> None:
    response = client.options(
        "/api/health",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.headers.get("access-control-allow-origin") is None


def test_trusted_host_middleware_rejects_unknown_host() -> None:
    response = client.get("/api/health", headers={"Host": "attacker.example.com"})

    assert response.status_code == 400


def test_security_headers_present_on_response() -> None:
    response = client.get("/api/health")

    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("x-frame-options") == "SAMEORIGIN"
    assert response.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
    assert "permissions-policy" in response.headers


# ---------------------------------------------------------------------------
# Anonymous access to auth-gated / expensive endpoints (sections C, J)
# ---------------------------------------------------------------------------

ANONYMOUS_DENIED_ROUTES = [
    ("get", "/api/campaigns"),
    ("post", "/api/campaigns"),
    ("post", "/api/campaigns/00000000-0000-0000-0000-000000000001/export-jobs"),
    ("get", "/api/campaigns/00000000-0000-0000-0000-000000000001/preview-html"),
    ("post", "/api/campaigns/00000000-0000-0000-0000-000000000001/generate-suggestions"),
    ("get", "/api/catalog/brands"),
    ("post", "/api/catalog/products"),
    ("post", "/api/catalog/market-products/private"),
    ("post", "/api/catalog/my-products/00000000-0000-0000-0000-000000000001/image"),
    ("get", "/api/catalog/my-products/00000000-0000-0000-0000-000000000001/image/content"),
    ("post", "/api/templates/custom"),
    ("post", "/api/templates/00000000-0000-0000-0000-000000000001/thumbnail"),
    ("get", "/api/onboarding"),
    ("get", "/api/market-members"),
    ("post", "/api/market-invitations"),
]


@pytest.mark.parametrize("method,path", ANONYMOUS_DENIED_ROUTES)
def test_anonymous_caller_denied_on_private_and_expensive_routes(method: str, path: str) -> None:
    kwargs = {"json": {}} if method in {"post", "patch"} else {}
    response = client.request(method.upper(), path, **kwargs)
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Cross-market tenant isolation beyond brands (section D) - DB backed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cross_market_isolation_across_resources_when_test_database_url_is_configured() -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed isolation tests skipped.")

    engine = create_async_engine(settings.test_database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def override_session():
        async with session_factory() as session:
            yield session

    market_a_id = uuid4()
    market_b_id = uuid4()
    email_a = f"tenant-a-{market_a_id}@example.com"
    email_b = f"tenant-b-{market_b_id}@example.com"
    password = "TenantPass123!"

    app.dependency_overrides[get_catalog_session] = override_session
    try:
        async with session_factory() as session:
            user_a = User(email=email_a, full_name="Tenant A Admin", password_hash=hash_password(password), is_active=True)
            user_b = User(email=email_b, full_name="Tenant B Admin", password_hash=hash_password(password), is_active=True)
            market_a = Market(
                id=market_a_id, name=f"Market A {market_a_id}", slug=f"tenant-a-{market_a_id}", subscription_plan="growth"
            )
            market_b = Market(
                id=market_b_id, name=f"Market B {market_b_id}", slug=f"tenant-b-{market_b_id}", subscription_plan="growth"
            )
            session.add_all([user_a, user_b, market_a, market_b])
            await session.flush()
            session.add_all(
                [
                    MarketUser(market_id=market_a_id, user_id=user_a.id, role="market_admin", is_active=True),
                    MarketUser(market_id=market_b_id, user_id=user_b.id, role="market_admin", is_active=True),
                ]
            )
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as async_client:
            login_a = await async_client.post("/api/auth/login", json={"email": email_a, "password": password})
            login_b = await async_client.post("/api/auth/login", json={"email": email_b, "password": password})
            assert login_a.status_code == 200
            assert login_b.status_code == 200

            headers_a = {"Authorization": f"Bearer {login_a.json()['access_token']}", "X-Market-Id": str(market_a_id)}
            headers_b_own = {"Authorization": f"Bearer {login_b.json()['access_token']}", "X-Market-Id": str(market_b_id)}
            # B's bearer token, but pointed at A's market_id header -> membership lookup fails.
            headers_b_as_a = {"Authorization": f"Bearer {login_b.json()['access_token']}", "X-Market-Id": str(market_a_id)}

            # Authenticated, but no X-Market-Id at all -> must never reach a mutation.
            no_market_header = await async_client.post(
                "/api/campaigns",
                headers={"Authorization": f"Bearer {login_a.json()['access_token']}"},
                json={"title": "Should not be created"},
            )
            assert no_market_header.status_code == 400

            # --- Campaigns ---
            create_campaign = await async_client.post(
                "/api/campaigns", headers=headers_a, json={"title": "Tenant A Campaign"}
            )
            assert create_campaign.status_code == 201, create_campaign.text
            campaign_id = create_campaign.json()["id"]

            for method, path, body in [
                ("GET", f"/api/campaigns/{campaign_id}", None),
                ("PATCH", f"/api/campaigns/{campaign_id}", {"title": "Hijacked"}),
                ("DELETE", f"/api/campaigns/{campaign_id}", None),
                ("GET", f"/api/campaigns/{campaign_id}/files", None),
                ("GET", f"/api/campaigns/{campaign_id}/export-jobs", None),
                ("POST", f"/api/campaigns/{campaign_id}/finalize", None),
            ]:
                response = await async_client.request(method, path, headers=headers_b_own, json=body)
                assert response.status_code == 404, f"{method} {path} leaked cross-tenant: {response.status_code}"

            # B cannot use A's market_id at all - membership check fails first.
            leaked = await async_client.get(f"/api/campaigns/{campaign_id}", headers=headers_b_as_a)
            assert leaked.status_code == 403

            # A can still read its own campaign (positive control).
            own_read = await async_client.get(f"/api/campaigns/{campaign_id}", headers=headers_a)
            assert own_read.status_code == 200

            # --- Private market products ---
            create_product = await async_client.post(
                "/api/catalog/market-products/private",
                headers=headers_a,
                json={"private_name": "Tenant A Private Product", "currency": "EUR"},
            )
            assert create_product.status_code == 201, create_product.text
            market_product_id = create_product.json()["id"]

            cross_patch = await async_client.patch(
                f"/api/catalog/my-products/{market_product_id}",
                headers=headers_b_own,
                json={"currency": "USD"},
            )
            assert cross_patch.status_code == 404

            cross_image = await async_client.get(
                f"/api/catalog/my-products/{market_product_id}/image/content",
                headers=headers_b_own,
            )
            assert cross_image.status_code == 404

            own_patch = await async_client.patch(
                f"/api/catalog/my-products/{market_product_id}",
                headers=headers_a,
                json={"currency": "USD"},
            )
            assert own_patch.status_code == 200

            # --- Custom templates ---
            create_template = await async_client.post(
                "/api/templates/custom",
                headers=headers_a,
                json={"name": "Tenant A Template", "template_type": "market"},
            )
            assert create_template.status_code == 201, create_template.text
            template_id = create_template.json()["id"]

            cross_template = await async_client.get(f"/api/templates/{template_id}", headers=headers_b_own)
            assert cross_template.status_code == 404

            cross_template_update = await async_client.patch(
                f"/api/templates/{template_id}",
                headers=headers_b_own,
                json={"name": "Hijacked template"},
            )
            assert cross_template_update.status_code == 404

            own_template = await async_client.get(f"/api/templates/{template_id}", headers=headers_a)
            assert own_template.status_code == 200
    finally:
        app.dependency_overrides.pop(get_catalog_session, None)
        await engine.dispose()
