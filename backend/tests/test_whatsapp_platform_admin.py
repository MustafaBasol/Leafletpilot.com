"""Platform Admin coverage for the central LeafletPilot WhatsApp channel.

`app/api/routes/platform_whatsapp.py` is entirely gated behind
`get_current_platform_admin` (a *separate* JWT type from the tenant
`get_current_user` token — see `app/core/security.py::create_platform_access_token`
/ `decode_platform_access_token`) and is documented to never surface a secret:
the Evolution API key, the webhook secret, the full base URL and verification
codes/code hashes must never appear in any response body.

DB-backed tests follow the `test_telegram_bot.py` / `test_platform_billing.py`
convention: `..._when_test_database_url_is_configured` name suffix, an
explicit `pytest.skip` guard, a fresh engine per test bound to
`settings.test_database_url` with `NullPool`, `Base.metadata.drop_all` +
`create_all`, and `app.dependency_overrides` for both `get_catalog_session`
and (for the connection-test endpoint) `get_evolution_client`.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401
from app.api.deps import get_catalog_session
from app.api.routes.platform_whatsapp import get_evolution_client
from app.core.config import settings
from app.core.database import Base
from app.core.security import (
    create_access_token,
    create_platform_access_token,
    hash_password,
    hash_whatsapp_verification_code,
)
from app.main import app
from app.models import (
    Market,
    MarketUser,
    PlatformAdmin,
    PlatformAuditLog,
    User,
    UserWhatsAppIdentity,
    WhatsAppIntegrationState,
    WhatsAppSession,
    WhatsAppVerification,
)
from app.models.base import utc_now

WHATSAPP_BASE = "/api/platform/integrations/whatsapp"


class _FakeEvolutionClient:
    """Minimal stand-in for `EvolutionClientProtocol` used via dependency override."""

    def __init__(self, *, result=None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error

    async def fetch_connection_state(self):
        if self._error is not None:
            raise self._error
        return self._result

    async def send_text(self, *args, **kwargs):  # pragma: no cover - unused by these tests
        raise NotImplementedError

    async def send_media(self, *args, **kwargs):  # pragma: no cover - unused by these tests
        raise NotImplementedError

    async def aclose(self) -> None:
        return None


# ---------------------------------------------------------------------------
# 1. RBAC — platform auth required on every endpoint, market auth rejected.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_whatsapp_platform_admin_endpoints_require_platform_auth() -> None:
    market_user_token = create_access_token(str(uuid4()))
    some_id = uuid4()
    endpoints = [
        ("GET", f"{WHATSAPP_BASE}/health", {}),
        ("POST", f"{WHATSAPP_BASE}/connection-test", {}),
        ("GET", f"{WHATSAPP_BASE}/identities", {}),
        ("POST", f"{WHATSAPP_BASE}/identities/{some_id}/revoke", {"json": {}}),
    ]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        for method, path, kwargs in endpoints:
            no_auth = await client.request(method, path, **kwargs)
            assert no_auth.status_code == 401, f"{method} {path} without auth returned {no_auth.status_code}"

            market_auth = await client.request(
                method,
                path,
                headers={"Authorization": f"Bearer {market_user_token}"},
                **kwargs,
            )
            assert market_auth.status_code == 401, f"{method} {path} with market token returned {market_auth.status_code}"


# ---------------------------------------------------------------------------
# 2/3/4. GET /health
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_whatsapp_health_reports_disabled_and_unconfigured_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp platform admin tests skipped.")

    monkeypatch.setattr(settings, "evolution_whatsapp_enabled", False)
    engine, session_factory = await _install_whatsapp_test_app(monkeypatch)
    try:
        _, token = await _seed_platform_admin(session_factory)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.get(f"{WHATSAPP_BASE}/health", headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 200
        body = response.json()
        assert body["enabled"] is False
        assert body["configured"] is False
    finally:
        await _cleanup_whatsapp_test_app(engine)


@pytest.mark.asyncio
async def test_whatsapp_health_never_leaks_secrets_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp platform admin tests skipped.")

    api_key = "super-secret-key-value"
    webhook_secret = "w" * 40
    base_url = "https://evo.example.com/base"
    official_number = "+33600000001"
    monkeypatch.setattr(settings, "evolution_api_key", api_key)
    monkeypatch.setattr(settings, "evolution_webhook_secret", webhook_secret)
    monkeypatch.setattr(settings, "evolution_api_base_url", base_url)
    monkeypatch.setattr(settings, "leafletpilot_whatsapp_number", official_number)
    monkeypatch.setattr(settings, "evolution_instance_name", "test-instance")

    engine, session_factory = await _install_whatsapp_test_app(monkeypatch)
    try:
        _, token = await _seed_platform_admin(session_factory)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.get(f"{WHATSAPP_BASE}/health", headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 200
        raw = response.text
        assert api_key not in raw
        assert webhook_secret not in raw
        assert base_url not in raw
        assert official_number not in raw
        assert "evo.example.com" in raw

        body = response.json()
        assert body["official_number_masked"] is not None
        assert "*" in body["official_number_masked"]
    finally:
        await _cleanup_whatsapp_test_app(engine)


@pytest.mark.asyncio
async def test_whatsapp_health_counts_verified_pending_and_markets_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp platform admin tests skipped.")

    engine, session_factory = await _install_whatsapp_test_app(monkeypatch)
    try:
        _, token = await _seed_platform_admin(session_factory)
        async with session_factory() as session:
            market_1 = await _create_market(session, name="Health Market 1")
            market_2 = await _create_market(session, name="Health Market 2")
            market_3 = await _create_market(session, name="Health Market 3")

            verified_user_1 = await _create_user(session, email="health-verified-1@example.com")
            verified_user_2 = await _create_user(session, email="health-verified-2@example.com")
            revoked_user = await _create_user(session, email="health-revoked@example.com")
            pending_user = await _create_user(session, email="health-pending@example.com")
            expired_user = await _create_user(session, email="health-expired@example.com")

            await _add_membership(session, market=market_1, user=verified_user_1)
            await _add_membership(session, market=market_2, user=verified_user_2)
            await _add_membership(session, market=market_3, user=revoked_user)

            await _add_identity(session, user=verified_user_1, phone_e164="+33600000071", status="verified")
            await _add_identity(session, user=verified_user_2, phone_e164="+33600000072", status="verified")
            await _add_identity(session, user=revoked_user, phone_e164="+33600000073", status="revoked")

            session.add(
                WhatsAppVerification(
                    user_id=pending_user.id,
                    market_id=market_1.id,
                    code_hash=f"hash-{uuid4()}",
                    status="pending",
                    expires_at=utc_now() + timedelta(minutes=10),
                )
            )
            session.add(
                WhatsAppVerification(
                    user_id=expired_user.id,
                    market_id=market_2.id,
                    code_hash=f"hash-{uuid4()}",
                    status="pending",
                    expires_at=utc_now() - timedelta(minutes=1),
                )
            )
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.get(f"{WHATSAPP_BASE}/health", headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 200
        body = response.json()
        assert body["verified_identity_count"] == 2
        assert body["pending_verification_count"] == 1
        assert body["market_count_with_verified_users"] == 2
    finally:
        await _cleanup_whatsapp_test_app(engine)


# ---------------------------------------------------------------------------
# 5/6/7. POST /connection-test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_whatsapp_connection_test_returns_ok_false_when_disabled_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp platform admin tests skipped.")

    monkeypatch.setattr(settings, "evolution_whatsapp_enabled", False)
    engine, session_factory = await _install_whatsapp_test_app(monkeypatch)
    try:
        _, token = await _seed_platform_admin(session_factory)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.post(
                f"{WHATSAPP_BASE}/connection-test", headers={"Authorization": f"Bearer {token}"}
            )

        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is False
        assert body["detail"]
        assert "devre" in body["detail"].lower()
    finally:
        await _cleanup_whatsapp_test_app(engine)


@pytest.mark.asyncio
async def test_whatsapp_connection_test_success_persists_state_and_audit_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp platform admin tests skipped.")

    from app.integrations.whatsapp.client import EvolutionConnectionState

    monkeypatch.setattr(settings, "evolution_whatsapp_enabled", True)
    monkeypatch.setattr(settings, "evolution_instance_name", "success-instance")
    fake_client = _FakeEvolutionClient(result=EvolutionConnectionState(ok=True, state="open"))
    engine, session_factory = await _install_whatsapp_test_app(monkeypatch, evolution_client=fake_client)
    try:
        _, token = await _seed_platform_admin(session_factory)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.post(
                f"{WHATSAPP_BASE}/connection-test", headers={"Authorization": f"Bearer {token}"}
            )

        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        assert body["state"] == "open"

        async with session_factory() as session:
            state = await session.scalar(
                select(WhatsAppIntegrationState).where(
                    WhatsAppIntegrationState.instance_name == "success-instance"
                )
            )
            assert state is not None
            assert state.last_connection_ok is True
            assert state.last_connection_check_at is not None

            audit = await session.scalar(
                select(PlatformAuditLog).where(PlatformAuditLog.action == "EVOLUTION_CONNECTION_TESTED")
            )
            assert audit is not None
            assert audit.metadata_.get("ok") is True
            assert audit.metadata_.get("state") == "open"
            assert "super-secret" not in str(audit.metadata_)
    finally:
        await _cleanup_whatsapp_test_app(engine)


@pytest.mark.asyncio
async def test_whatsapp_connection_test_failure_paths_never_leak_underlying_error_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp platform admin tests skipped.")

    from app.integrations.whatsapp.client import EvolutionAuthError, EvolutionClientError, EvolutionUnavailableError

    monkeypatch.setattr(settings, "evolution_whatsapp_enabled", True)
    engine, session_factory = await _install_whatsapp_test_app(monkeypatch)
    try:
        _, token = await _seed_platform_admin(session_factory)
        secret_fragment = "sk-leak-me"
        secret_message = f"api key {secret_fragment} failed"
        cases = [
            EvolutionAuthError(secret_message),
            EvolutionUnavailableError(secret_message),
            EvolutionClientError(secret_message),
        ]

        seen_details: set[str] = set()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            for exc in cases:

                async def override_client(exc=exc):
                    yield _FakeEvolutionClient(error=exc)

                app.dependency_overrides[get_evolution_client] = override_client
                response = await client.post(
                    f"{WHATSAPP_BASE}/connection-test", headers={"Authorization": f"Bearer {token}"}
                )
                assert response.status_code == 200
                body = response.json()
                assert body["ok"] is False
                assert body["detail"]
                seen_details.add(body["detail"])
                assert secret_fragment not in response.text

        # Each failure path has its own distinct Turkish detail message.
        assert len(seen_details) == 3

        async with session_factory() as session:
            state = await session.scalar(select(WhatsAppIntegrationState))
            assert state is not None
            assert secret_fragment not in (state.last_connection_error or "")
    finally:
        await _cleanup_whatsapp_test_app(engine)


# ---------------------------------------------------------------------------
# 8-13. GET /identities
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_whatsapp_identities_one_row_per_identity_with_all_markets_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp platform admin tests skipped.")

    engine, session_factory = await _install_whatsapp_test_app(monkeypatch)
    try:
        _, token = await _seed_platform_admin(session_factory)
        async with session_factory() as session:
            user = await _create_user(session, email="triple-market@example.com", full_name="Triple Market")
            market_a = await _create_market(session, name="Triple Market A")
            market_b = await _create_market(session, name="Triple Market B")
            market_c = await _create_market(session, name="Triple Market C")
            await _add_membership(session, market=market_a, user=user, role="market_admin")
            await _add_membership(session, market=market_b, user=user, role="market_staff")
            await _add_membership(session, market=market_c, user=user, role="viewer")
            await _add_identity(session, user=user, phone_e164="+33600000031")
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.get(
                f"{WHATSAPP_BASE}/identities", headers={"Authorization": f"Bearer {token}"}
            )

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert len(body["items"]) == 1
        item = body["items"][0]
        assert len(item["markets"]) == 3
        roles_by_market = {market["market_name"]: market["role"] for market in item["markets"]}
        assert roles_by_market == {
            "Triple Market A": "market_admin",
            "Triple Market B": "market_staff",
            "Triple Market C": "viewer",
        }
    finally:
        await _cleanup_whatsapp_test_app(engine)


@pytest.mark.asyncio
async def test_whatsapp_identities_market_filter_still_shows_every_market_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp platform admin tests skipped.")

    engine, session_factory = await _install_whatsapp_test_app(monkeypatch)
    try:
        _, token = await _seed_platform_admin(session_factory)
        async with session_factory() as session:
            market_a = await _create_market(session, name="Filter Market A")
            market_b = await _create_market(session, name="Filter Market B")
            user_a = await _create_user(session, email="filter-a@example.com")
            user_b = await _create_user(session, email="filter-b@example.com")
            user_both = await _create_user(session, email="filter-both@example.com")
            await _add_membership(session, market=market_a, user=user_a)
            await _add_membership(session, market=market_b, user=user_b)
            await _add_membership(session, market=market_a, user=user_both)
            await _add_membership(session, market=market_b, user=user_both)
            await _add_identity(session, user=user_a, phone_e164="+33600000041")
            await _add_identity(session, user=user_b, phone_e164="+33600000042")
            await _add_identity(session, user=user_both, phone_e164="+33600000043")
            market_a_id = market_a.id
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.get(
                f"{WHATSAPP_BASE}/identities",
                params={"market_id": str(market_a_id)},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 2
        emails = {item["user_email"] for item in body["items"]}
        assert emails == {"filter-a@example.com", "filter-both@example.com"}
        both_item = next(item for item in body["items"] if item["user_email"] == "filter-both@example.com")
        assert {market["market_name"] for market in both_item["markets"]} == {"Filter Market A", "Filter Market B"}
    finally:
        await _cleanup_whatsapp_test_app(engine)


@pytest.mark.asyncio
async def test_whatsapp_identities_status_filter_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp platform admin tests skipped.")

    engine, session_factory = await _install_whatsapp_test_app(monkeypatch)
    try:
        _, token = await _seed_platform_admin(session_factory)
        async with session_factory() as session:
            verified_user = await _create_user(session, email="status-verified@example.com")
            revoked_user = await _create_user(session, email="status-revoked@example.com")
            market = await _create_market(session)
            await _add_membership(session, market=market, user=verified_user)
            await _add_membership(session, market=market, user=revoked_user)
            await _add_identity(session, user=verified_user, phone_e164="+33600000061", status="verified")
            await _add_identity(session, user=revoked_user, phone_e164="+33600000062", status="revoked")
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            verified_response = await client.get(
                f"{WHATSAPP_BASE}/identities",
                params={"status": "verified"},
                headers={"Authorization": f"Bearer {token}"},
            )
            revoked_response = await client.get(
                f"{WHATSAPP_BASE}/identities",
                params={"status": "revoked"},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert {item["user_email"] for item in verified_response.json()["items"]} == {"status-verified@example.com"}
        assert {item["user_email"] for item in revoked_response.json()["items"]} == {"status-revoked@example.com"}
    finally:
        await _cleanup_whatsapp_test_app(engine)


@pytest.mark.asyncio
async def test_whatsapp_identities_search_matches_email_and_name_case_insensitively_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp platform admin tests skipped.")

    engine, session_factory = await _install_whatsapp_test_app(monkeypatch)
    try:
        _, token = await _seed_platform_admin(session_factory)
        async with session_factory() as session:
            user = await _create_user(
                session, email="Distinctive.Person@Example.com", full_name="Zed Uncommon Name"
            )
            market = await _create_market(session)
            await _add_membership(session, market=market, user=user)
            await _add_identity(session, user=user, phone_e164="+33600000051")

            other = await _create_user(session, email="other-search@example.com", full_name="Other Person")
            other_market = await _create_market(session)
            await _add_membership(session, market=other_market, user=other)
            await _add_identity(session, user=other, phone_e164="+33600000052")
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            by_email = await client.get(
                f"{WHATSAPP_BASE}/identities",
                params={"search": "distinctive.person"},
                headers={"Authorization": f"Bearer {token}"},
            )
            by_name = await client.get(
                f"{WHATSAPP_BASE}/identities",
                params={"search": "uncommon"},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert by_email.json()["total"] == 1
        assert by_email.json()["items"][0]["user_email"] == "Distinctive.Person@Example.com"
        assert by_name.json()["total"] == 1
        assert by_name.json()["items"][0]["user_email"] == "Distinctive.Person@Example.com"
    finally:
        await _cleanup_whatsapp_test_app(engine)


@pytest.mark.asyncio
async def test_whatsapp_identities_search_by_phone_normalizes_spaces_and_plus_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp platform admin tests skipped.")

    engine, session_factory = await _install_whatsapp_test_app(monkeypatch)
    try:
        _, token = await _seed_platform_admin(session_factory)
        async with session_factory() as session:
            user = await _create_user(session, email="phone-search@example.com")
            market = await _create_market(session)
            await _add_membership(session, market=market, user=user)
            await _add_identity(session, user=user, phone_e164="+33600000012")
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.get(
                f"{WHATSAPP_BASE}/identities",
                params={"phone": "+33 600 000 012"},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["phone_e164"] == "+33600000012"
    finally:
        await _cleanup_whatsapp_test_app(engine)


@pytest.mark.asyncio
async def test_whatsapp_identities_paging_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp platform admin tests skipped.")

    engine, session_factory = await _install_whatsapp_test_app(monkeypatch)
    try:
        _, token = await _seed_platform_admin(session_factory)
        async with session_factory() as session:
            for index in range(3):
                user = await _create_user(session, email=f"page-{index}@example.com")
                market = await _create_market(session, name=f"Page Market {index}")
                await _add_membership(session, market=market, user=user)
                await _add_identity(session, user=user, phone_e164=f"+3360000010{index}")
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            first_page = await client.get(
                f"{WHATSAPP_BASE}/identities",
                params={"limit": 2, "offset": 0},
                headers={"Authorization": f"Bearer {token}"},
            )
            second_page = await client.get(
                f"{WHATSAPP_BASE}/identities",
                params={"limit": 2, "offset": 2},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert first_page.json()["total"] == 3
        assert len(first_page.json()["items"]) == 2
        assert second_page.json()["total"] == 3
        assert len(second_page.json()["items"]) == 1
    finally:
        await _cleanup_whatsapp_test_app(engine)


# ---------------------------------------------------------------------------
# 14/15. POST /identities/{id}/revoke
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_whatsapp_revoke_identity_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp platform admin tests skipped.")

    engine, session_factory = await _install_whatsapp_test_app(monkeypatch)
    try:
        admin_id, token = await _seed_platform_admin(session_factory)
        user_id, identity_id, pending_id = await _seed_identity_for_revoke(session_factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            missing = await client.post(
                f"{WHATSAPP_BASE}/identities/{uuid4()}/revoke",
                headers={"Authorization": f"Bearer {token}"},
                json={"reason": "abuse"},
            )
            assert missing.status_code == 404

            response = await client.post(
                f"{WHATSAPP_BASE}/identities/{identity_id}/revoke",
                headers={"Authorization": f"Bearer {token}"},
                json={"reason": "fraud suspected"},
            )
            assert response.status_code == 204

        async with session_factory() as session:
            identity = await session.get(UserWhatsAppIdentity, identity_id)
            assert identity.status == "revoked"
            assert identity.revoked_at is not None
            assert identity.revoked_by_platform_admin_id == admin_id

            pending = await session.get(WhatsAppVerification, pending_id)
            assert pending.status == "cancelled"

            remaining_session = await session.scalar(
                select(WhatsAppSession).where(WhatsAppSession.user_id == user_id)
            )
            assert remaining_session is None

            audit = await session.scalar(
                select(PlatformAuditLog).where(PlatformAuditLog.action == "WHATSAPP_VERIFICATION_REVOKED")
            )
            assert audit is not None
            assert audit.metadata_.get("phone_masked")
            assert "*" in audit.metadata_["phone_masked"]
            assert "+33600000099" not in str(audit.metadata_)
    finally:
        await _cleanup_whatsapp_test_app(engine)


@pytest.mark.asyncio
async def test_whatsapp_revoke_identity_is_idempotent_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp platform admin tests skipped.")

    engine, session_factory = await _install_whatsapp_test_app(monkeypatch)
    try:
        _, token = await _seed_platform_admin(session_factory)
        _, identity_id, _ = await _seed_identity_for_revoke(session_factory)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            first = await client.post(
                f"{WHATSAPP_BASE}/identities/{identity_id}/revoke",
                headers={"Authorization": f"Bearer {token}"},
                json={},
            )
            second = await client.post(
                f"{WHATSAPP_BASE}/identities/{identity_id}/revoke",
                headers={"Authorization": f"Bearer {token}"},
                json={},
            )

        assert first.status_code == 204
        assert second.status_code == 204

        async with session_factory() as session:
            count = await session.scalar(
                select(func.count())
                .select_from(PlatformAuditLog)
                .where(PlatformAuditLog.action == "WHATSAPP_VERIFICATION_REVOKED")
            )
        assert count == 1
    finally:
        await _cleanup_whatsapp_test_app(engine)


# ---------------------------------------------------------------------------
# 16. No endpoint ever returns a verification code or code hash.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_whatsapp_health_and_identities_never_leak_verification_code_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp platform admin tests skipped.")

    engine, session_factory = await _install_whatsapp_test_app(monkeypatch)
    try:
        _, token = await _seed_platform_admin(session_factory)
        plaintext_code = "LP-X7K4-M92Q"
        code_hash = hash_whatsapp_verification_code(plaintext_code)
        async with session_factory() as session:
            user = await _create_user(session, email="pending-code@example.com")
            market = await _create_market(session)
            await _add_membership(session, market=market, user=user)
            session.add(
                WhatsAppVerification(
                    user_id=user.id,
                    market_id=market.id,
                    code_hash=code_hash,
                    status="pending",
                    expires_at=utc_now() + timedelta(minutes=10),
                )
            )
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            health = await client.get(f"{WHATSAPP_BASE}/health", headers={"Authorization": f"Bearer {token}"})
            identities = await client.get(
                f"{WHATSAPP_BASE}/identities", headers={"Authorization": f"Bearer {token}"}
            )

        assert plaintext_code not in health.text
        assert code_hash not in health.text
        assert plaintext_code not in identities.text
        assert code_hash not in identities.text
    finally:
        await _cleanup_whatsapp_test_app(engine)


# ---------------------------------------------------------------------------
# Shared install / cleanup / seeding helpers.
# ---------------------------------------------------------------------------


async def _install_whatsapp_test_app(monkeypatch, evolution_client=None):
    engine = create_async_engine(settings.test_database_url, pool_pre_ping=True, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    async def override_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_catalog_session] = override_session

    if evolution_client is not None:

        async def override_client():
            yield evolution_client

        app.dependency_overrides[get_evolution_client] = override_client

    return engine, session_factory


async def _cleanup_whatsapp_test_app(engine) -> None:
    app.dependency_overrides.pop(get_catalog_session, None)
    app.dependency_overrides.pop(get_evolution_client, None)
    await engine.dispose()


async def _seed_platform_admin(session_factory) -> tuple[UUID, str]:
    admin_id = uuid4()
    async with session_factory() as session:
        session.add(
            PlatformAdmin(
                id=admin_id,
                email=f"admin-{admin_id}@example.com",
                full_name="Platform Admin",
                password_hash=hash_password("Sup3rSecret!123"),
                is_active=True,
            )
        )
        await session.commit()
    return admin_id, create_platform_access_token(str(admin_id))


async def _create_market(session, *, name: str | None = None, lifecycle_status: str = "active", is_active: bool = True) -> Market:
    market_id = uuid4()
    market = Market(
        id=market_id,
        name=name or f"Market {market_id}",
        slug=f"market-{market_id}",
        lifecycle_status=lifecycle_status,
        is_active=is_active,
    )
    session.add(market)
    await session.flush()
    return market


async def _create_user(session, *, email: str | None = None, full_name: str | None = None, is_active: bool = True) -> User:
    user_id = uuid4()
    user = User(
        id=user_id,
        email=email or f"user-{user_id}@example.com",
        full_name=full_name,
        is_active=is_active,
    )
    session.add(user)
    await session.flush()
    return user


async def _add_membership(session, *, market: Market, user: User, role: str = "market_admin", is_active: bool = True) -> MarketUser:
    membership = MarketUser(market_id=market.id, user_id=user.id, role=role, is_active=is_active)
    session.add(membership)
    await session.flush()
    return membership


async def _add_identity(
    session, *, user: User, phone_e164: str, status: str = "verified", jid: str | None = None
) -> UserWhatsAppIdentity:
    identity = UserWhatsAppIdentity(
        user_id=user.id,
        phone_e164=phone_e164,
        whatsapp_jid=jid or f"{phone_e164.lstrip('+')}@s.whatsapp.net",
        status=status,
    )
    session.add(identity)
    await session.flush()
    return identity


async def _seed_identity_for_revoke(session_factory) -> tuple[UUID, UUID, UUID]:
    """Seeds one verified identity plus a live session and a pending verification.

    Returns (user_id, identity_id, pending_verification_id).
    """
    async with session_factory() as session:
        user = await _create_user(session, email=f"revoke-{uuid4()}@example.com")
        market = await _create_market(session, name="Revoke Market")
        await _add_membership(session, market=market, user=user)
        identity = await _add_identity(session, user=user, phone_e164="+33600000099")
        session.add(WhatsAppSession(identity_id=identity.id, user_id=user.id, state="idle"))
        pending = WhatsAppVerification(
            user_id=user.id,
            market_id=market.id,
            code_hash=f"hash-{uuid4()}",
            status="pending",
            expires_at=utc_now() + timedelta(minutes=10),
        )
        session.add(pending)
        await session.commit()
        return user.id, identity.id, pending.id
