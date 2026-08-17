from __future__ import annotations

import json
import re
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401
from app.api.deps import get_catalog_session
from app.core.config import settings
from app.core.database import Base
from app.core.security import (
    create_access_token,
    hash_whatsapp_verification_code,
    normalize_whatsapp_verification_code,
)
from app.main import app
from app.models import (
    ActivityLog,
    Market,
    MarketUser,
    User,
    UserWhatsAppIdentity,
    WhatsAppSession,
    WhatsAppVerification,
)
from app.models.base import utc_now


# ---------------------------------------------------------------------------
# Shared setup helpers, modelled on _install_telegram_test_app /
# _seed_linked_user in test_telegram_bot.py.
# ---------------------------------------------------------------------------


def _enable_whatsapp_channel(monkeypatch) -> None:
    monkeypatch.setattr(settings, "evolution_whatsapp_enabled", True)
    monkeypatch.setattr(settings, "leafletpilot_whatsapp_number", "+33600000001")
    monkeypatch.setattr(settings, "evolution_instance_name", "test-instance")
    monkeypatch.setattr(settings, "evolution_webhook_secret", "w" * 40)


async def _install_whatsapp_test_app():
    engine = create_async_engine(settings.test_database_url, pool_pre_ping=True, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    async def override_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_catalog_session] = override_session
    return engine, session_factory


async def _cleanup_whatsapp_test_app(engine) -> None:
    app.dependency_overrides.pop(get_catalog_session, None)
    await engine.dispose()


async def _seed_market(session_factory, *, lifecycle_status: str = "active", is_active: bool = True):
    market_id = uuid4()
    async with session_factory() as session:
        market = Market(
            id=market_id,
            name=f"WhatsApp Market {market_id}",
            slug=f"wa-market-{market_id}",
            lifecycle_status=lifecycle_status,
            is_active=is_active,
            country_code="FR",
        )
        session.add(market)
        await session.commit()
    return market_id


async def _seed_member(session_factory, market_id, *, role: str, is_active: bool = True, user_is_active: bool = True):
    user_id = uuid4()
    async with session_factory() as session:
        user = User(id=user_id, email=f"wa-user-{user_id}@example.com", is_active=user_is_active)
        session.add(user)
        await session.flush()
        membership = MarketUser(market_id=market_id, user_id=user_id, role=role, is_active=is_active)
        session.add(membership)
        await session.commit()
        membership_id = membership.id
    return user_id, membership_id


async def _seed_market_with_users(session_factory, *, roles: list[str], lifecycle_status: str = "active", is_active: bool = True):
    """Seeds one market plus one member per role in `roles`.

    Returns (market_id, [(user_id, membership_id), ...]) in the same order as `roles`.
    """
    market_id = await _seed_market(session_factory, lifecycle_status=lifecycle_status, is_active=is_active)
    members = []
    for role in roles:
        members.append(await _seed_member(session_factory, market_id, role=role))
    return market_id, members


def _auth_headers(user_id, market_id) -> dict[str, str]:
    token = create_access_token(str(user_id))
    return {"Authorization": f"Bearer {token}", "X-Market-Id": str(market_id)}


# ---------------------------------------------------------------------------
# 1. Channel disabled
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_verification_returns_503_when_channel_disabled_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    monkeypatch.setattr(settings, "evolution_whatsapp_enabled", False)
    monkeypatch.setattr(settings, "leafletpilot_whatsapp_number", "+33600000001")
    monkeypatch.setattr(settings, "evolution_instance_name", "test-instance")
    monkeypatch.setattr(settings, "evolution_webhook_secret", "w" * 40)

    engine, session_factory = await _install_whatsapp_test_app()
    try:
        market_id, [(admin_id, admin_membership_id)] = await _seed_market_with_users(
            session_factory, roles=["market_admin"]
        )
        headers = _auth_headers(admin_id, market_id)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.post(
                "/api/integrations/whatsapp/verifications",
                headers=headers,
                json={"membership_id": str(admin_membership_id)},
            )

        assert response.status_code == 503
    finally:
        await _cleanup_whatsapp_test_app(engine)


