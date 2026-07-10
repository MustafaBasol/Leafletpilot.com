from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.api.deps import get_catalog_session
from app.api.deps import require_market_member
from app.core.config import settings
from app.core.database import Base
from app.core.security import hash_invitation_token, hash_password
from app.main import app
from app.models import Market, MarketInvitation, MarketUser, User


class FakeMembershipSession:
    def __init__(self, membership):
        self.membership = membership

    async def scalar(self, statement):
        return self.membership


@pytest.mark.asyncio
async def test_require_market_member_accepts_active_membership() -> None:
    market_id = uuid4()
    user_id = uuid4()
    user = User(id=user_id, email=f"member-{user_id}@example.com", is_active=True)
    market = Market(id=market_id, name="Member Market", slug=f"member-{market_id}", is_active=True)
    membership = MarketUser(market_id=market_id, user_id=user_id, role="market_admin", is_active=True)
    membership.market = market

    resolved_market_id = await require_market_member(
        x_market_id=market_id,
        current_user=user,
        session=FakeMembershipSession(membership),
    )

    assert resolved_market_id == market_id


@pytest.mark.asyncio
async def test_require_market_member_rejects_cross_market_access() -> None:
    user_id = uuid4()
    user = User(id=user_id, email=f"member-{user_id}@example.com", is_active=True)

    with pytest.raises(HTTPException) as exc_info:
        await require_market_member(
            x_market_id=uuid4(),
            current_user=user,
            session=FakeMembershipSession(None),
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_auth_flow_and_market_membership_when_test_database_url_is_configured() -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed auth tests skipped.")

    engine = create_async_engine(settings.test_database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def override_session():
        async with session_factory() as session:
            yield session

    market_id = uuid4()
    other_market_id = uuid4()
    email = "demo@leafletpilot.com"
    password = "demo1234"

    app.dependency_overrides[get_catalog_session] = override_session
    try:
        async with session_factory() as session:
            user = await session.scalar(select(User).where(User.email == email))
            if user is None:
                user = User(email=email, full_name="Demo Admin", password_hash=hash_password(password), is_active=True)
                session.add(user)
                await session.flush()
            else:
                user.full_name = "Demo Admin"
                user.password_hash = hash_password(password)
                user.is_active = True

            market = Market(id=market_id, name=f"Auth Market {market_id}", slug=f"auth-{market_id}")
            other_market = Market(
                id=other_market_id,
                name=f"Other Auth Market {other_market_id}",
                slug=f"other-auth-{other_market_id}",
            )
            session.add_all([market, other_market])
            await session.flush()
            session.add(MarketUser(market_id=market_id, user_id=user.id, role="market_admin", is_active=True))
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as async_client:
            bad_login = await async_client.post("/api/auth/login", json={"email": email, "password": "wrong"})
            assert bad_login.status_code == 401

            login = await async_client.post("/api/auth/login", json={"email": email, "password": password})
            assert login.status_code == 200
            login_body = login.json()
            assert login_body["token_type"] == "bearer"
            assert login_body["access_token"]
            assert login_body["user"]["email"] == email
            assert any(market["id"] == str(market_id) for market in login_body["markets"])

            missing_me = await async_client.get("/api/auth/me")
            assert missing_me.status_code == 401

            auth_headers = {"Authorization": f"Bearer {login_body['access_token']}"}
            me = await async_client.get("/api/auth/me", headers=auth_headers)
            assert me.status_code == 200
            assert me.json()["user"]["email"] == email

            accepted = await async_client.get(
                "/api/catalog/brands",
                headers={**auth_headers, "X-Market-Id": str(market_id)},
            )
            assert accepted.status_code == 200

            forbidden = await async_client.get(
                "/api/catalog/brands",
                headers={**auth_headers, "X-Market-Id": str(other_market_id)},
            )
            assert forbidden.status_code == 403
    finally:
        app.dependency_overrides.pop(get_catalog_session, None)
        await engine.dispose()


@pytest.mark.asyncio
async def test_public_invitation_accept_creates_user_and_password_can_login(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed auth tests skipped.")
    monkeypatch.setattr(settings, "public_signup_throttle_limit", 20)

    engine = create_async_engine(settings.test_database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    async def override_session():
        async with session_factory() as session:
            yield session

    market_id = uuid4()
    admin_email = f"invite-admin-{market_id}@example.com"
    invited_email = f"invite-user-{market_id}@example.com"
    other_invited_email = f"invite-other-{market_id}@example.com"
    admin_password = "demo1234"
    invited_password = "InvitePass123!"

    app.dependency_overrides[get_catalog_session] = override_session
    try:
        async with session_factory() as session:
            admin = User(
                email=admin_email,
                full_name="Invite Admin",
                password_hash=hash_password(admin_password),
                is_active=True,
            )
            market = Market(
                id=market_id,
                name=f"Invite Market {market_id}",
                slug=f"invite-{market_id}",
                onboarding_status="not_started",
                onboarding_step=1,
            )
            session.add_all([admin, market])
            await session.flush()
            session.add(MarketUser(market_id=market_id, user_id=admin.id, role="market_admin", is_active=True))
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as async_client:
            login = await async_client.post("/api/auth/login", json={"email": admin_email, "password": admin_password})
            assert login.status_code == 200
            admin_headers = {
                "Authorization": f"Bearer {login.json()['access_token']}",
                "X-Market-Id": str(market_id),
            }

            invite_response = await async_client.post(
                "/api/market-invitations",
                headers=admin_headers,
                json={"email": invited_email, "role": "market_admin"},
            )
            assert invite_response.status_code == 201
            invite = invite_response.json()

            accept_response = await async_client.post(
                "/api/auth/accept-invitation",
                json={"token": invite["invite_token"], "full_name": "Invited User", "password": invited_password},
            )
            assert accept_response.status_code == 200
            accept_body = accept_response.json()
            assert accept_body["token_type"] == "bearer"
            assert accept_body["access_token"]
            assert "platform" not in accept_body
            accepted_market = next(market for market in accept_body["markets"] if market["id"] == str(market_id))
            assert accepted_market["role"] == "market_admin"
            assert accepted_market["lifecycle_status"] == "active"
            assert accepted_market["onboarding_status"] == "in_progress"
            assert accepted_market["onboarding_step"] == 1
            assert accepted_market["role"] == "market_admin" and accepted_market["onboarding_status"] != "completed"

            invited_headers = {
                "Authorization": f"Bearer {accept_body['access_token']}",
                "X-Market-Id": str(market_id),
            }
            me = await async_client.get("/api/auth/me", headers={"Authorization": invited_headers["Authorization"]})
            assert me.status_code == 200
            assert me.json()["user"]["email"] == invited_email
            onboarding = await async_client.get("/api/onboarding", headers=invited_headers)
            assert onboarding.status_code == 200
            profile_payload = {
                "display_name": "Invite Market Updated",
                "legal_name": "Invite Market Legal",
                "country_code": "fr",
                "city": "Paris",
                "language": "tr",
                "currency": "eur",
                "timezone": "Europe/Paris",
                "contact_email": invited_email,
                "contact_phone": "+33123456789",
            }
            valid_profile = await async_client.patch(
                "/api/onboarding/profile",
                headers=invited_headers,
                json=profile_payload,
            )
            assert valid_profile.status_code == 200, valid_profile.text
            assert valid_profile.json()["timezone"] == "Europe/Paris"
            invalid_profile = await async_client.patch(
                "/api/onboarding/profile",
                headers=invited_headers,
                json={**profile_payload, "timezone": "Not/AZone"},
            )
            assert invalid_profile.status_code == 422
            unchanged = await async_client.get("/api/onboarding", headers=invited_headers)
            assert unchanged.status_code == 200
            assert unchanged.json()["timezone"] == "Europe/Paris"

            invited_login = await async_client.post(
                "/api/auth/login",
                json={"email": invited_email, "password": invited_password},
            )
            assert invited_login.status_code == 200
            assert invited_login.json()["user"]["email"] == invited_email

            reuse_response = await async_client.post(
                "/api/auth/accept-invitation",
                json={"token": invite["invite_token"], "full_name": "Invited User", "password": invited_password},
            )
            assert reuse_response.status_code == 409
            assert reuse_response.json()["detail"]["code"] == "invitation_accepted"
            accepted_preview = await async_client.post("/api/auth/invitation-preview", json={"token": invite["invite_token"]})
            assert accepted_preview.status_code == 200
            assert accepted_preview.json()["status"] == "accepted"

            other_invite_response = await async_client.post(
                "/api/market-invitations",
                headers=admin_headers,
                json={"email": other_invited_email, "role": "market_staff"},
            )
            assert other_invite_response.status_code == 201
            mismatch = await async_client.post(
                "/api/auth/accept-invitation-authenticated",
                headers={"Authorization": admin_headers["Authorization"]},
                json={"token": other_invite_response.json()["invite_token"]},
            )
            assert mismatch.status_code == 403
            assert mismatch.json()["detail"]["code"] == "invitation_email_mismatch"

            admin_invite_response = await async_client.post(
                "/api/market-invitations",
                headers=admin_headers,
                json={"email": admin_email, "role": "market_admin"},
            )
            assert admin_invite_response.status_code == 201
            admin_accept = await async_client.post(
                "/api/auth/accept-invitation-authenticated",
                headers={"Authorization": admin_headers["Authorization"]},
                json={"token": admin_invite_response.json()["invite_token"]},
            )
            assert admin_accept.status_code == 200
            assert admin_accept.json()["access_token"]
            assert any(market["id"] == str(market_id) for market in admin_accept.json()["markets"])

            expired_token = "expired-" + uuid4().hex
            revoked_token = "revoked-" + uuid4().hex
            failed_token = "failed-" + uuid4().hex
            async with session_factory() as session:
                session.add_all(
                    [
                        MarketInvitation(
                            market_id=market_id,
                            email=f"expired-{market_id}@example.com",
                            role="viewer",
                            token_hash=hash_invitation_token(expired_token),
                            status="pending",
                            expires_at=datetime.now(UTC) - timedelta(minutes=1),
                            created_by_user_id=None,
                        ),
                        MarketInvitation(
                            market_id=market_id,
                            email=f"revoked-{market_id}@example.com",
                            role="viewer",
                            token_hash=hash_invitation_token(revoked_token),
                            status="revoked",
                            expires_at=datetime.now(UTC) + timedelta(days=1),
                            created_by_user_id=None,
                            revoked_at=datetime.now(UTC),
                        ),
                        MarketInvitation(
                            market_id=market_id,
                            email=f"failed-{market_id}@example.com",
                            role="viewer",
                            token_hash=hash_invitation_token(failed_token),
                            status="failed",
                            expires_at=datetime.now(UTC) + timedelta(days=1),
                            created_by_user_id=None,
                        ),
                    ]
                )
                await session.commit()
            invalid_preview = await async_client.post("/api/auth/invitation-preview", json={"token": "missing-" + uuid4().hex})
            expired_preview = await async_client.post("/api/auth/invitation-preview", json={"token": expired_token})
            revoked_preview = await async_client.post("/api/auth/invitation-preview", json={"token": revoked_token})
            failed_preview = await async_client.post("/api/auth/invitation-preview", json={"token": failed_token})
            assert invalid_preview.status_code == 200
            assert invalid_preview.json()["status"] == "invalid"
            assert expired_preview.status_code == 200
            assert expired_preview.json()["status"] == "expired"
            assert revoked_preview.status_code == 200
            assert revoked_preview.json()["status"] == "revoked"
            assert failed_preview.status_code == 200
            assert failed_preview.json()["status"] == "failed"
            expired = await async_client.post(
                "/api/auth/accept-invitation",
                json={"token": expired_token, "full_name": "Expired User", "password": invited_password},
            )
            revoked = await async_client.post(
                "/api/auth/accept-invitation",
                json={"token": revoked_token, "full_name": "Revoked User", "password": invited_password},
            )
            failed = await async_client.post(
                "/api/auth/accept-invitation",
                json={"token": failed_token, "full_name": "Failed User", "password": invited_password},
            )
            assert expired.status_code == 410
            assert expired.json()["detail"]["code"] == "invitation_expired"
            assert revoked.status_code == 409
            assert revoked.json()["detail"]["code"] == "invitation_revoked"
            assert failed.status_code == 409
            assert failed.json()["detail"]["code"] == "invitation_delivery_failed"

        async with session_factory() as session:
            created_user = await session.scalar(select(User).where(User.email == invited_email))
            assert created_user is not None
            assert created_user.is_active is True
            membership = await session.scalar(
                select(MarketUser).where(MarketUser.market_id == market_id, MarketUser.user_id == created_user.id)
            )
            assert membership is not None
            assert membership.role == "market_admin"
            accepted_invitation = await session.scalar(
                select(MarketInvitation).where(MarketInvitation.email == invited_email)
            )
            assert accepted_invitation is not None
            assert accepted_invitation.status == "accepted"
            assert accepted_invitation.accepted_by_user_id == created_user.id
    finally:
        app.dependency_overrides.pop(get_catalog_session, None)
        await engine.dispose()
