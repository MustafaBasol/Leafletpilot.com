from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.api.deps import get_catalog_session, get_current_platform_admin
from app.core.config import settings
from app.core.database import Base
from app.main import app
from app.models import Market, MarketInvitation, PlatformAdmin
from app.services.invitation_email import InvitationEmailError


@pytest.mark.asyncio
async def test_owner_invitation_delivery_success_metadata_and_resend_rotation(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed invitation delivery tests skipped.")

    engine = create_async_engine(settings.test_database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    captured_urls = []

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    admin = PlatformAdmin(id=uuid4(), email="platform@example.com", full_name="Platform Admin", password_hash="hash")
    market_id = uuid4()

    async def override_session():
        async with session_factory() as session:
            yield session

    async def override_admin():
        return admin

    async def fake_send(message):
        captured_urls.append(message.accept_url)

    monkeypatch.setattr("app.api.routes.platform.send_owner_invitation_email", fake_send)
    app.dependency_overrides[get_catalog_session] = override_session
    app.dependency_overrides[get_current_platform_admin] = override_admin
    try:
        async with session_factory() as session:
            session.add_all(
                [
                    admin,
                    Market(
                        id=market_id,
                        name="Pilot Market",
                        slug=f"pilot-{market_id}",
                        language="tr",
                        contact_email="owner@example.com",
                        lifecycle_status="trial",
                        onboarding_status="not_started",
                        onboarding_step=1,
                        is_active=True,
                    ),
                ]
            )
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as async_client:
            first = await async_client.post(f"/api/platform/markets/{market_id}/owner-invitation", json={})
            assert first.status_code == 200, first.text
            first_body = first.json()
            assert "token" not in first.text
            assert captured_urls[0] not in first.text
            assert first_body["invitation"]["status"] == "sent"
            assert first_body["invitation"]["send_count"] == 1
            assert first_body["invitation"]["last_sent_at"] is not None

            old_token = captured_urls[0].rsplit("token=", 1)[-1]
            rotated = await async_client.post(f"/api/platform/markets/{market_id}/owner-invitation/rotate", json={})
            assert rotated.status_code == 200, rotated.text
            new_token = captured_urls[1].rsplit("token=", 1)[-1]
            assert new_token != old_token
            assert captured_urls[1] not in rotated.text
            assert rotated.json()["invitation"]["status"] == "sent"

            old_accept = await async_client.post(
                "/api/auth/accept-invitation",
                json={"token": old_token, "full_name": "Old Owner", "password": "OwnerPass123!"},
            )
            assert old_accept.status_code == 409

            preview = await async_client.post("/api/auth/invitation-preview", json={"token": new_token})
            assert preview.status_code == 200
            assert preview.json()["email"] == "owner@example.com"

        async with session_factory() as session:
            invitations = (
                await session.scalars(select(MarketInvitation).where(MarketInvitation.market_id == market_id).order_by(MarketInvitation.created_at))
            ).all()
            assert [invitation.status for invitation in invitations] == ["revoked", "sent"]
            assert invitations[0].token_hash != invitations[1].token_hash
            assert invitations[1].last_sent_at is not None
            assert invitations[1].send_count == 1
    finally:
        app.dependency_overrides.pop(get_catalog_session, None)
        app.dependency_overrides.pop(get_current_platform_admin, None)
        await engine.dispose()


@pytest.mark.asyncio
async def test_owner_invitation_delivery_failure_keeps_retryable_failed_state(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed invitation delivery tests skipped.")

    engine = create_async_engine(settings.test_database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    admin = PlatformAdmin(id=uuid4(), email="platform@example.com", full_name="Platform Admin", password_hash="hash")
    market_id = uuid4()

    async def override_session():
        async with session_factory() as session:
            yield session

    async def override_admin():
        return admin

    async def failing_send(message):
        raise InvitationEmailError("Invitation email delivery failed.")

    monkeypatch.setattr("app.api.routes.platform.send_owner_invitation_email", failing_send)
    app.dependency_overrides[get_catalog_session] = override_session
    app.dependency_overrides[get_current_platform_admin] = override_admin
    try:
        async with session_factory() as session:
            session.add_all(
                [
                    admin,
                    Market(
                        id=market_id,
                        name="Failed Mail Market",
                        slug=f"failed-mail-{market_id}",
                        language="en",
                        contact_email="owner@example.com",
                        lifecycle_status="trial",
                        onboarding_status="not_started",
                        onboarding_step=1,
                        is_active=True,
                    ),
                ]
            )
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as async_client:
            response = await async_client.post(f"/api/platform/markets/{market_id}/owner-invitation", json={})
            assert response.status_code == 200, response.text
            invitation = response.json()["invitation"]
            assert invitation["status"] == "failed"
            assert invitation["delivery_status"] == "failed"
            assert invitation["send_count"] == 0
            assert invitation["last_sent_at"] is None
            assert invitation["last_send_error"] == "Invitation email delivery failed."

        async with session_factory() as session:
            invitation = await session.scalar(select(MarketInvitation).where(MarketInvitation.market_id == market_id))
            assert invitation is not None
            assert invitation.status == "failed"
            assert invitation.last_sent_at is None
            assert invitation.send_count == 0
            assert invitation.last_send_error == "Invitation email delivery failed."
    finally:
        app.dependency_overrides.pop(get_catalog_session, None)
        app.dependency_overrides.pop(get_current_platform_admin, None)
        await engine.dispose()