# ---------------------------------------------------------------------------
# 2. Code is hashed, never stored in plaintext
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verification_code_is_hashed_and_plaintext_never_persisted_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    _enable_whatsapp_channel(monkeypatch)
    engine, session_factory = await _install_whatsapp_test_app()
    try:
        market_id, [(admin_id, admin_membership_id)] = await _seed_market_with_users(
            session_factory, roles=["market_admin"]
        )
        headers = _auth_headers(admin_id, market_id)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            created = await client.post(
                "/api/integrations/whatsapp/verifications",
                headers=headers,
                json={"membership_id": str(admin_membership_id)},
            )
        assert created.status_code == 201, created.text
        code = created.json()["code"]
        verification_id = UUID(created.json()["verification_id"])

        async with session_factory() as session:
            row = await session.get(WhatsAppVerification, verification_id)

        assert row is not None
        assert row.code_hash == hash_whatsapp_verification_code(code)
        assert row.code_hash != code
        for column in row.__table__.columns:
            assert getattr(row, column.name) != code
    finally:
        await _cleanup_whatsapp_test_app(engine)


# ---------------------------------------------------------------------------
# 3. Code shape and distinctness
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verification_code_matches_expected_shape_and_is_distinct_across_creates_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    _enable_whatsapp_channel(monkeypatch)
    engine, session_factory = await _install_whatsapp_test_app()
    try:
        market_id, members = await _seed_market_with_users(
            session_factory,
            roles=["market_admin", "market_staff", "market_staff", "market_staff", "market_staff", "market_staff"],
        )
        admin_id, _ = members[0]
        targets = members[1:]
        headers = _auth_headers(admin_id, market_id)

        codes: list[str] = []
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            for _, membership_id in targets:
                response = await client.post(
                    "/api/integrations/whatsapp/verifications",
                    headers=headers,
                    json={"membership_id": str(membership_id)},
                )
                assert response.status_code == 201, response.text
                codes.append(response.json()["code"])

        pattern = re.compile(r"^LP-[0-9A-Z]{4}-[0-9A-Z]{4}$")
        for code in codes:
            assert pattern.match(code), code
            assert normalize_whatsapp_verification_code(code) == code
        assert len(set(codes)) == len(codes)
    finally:
        await _cleanup_whatsapp_test_app(engine)


# ---------------------------------------------------------------------------
# 4. Polling never returns the code
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_verification_never_returns_the_code_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    _enable_whatsapp_channel(monkeypatch)
    engine, session_factory = await _install_whatsapp_test_app()
    try:
        market_id, [(admin_id, admin_membership_id)] = await _seed_market_with_users(
            session_factory, roles=["market_admin"]
        )
        headers = _auth_headers(admin_id, market_id)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            created = await client.post(
                "/api/integrations/whatsapp/verifications",
                headers=headers,
                json={"membership_id": str(admin_membership_id)},
            )
        assert created.status_code == 201, created.text
        code = created.json()["code"]
        verification_id = created.json()["verification_id"]

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.get(
                f"/api/integrations/whatsapp/verifications/{verification_id}", headers=headers
            )
        assert response.status_code == 200
        body = response.json()
        assert "code" not in body
        assert code not in json.dumps(body)
    finally:
        await _cleanup_whatsapp_test_app(engine)


# ---------------------------------------------------------------------------
# 5. Resend invalidates the previous challenge
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resend_invalidates_previous_pending_challenge_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    _enable_whatsapp_channel(monkeypatch)
    monkeypatch.setattr(settings, "whatsapp_verification_resend_cooldown_seconds", 0)
    engine, session_factory = await _install_whatsapp_test_app()
    try:
        market_id, [(admin_id, admin_membership_id)] = await _seed_market_with_users(
            session_factory, roles=["market_admin"]
        )
        headers = _auth_headers(admin_id, market_id)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            first = await client.post(
                "/api/integrations/whatsapp/verifications",
                headers=headers,
                json={"membership_id": str(admin_membership_id)},
            )
            second = await client.post(
                "/api/integrations/whatsapp/verifications",
                headers=headers,
                json={"membership_id": str(admin_membership_id)},
            )
        assert first.status_code == 201, first.text
        assert second.status_code == 201, second.text
        first_id = UUID(first.json()["verification_id"])

        async with session_factory() as session:
            first_row = await session.get(WhatsAppVerification, first_id)
            pending_rows = (
                await session.scalars(
                    select(WhatsAppVerification).where(
                        WhatsAppVerification.user_id == admin_id,
                        WhatsAppVerification.status == "pending",
                    )
                )
            ).all()

        assert first_row.status == "cancelled"
        assert first_row.failure_reason == "superseded"
        assert len(pending_rows) == 1
        assert str(pending_rows[0].id) == second.json()["verification_id"]
    finally:
        await _cleanup_whatsapp_test_app(engine)


# ---------------------------------------------------------------------------
# 6. Resend cooldown
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resend_within_cooldown_returns_429_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    _enable_whatsapp_channel(monkeypatch)
    monkeypatch.setattr(settings, "whatsapp_verification_resend_cooldown_seconds", 300)
    engine, session_factory = await _install_whatsapp_test_app()
    try:
        market_id, [(admin_id, admin_membership_id)] = await _seed_market_with_users(
            session_factory, roles=["market_admin"]
        )
        headers = _auth_headers(admin_id, market_id)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            first = await client.post(
                "/api/integrations/whatsapp/verifications",
                headers=headers,
                json={"membership_id": str(admin_membership_id)},
            )
            second = await client.post(
                "/api/integrations/whatsapp/verifications",
                headers=headers,
                json={"membership_id": str(admin_membership_id)},
            )

        assert first.status_code == 201, first.text
        assert second.status_code == 429
    finally:
        await _cleanup_whatsapp_test_app(engine)


# ---------------------------------------------------------------------------
# 7. Rate limit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_verification_enforces_rate_limit_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    _enable_whatsapp_channel(monkeypatch)
    monkeypatch.setattr(settings, "whatsapp_verification_request_limit", 2)
    monkeypatch.setattr(settings, "whatsapp_verification_resend_cooldown_seconds", 0)
    engine, session_factory = await _install_whatsapp_test_app()
    try:
        market_id, [(admin_id, admin_membership_id)] = await _seed_market_with_users(
            session_factory, roles=["market_admin"]
        )
        headers = _auth_headers(admin_id, market_id)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            first = await client.post(
                "/api/integrations/whatsapp/verifications",
                headers=headers,
                json={"membership_id": str(admin_membership_id)},
            )
            second = await client.post(
                "/api/integrations/whatsapp/verifications",
                headers=headers,
                json={"membership_id": str(admin_membership_id)},
            )
            third = await client.post(
                "/api/integrations/whatsapp/verifications",
                headers=headers,
                json={"membership_id": str(admin_membership_id)},
            )

        assert first.status_code == 201, first.text
        assert second.status_code == 201, second.text
        assert third.status_code == 429
    finally:
        await _cleanup_whatsapp_test_app(engine)


# ---------------------------------------------------------------------------
# 8. Expiry is reported without mutating the row
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_verification_reports_expired_without_mutating_stored_status_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    _enable_whatsapp_channel(monkeypatch)
    engine, session_factory = await _install_whatsapp_test_app()
    try:
        market_id, [(admin_id, admin_membership_id)] = await _seed_market_with_users(
            session_factory, roles=["market_admin"]
        )
        headers = _auth_headers(admin_id, market_id)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            created = await client.post(
                "/api/integrations/whatsapp/verifications",
                headers=headers,
                json={"membership_id": str(admin_membership_id)},
            )
        assert created.status_code == 201, created.text
        verification_id = created.json()["verification_id"]

        async with session_factory() as session:
            row = await session.get(WhatsAppVerification, UUID(verification_id))
            row.expires_at = utc_now() - timedelta(minutes=1)
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.get(
                f"/api/integrations/whatsapp/verifications/{verification_id}", headers=headers
            )
        assert response.status_code == 200
        assert response.json()["status"] == "expired"

        async with session_factory() as session:
            stored_row = await session.get(WhatsAppVerification, UUID(verification_id))
        assert stored_row.status == "pending"
    finally:
        await _cleanup_whatsapp_test_app(engine)


# ---------------------------------------------------------------------------
# 9. Cross-market IDOR on membership_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_verification_membership_id_cross_market_returns_identical_404_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    _enable_whatsapp_channel(monkeypatch)
    engine, session_factory = await _install_whatsapp_test_app()
    try:
        market_a_id, [(admin_a_id, _admin_a_membership_id)] = await _seed_market_with_users(
            session_factory, roles=["market_admin"]
        )
        _market_b_id, [(_, member_b_membership_id)] = await _seed_market_with_users(
            session_factory, roles=["market_admin"]
        )
        headers = _auth_headers(admin_a_id, market_a_id)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            cross_market = await client.post(
                "/api/integrations/whatsapp/verifications",
                headers=headers,
                json={"membership_id": str(member_b_membership_id)},
            )
            random_uuid = await client.post(
                "/api/integrations/whatsapp/verifications",
                headers=headers,
                json={"membership_id": str(uuid4())},
            )

        assert cross_market.status_code == 404
        assert random_uuid.status_code == 404
        assert cross_market.json()["detail"] == random_uuid.json()["detail"]
    finally:
        await _cleanup_whatsapp_test_app(engine)


# ---------------------------------------------------------------------------
# 10. Cross-market IDOR on verification_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_verification_cross_market_returns_identical_404_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    _enable_whatsapp_channel(monkeypatch)
    engine, session_factory = await _install_whatsapp_test_app()
    try:
        market_a_id, [(admin_a_id, _admin_a_membership_id)] = await _seed_market_with_users(
            session_factory, roles=["market_admin"]
        )
        market_b_id, [(admin_b_id, admin_b_membership_id)] = await _seed_market_with_users(
            session_factory, roles=["market_admin"]
        )
        headers_b = _auth_headers(admin_b_id, market_b_id)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            created = await client.post(
                "/api/integrations/whatsapp/verifications",
                headers=headers_b,
                json={"membership_id": str(admin_b_membership_id)},
            )
        assert created.status_code == 201, created.text
        verification_id = created.json()["verification_id"]

        headers_a = _auth_headers(admin_a_id, market_a_id)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            cross_market = await client.get(
                f"/api/integrations/whatsapp/verifications/{verification_id}", headers=headers_a
            )
            random_uuid = await client.get(
                f"/api/integrations/whatsapp/verifications/{uuid4()}", headers=headers_a
            )

        assert cross_market.status_code == 404
        assert random_uuid.status_code == 404
        assert cross_market.json()["detail"] == random_uuid.json()["detail"]
    finally:
        await _cleanup_whatsapp_test_app(engine)


# ---------------------------------------------------------------------------
# 11. Non-admin cannot verify someone else
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_admin_cannot_request_verification_for_another_member_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    _enable_whatsapp_channel(monkeypatch)
    engine, session_factory = await _install_whatsapp_test_app()
    try:
        market_id, [(_, admin_membership_id), (staff_id, _staff_membership_id)] = await _seed_market_with_users(
            session_factory, roles=["market_admin", "market_staff"]
        )
        headers = _auth_headers(staff_id, market_id)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.post(
                "/api/integrations/whatsapp/verifications",
                headers=headers,
                json={"membership_id": str(admin_membership_id)},
            )
        assert response.status_code == 403
    finally:
        await _cleanup_whatsapp_test_app(engine)


# ---------------------------------------------------------------------------
# 12. Non-admin CAN verify themselves
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_admin_can_request_verification_for_self_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    _enable_whatsapp_channel(monkeypatch)
    engine, session_factory = await _install_whatsapp_test_app()
    try:
        market_id, [(_, _admin_membership_id), (staff_id, staff_membership_id)] = await _seed_market_with_users(
            session_factory, roles=["market_admin", "market_staff"]
        )
        headers = _auth_headers(staff_id, market_id)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.post(
                "/api/integrations/whatsapp/verifications",
                headers=headers,
                json={"membership_id": str(staff_membership_id)},
            )
        assert response.status_code == 201, response.text
    finally:
        await _cleanup_whatsapp_test_app(engine)


# ---------------------------------------------------------------------------
# 13. Already-verified target is rejected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_verification_rejects_already_verified_target_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    _enable_whatsapp_channel(monkeypatch)
    engine, session_factory = await _install_whatsapp_test_app()
    try:
        market_id, [(admin_id, admin_membership_id)] = await _seed_market_with_users(
            session_factory, roles=["market_admin"]
        )
        async with session_factory() as session:
            session.add(
                UserWhatsAppIdentity(
                    user_id=admin_id,
                    phone_e164="+33611110000",
                    whatsapp_jid="33611110000@s.whatsapp.net",
                    status="verified",
                    verified_via_market_id=market_id,
                )
            )
            await session.commit()

        headers = _auth_headers(admin_id, market_id)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.post(
                "/api/integrations/whatsapp/verifications",
                headers=headers,
                json={"membership_id": str(admin_membership_id)},
            )
        assert response.status_code == 409
    finally:
        await _cleanup_whatsapp_test_app(engine)


# ---------------------------------------------------------------------------
# 14. Revoke requires an existing verified identity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revoke_without_verified_identity_returns_404_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    _enable_whatsapp_channel(monkeypatch)
    engine, session_factory = await _install_whatsapp_test_app()
    try:
        market_id, [(admin_id, admin_membership_id)] = await _seed_market_with_users(
            session_factory, roles=["market_admin"]
        )
        headers = _auth_headers(admin_id, market_id)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.post(
                f"/api/integrations/whatsapp/members/{admin_membership_id}/revoke",
                headers=headers,
                json={},
            )
        assert response.status_code == 404
    finally:
        await _cleanup_whatsapp_test_app(engine)


# ---------------------------------------------------------------------------
# 15. Revoke works and cascades
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revoke_cascades_identity_pending_verification_and_session_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    _enable_whatsapp_channel(monkeypatch)
    engine, session_factory = await _install_whatsapp_test_app()
    try:
        market_id, [(admin_id, _admin_membership_id), (staff_id, staff_membership_id)] = await _seed_market_with_users(
            session_factory, roles=["market_admin", "market_staff"]
        )
        async with session_factory() as session:
            identity = UserWhatsAppIdentity(
                user_id=staff_id,
                phone_e164="+33622223333",
                whatsapp_jid="33622223333@s.whatsapp.net",
                status="verified",
                verified_via_market_id=market_id,
            )
            session.add(identity)
            await session.flush()
            identity_id = identity.id
            session.add(WhatsAppSession(identity_id=identity_id, user_id=staff_id, state="idle"))
            session.add(
                WhatsAppVerification(
                    user_id=staff_id,
                    market_id=market_id,
                    membership_id=staff_membership_id,
                    code_hash="another-pending-hash",
                    status="pending",
                    expires_at=utc_now() + timedelta(minutes=10),
                )
            )
            await session.commit()

        headers = _auth_headers(admin_id, market_id)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.post(
                f"/api/integrations/whatsapp/members/{staff_membership_id}/revoke",
                headers=headers,
                json={"reason": "lost phone"},
            )
        assert response.status_code == 204, response.text

        async with session_factory() as session:
            refreshed_identity = await session.get(UserWhatsAppIdentity, identity_id)
            sessions_left = (
                await session.scalars(select(WhatsAppSession).where(WhatsAppSession.user_id == staff_id))
            ).all()
            pending_rows = (
                await session.scalars(select(WhatsAppVerification).where(WhatsAppVerification.user_id == staff_id))
            ).all()

        assert refreshed_identity.status == "revoked"
        assert refreshed_identity.revoked_at is not None
        assert refreshed_identity.revoked_by_user_id == admin_id
        assert sessions_left == []
        assert pending_rows
        assert all(row.status == "cancelled" for row in pending_rows)
    finally:
        await _cleanup_whatsapp_test_app(engine)


# ---------------------------------------------------------------------------
# 16. Multi-market revoke guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revoke_by_other_markets_admin_is_blocked_but_self_revoke_succeeds_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    _enable_whatsapp_channel(monkeypatch)
    engine, session_factory = await _install_whatsapp_test_app()
    try:
        market_a_id, [(admin_a_id, _admin_a_membership_id)] = await _seed_market_with_users(
            session_factory, roles=["market_admin"]
        )
        market_b_id = await _seed_market(session_factory)

        # The target user belongs to both market A (as staff) and market B (as staff), both active.
        shared_user_id, membership_a_id = await _seed_member(session_factory, market_a_id, role="market_staff")
        async with session_factory() as session:
            session.add(MarketUser(market_id=market_b_id, user_id=shared_user_id, role="market_staff", is_active=True))
            session.add(
                UserWhatsAppIdentity(
                    user_id=shared_user_id,
                    phone_e164="+33633334444",
                    whatsapp_jid="33633334444@s.whatsapp.net",
                    status="verified",
                    verified_via_market_id=market_a_id,
                )
            )
            await session.commit()

        headers_admin_a = _auth_headers(admin_a_id, market_a_id)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            blocked = await client.post(
                f"/api/integrations/whatsapp/members/{membership_a_id}/revoke",
                headers=headers_admin_a,
                json={},
            )
        assert blocked.status_code == 409

        headers_self = _auth_headers(shared_user_id, market_a_id)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            self_revoke = await client.post(
                f"/api/integrations/whatsapp/members/{membership_a_id}/revoke",
                headers=headers_self,
                json={},
            )
        assert self_revoke.status_code == 204, self_revoke.text
    finally:
        await _cleanup_whatsapp_test_app(engine)


# ---------------------------------------------------------------------------
# 17. Status list hides other members' full phone from a non-admin
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_list_hides_other_members_phone_from_non_admin_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    _enable_whatsapp_channel(monkeypatch)
    engine, session_factory = await _install_whatsapp_test_app()
    try:
        market_id, [
            (admin_id, _admin_membership_id),
            (viewer_id, _viewer_membership_id),
            (target_id, _target_membership_id),
        ] = await _seed_market_with_users(session_factory, roles=["market_admin", "viewer", "market_staff"])

        verified_phone = "+33611112222"
        async with session_factory() as session:
            session.add(
                UserWhatsAppIdentity(
                    user_id=target_id,
                    phone_e164=verified_phone,
                    whatsapp_jid="33611112222@s.whatsapp.net",
                    status="verified",
                    verified_via_market_id=market_id,
                )
            )
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            viewer_response = await client.get(
                "/api/integrations/whatsapp/status", headers=_auth_headers(viewer_id, market_id)
            )
            admin_response = await client.get(
                "/api/integrations/whatsapp/status", headers=_auth_headers(admin_id, market_id)
            )

        assert viewer_response.status_code == 200
        assert admin_response.status_code == 200
        viewer_rows = {row["user_id"]: row for row in viewer_response.json()["members"]}
        admin_rows = {row["user_id"]: row for row in admin_response.json()["members"]}

        target_row_as_viewer = viewer_rows[str(target_id)]
        assert target_row_as_viewer["verified_phone"] is None
        assert target_row_as_viewer["verified_phone_masked"]

        target_row_as_admin = admin_rows[str(target_id)]
        assert target_row_as_admin["verified_phone"] == verified_phone
    finally:
        await _cleanup_whatsapp_test_app(engine)


# ---------------------------------------------------------------------------
# 18. Status list derives every state
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_list_derives_all_five_member_states_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    _enable_whatsapp_channel(monkeypatch)
    engine, session_factory = await _install_whatsapp_test_app()
    try:
        market_id, members = await _seed_market_with_users(
            session_factory,
            roles=["market_admin", "market_staff", "market_staff", "market_staff", "market_staff", "market_staff"],
        )
        admin_id, _admin_membership_id = members[0]
        (not_configured_id, not_configured_membership_id) = members[1]
        (pending_id, pending_membership_id) = members[2]
        (expired_id, expired_membership_id) = members[3]
        (verified_id, _verified_membership_id) = members[4]
        (revoked_id, _revoked_membership_id) = members[5]

        now = utc_now()
        async with session_factory() as session:
            session.add(
                WhatsAppVerification(
                    user_id=pending_id,
                    market_id=market_id,
                    membership_id=pending_membership_id,
                    code_hash="status-pending-hash",
                    status="pending",
                    expires_at=now + timedelta(minutes=10),
                )
            )
            session.add(
                WhatsAppVerification(
                    user_id=expired_id,
                    market_id=market_id,
                    membership_id=expired_membership_id,
                    code_hash="status-expired-hash",
                    status="pending",
                    expires_at=now - timedelta(minutes=1),
                )
            )
            session.add(
                UserWhatsAppIdentity(
                    user_id=verified_id,
                    phone_e164="+33600000099",
                    whatsapp_jid="33600000099@s.whatsapp.net",
                    status="verified",
                    verified_via_market_id=market_id,
                )
            )
            session.add(
                UserWhatsAppIdentity(
                    user_id=revoked_id,
                    phone_e164="+33600000098",
                    whatsapp_jid="33600000098@s.whatsapp.net",
                    status="revoked",
                    verified_via_market_id=market_id,
                    revoked_at=now,
                )
            )
            await session.commit()

        _ = not_configured_membership_id  # no DB row needed for this state
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.get(
                "/api/integrations/whatsapp/status", headers=_auth_headers(admin_id, market_id)
            )
        assert response.status_code == 200
        rows_by_user = {row["user_id"]: row["status"] for row in response.json()["members"]}

        assert rows_by_user[str(not_configured_id)] == "not_configured"
        assert rows_by_user[str(pending_id)] == "pending"
        assert rows_by_user[str(expired_id)] == "expired"
        assert rows_by_user[str(verified_id)] == "verified"
        assert rows_by_user[str(revoked_id)] == "revoked"
        observed_statuses = {
            rows_by_user[str(uid)]
            for uid in (not_configured_id, pending_id, expired_id, verified_id, revoked_id)
        }
        assert observed_statuses == {"not_configured", "pending", "expired", "verified", "revoked"}
    finally:
        await _cleanup_whatsapp_test_app(engine)


# ---------------------------------------------------------------------------
# 19. Audit rows carry no secrets
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_log_rows_never_contain_secrets_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    _enable_whatsapp_channel(monkeypatch)
    engine, session_factory = await _install_whatsapp_test_app()
    try:
        market_id, [(admin_id, _admin_membership_id), (staff_id, staff_membership_id)] = await _seed_market_with_users(
            session_factory, roles=["market_admin", "market_staff"]
        )
        headers = _auth_headers(admin_id, market_id)
        claimed_phone = "+33612345678"

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            created = await client.post(
                "/api/integrations/whatsapp/verifications",
                headers=headers,
                json={"membership_id": str(staff_membership_id), "phone": claimed_phone},
            )
        assert created.status_code == 201, created.text
        code = created.json()["code"]

        # Seed a verified identity directly — the Evolution webhook flow that would normally
        # produce it is out of scope for these endpoint-level tests.
        verified_phone = "+33687654321"
        async with session_factory() as session:
            session.add(
                UserWhatsAppIdentity(
                    user_id=staff_id,
                    phone_e164=verified_phone,
                    whatsapp_jid="33687654321@s.whatsapp.net",
                    status="verified",
                    verified_via_market_id=market_id,
                )
            )
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            revoked = await client.post(
                f"/api/integrations/whatsapp/members/{staff_membership_id}/revoke",
                headers=headers,
                json={},
            )
        assert revoked.status_code == 204, revoked.text

        async with session_factory() as session:
            rows = (
                await session.scalars(
                    select(ActivityLog).where(
                        ActivityLog.action.in_(
                            ["WHATSAPP_VERIFICATION_REQUESTED", "WHATSAPP_VERIFICATION_REVOKED"]
                        )
                    )
                )
            ).all()

        assert {row.action for row in rows} == {
            "WHATSAPP_VERIFICATION_REQUESTED",
            "WHATSAPP_VERIFICATION_REVOKED",
        }
        for row in rows:
            dumped = json.dumps(row.metadata_)
            assert code not in dumped
            assert claimed_phone not in dumped
            assert verified_phone not in dumped
            assert "*" in dumped
    finally:
        await _cleanup_whatsapp_test_app(engine)
