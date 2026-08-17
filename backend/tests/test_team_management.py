from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.api.deps import get_catalog_session, get_current_user
from app.core.config import settings
from app.core.database import Base
from app.core.security import generate_invitation_token, hash_invitation_token, hash_password
from app.main import app
from app.models import EmailChangeToken, Market, MarketInvitation, MarketUser, PasswordResetToken, User
from app.services.invitation_email import InvitationEmailError


def _override_user(user_id):
    async def override_user():
        return User(id=user_id, email=f"team-{user_id}@example.com", is_active=True)

    return override_user


async def _make_market_with_admin(session, market_id, admin_id, *, extra_members=None):
    market = Market(id=market_id, name=f"Team Test Market {market_id}", slug=f"team-{market_id}", language="tr")
    admin_user = User(id=admin_id, email=f"admin-{admin_id}@example.com", is_active=True)
    session.add_all([market, admin_user])
    await session.flush()
    session.add(MarketUser(market_id=market_id, user_id=admin_id, role="market_admin", is_active=True))
    for member_id, role in extra_members or []:
        session.add(User(id=member_id, email=f"member-{member_id}@example.com", is_active=True))
        session.add(MarketUser(market_id=market_id, user_id=member_id, role=role, is_active=True))
    await session.commit()


@pytest.mark.asyncio
async def test_invitation_delivery_duplicate_resend_revoke_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed team tests skipped.")

    engine = create_async_engine(settings.test_database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def override_session():
        async with session_factory() as session:
            yield session

    market_id = uuid4()
    admin_id = uuid4()
    app.dependency_overrides[get_catalog_session] = override_session
    app.dependency_overrides[get_current_user] = _override_user(admin_id)
    try:
        async with session_factory() as session:
            await _make_market_with_admin(session, market_id, admin_id)

        invited_email = f"invitee-{market_id}@example.com"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as async_client:
            headers = {"X-Market-Id": str(market_id)}

            # Default test settings use invitation_email_delivery="disabled" — a deterministic,
            # SMTP-free outcome: the invitation is created but flagged manual_delivery_required,
            # and the record itself is never lost.
            created = await async_client.post(
                "/api/market-invitations",
                headers=headers,
                json={"email": invited_email, "role": "market_staff"},
            )
            assert created.status_code == 201, created.text
            invitation = created.json()
            assert invitation["status"] == "manual_delivery_required"
            assert invitation["accept_url"]

            # A second create for the same active email+market must not create a duplicate row.
            duplicate = await async_client.post(
                "/api/market-invitations",
                headers=headers,
                json={"email": invited_email, "role": "market_staff"},
            )
            assert duplicate.status_code == 409

            listed = await async_client.get("/api/market-invitations", headers=headers)
            assert listed.status_code == 200
            assert len([item for item in listed.json() if item["email"] == invited_email]) == 1

            # Resend mints a fresh token for the SAME row and keeps it retrievable.
            resend = await async_client.post(
                f"/api/market-invitations/{invitation['id']}/resend", headers=headers
            )
            assert resend.status_code == 200, resend.text
            assert resend.json()["id"] == invitation["id"]
            assert resend.json()["invite_token"] != invitation["invite_token"]

            # Revoke frees the email+market slot up for a brand new invitation.
            revoke = await async_client.post(
                f"/api/market-invitations/{invitation['id']}/revoke", headers=headers
            )
            assert revoke.status_code == 200
            assert revoke.json()["status"] == "revoked"

            reinvite = await async_client.post(
                "/api/market-invitations",
                headers=headers,
                json={"email": invited_email, "role": "market_staff"},
            )
            assert reinvite.status_code == 201

        async with session_factory() as session:
            rows = (
                await session.scalars(
                    select(MarketInvitation).where(MarketInvitation.email == invited_email)
                )
            ).all()
            assert len(rows) == 2
            assert sorted(row.status for row in rows) == ["manual_delivery_required", "revoked"]
    finally:
        app.dependency_overrides.pop(get_catalog_session, None)
        app.dependency_overrides.pop(get_current_user, None)
        await engine.dispose()


@pytest.mark.asyncio
async def test_invitation_send_success_and_failure_never_loses_the_record_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed team tests skipped.")

    engine = create_async_engine(settings.test_database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def override_session():
        async with session_factory() as session:
            yield session

    market_id = uuid4()
    admin_id = uuid4()
    app.dependency_overrides[get_catalog_session] = override_session
    app.dependency_overrides[get_current_user] = _override_user(admin_id)
    try:
        async with session_factory() as session:
            await _make_market_with_admin(session, market_id, admin_id)

        async def fake_send(message):
            return None

        monkeypatch.setattr("app.api.routes.team.send_owner_invitation_email", fake_send)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as async_client:
            headers = {"X-Market-Id": str(market_id)}
            success_email = f"sent-{market_id}@example.com"
            sent = await async_client.post(
                "/api/market-invitations", headers=headers, json={"email": success_email, "role": "market_staff"}
            )
            assert sent.status_code == 201
            assert sent.json()["status"] == "sent"

        async def failing_send(message):
            raise InvitationEmailError("smtp exploded")

        monkeypatch.setattr("app.api.routes.team.send_owner_invitation_email", failing_send)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as async_client:
            headers = {"X-Market-Id": str(market_id)}
            failure_email = f"failed-{market_id}@example.com"
            failed = await async_client.post(
                "/api/market-invitations", headers=headers, json={"email": failure_email, "role": "market_staff"}
            )
            assert failed.status_code == 201
            assert failed.json()["status"] == "failed"

        async with session_factory() as session:
            failed_row = await session.scalar(
                select(MarketInvitation).where(MarketInvitation.email == failure_email)
            )
            assert failed_row is not None
            assert failed_row.status == "failed"
    finally:
        app.dependency_overrides.pop(get_catalog_session, None)
        app.dependency_overrides.pop(get_current_user, None)
        await engine.dispose()


@pytest.mark.asyncio
async def test_role_change_last_admin_cross_market_and_self_escalation_when_test_database_url_is_configured() -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed team tests skipped.")

    engine = create_async_engine(settings.test_database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def override_session():
        async with session_factory() as session:
            yield session

    market_id = uuid4()
    other_market_id = uuid4()
    admin_id = uuid4()
    staff_id = uuid4()
    other_admin_id = uuid4()
    app.dependency_overrides[get_catalog_session] = override_session
    try:
        async with session_factory() as session:
            await _make_market_with_admin(session, market_id, admin_id, extra_members=[(staff_id, "market_staff")])
            await _make_market_with_admin(session, other_market_id, other_admin_id)
            admin_membership_id = (
                await session.scalar(select(MarketUser).where(MarketUser.market_id == market_id, MarketUser.user_id == admin_id))
            ).id
            staff_membership_id = (
                await session.scalar(select(MarketUser).where(MarketUser.market_id == market_id, MarketUser.user_id == staff_id))
            ).id
            other_admin_membership_id = (
                await session.scalar(select(MarketUser).where(MarketUser.market_id == other_market_id, MarketUser.user_id == other_admin_id))
            ).id

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as async_client:
            # Last-admin protection: the market's sole admin cannot be demoted, even by itself.
            app.dependency_overrides[get_current_user] = _override_user(admin_id)
            last_admin = await async_client.patch(
                f"/api/market-members/{admin_membership_id}",
                headers={"X-Market-Id": str(market_id)},
                json={"role": "market_staff"},
            )
            assert last_admin.status_code == 409

            # Cross-market rejection: an admin of market A cannot act on market B's membership,
            # even though the actor is still a valid admin of market A at this point.
            cross_market = await async_client.patch(
                f"/api/market-members/{other_admin_membership_id}",
                headers={"X-Market-Id": str(market_id)},
                json={"role": "market_staff"},
            )
            assert cross_market.status_code == 404

            # Promoting the staff member first must free up the admin to be demoted afterwards.
            promote = await async_client.patch(
                f"/api/market-members/{staff_membership_id}",
                headers={"X-Market-Id": str(market_id)},
                json={"role": "market_admin"},
            )
            assert promote.status_code == 200
            now_demotable = await async_client.patch(
                f"/api/market-members/{admin_membership_id}",
                headers={"X-Market-Id": str(market_id)},
                json={"role": "market_staff"},
            )
            assert now_demotable.status_code == 200

            # Self-escalation: a non-admin cannot reach this admin-only endpoint at all.
            app.dependency_overrides[get_current_user] = _override_user(admin_id)  # now market_staff after demotion
            self_escalate = await async_client.patch(
                f"/api/market-members/{admin_membership_id}",
                headers={"X-Market-Id": str(market_id)},
                json={"role": "market_admin"},
            )
            assert self_escalate.status_code == 403
    finally:
        app.dependency_overrides.pop(get_catalog_session, None)
        app.dependency_overrides.pop(get_current_user, None)
        await engine.dispose()


@pytest.mark.asyncio
async def test_password_reset_flow_never_exposes_password_one_time_use_and_expiry_when_test_database_url_is_configured() -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed team tests skipped.")

    engine = create_async_engine(settings.test_database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def override_session():
        async with session_factory() as session:
            yield session

    market_id = uuid4()
    admin_id = uuid4()
    member_id = uuid4()
    old_password = "OldPass123!"
    new_password = "NewPass456!"
    member_email = f"reset-target-{member_id}@example.com"

    app.dependency_overrides[get_catalog_session] = override_session
    try:
        async with session_factory() as session:
            market = Market(id=market_id, name=f"Reset Market {market_id}", slug=f"reset-{market_id}", language="tr")
            admin_user = User(id=admin_id, email=f"reset-admin-{admin_id}@example.com", is_active=True)
            member_user = User(id=member_id, email=member_email, password_hash=hash_password(old_password), is_active=True)
            session.add_all([market, admin_user, member_user])
            await session.flush()
            session.add_all(
                [
                    MarketUser(market_id=market_id, user_id=admin_id, role="market_admin", is_active=True),
                    MarketUser(market_id=market_id, user_id=member_id, role="market_staff", is_active=True),
                ]
            )
            await session.commit()
            member_membership_id = (
                await session.scalar(select(MarketUser).where(MarketUser.market_id == market_id, MarketUser.user_id == member_id))
            ).id

        app.dependency_overrides[get_current_user] = _override_user(admin_id)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as async_client:
            requested = await async_client.post(
                f"/api/market-members/{member_membership_id}/password-reset",
                headers={"X-Market-Id": str(market_id)},
            )
            assert requested.status_code == 200
            # The response is delivery-status only — no password, hash, or token is ever returned.
            assert set(requested.json().keys()) == {"delivery"}

        async with session_factory() as session:
            token_row = await session.scalar(
                select(PasswordResetToken).where(PasswordResetToken.user_id == member_id)
            )
            assert token_row is not None
            assert token_row.used_at is None

        app.dependency_overrides.pop(get_current_user, None)
        raw_token = "known-reset-token-" + uuid4().hex
        async with session_factory() as session:
            token_row = await session.scalar(select(PasswordResetToken).where(PasswordResetToken.user_id == member_id))
            token_row.token_hash = hash_invitation_token(raw_token)
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as async_client:
            confirmed = await async_client.post(
                "/api/auth/password-reset/confirm", json={"token": raw_token, "password": new_password}
            )
            assert confirmed.status_code == 200
            assert confirmed.json() == {"status": "ok"}

            # One-time use: replaying the same token must fail, not silently succeed again.
            replay = await async_client.post(
                "/api/auth/password-reset/confirm", json={"token": raw_token, "password": "AnotherPass789!"}
            )
            assert replay.status_code == 409

            # The old password must no longer work; the new one must.
            old_login = await async_client.post("/api/auth/login", json={"email": member_email, "password": old_password})
            assert old_login.status_code == 401
            new_login = await async_client.post("/api/auth/login", json={"email": member_email, "password": new_password})
            assert new_login.status_code == 200

        # An expired (but otherwise valid, unused) token must be inert, not usable.
        async with session_factory() as session:
            expired_raw = generate_invitation_token()
            session.add(
                PasswordResetToken(
                    user_id=member_id,
                    token_hash=hash_invitation_token(expired_raw),
                    expires_at=datetime.now(UTC) - timedelta(minutes=1),
                )
            )
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as async_client:
            expired_attempt = await async_client.post(
                "/api/auth/password-reset/confirm", json={"token": expired_raw, "password": "YetAnother12!"}
            )
            assert expired_attempt.status_code == 410
    finally:
        app.dependency_overrides.pop(get_catalog_session, None)
        app.dependency_overrides.pop(get_current_user, None)
        await engine.dispose()


@pytest.mark.asyncio
async def test_email_change_verify_first_hard_requirements_when_test_database_url_is_configured(monkeypatch) -> None:
    """Regression for approved-plan adjustment #8's four hard requirements: old email stays
    active until verified; expired/replayed tokens are inert; uniqueness is re-checked at
    confirm time (not just request time); a pending change never disturbs the current login."""
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed team tests skipped.")
    # This test makes several distinct /auth/email-change/confirm calls from the same test
    # client "IP" — raise the throttle ceiling so the confirm-attempt limiter (a genuine
    # anti-abuse control, not something this test is exercising) doesn't interfere.
    monkeypatch.setattr(settings, "public_signup_throttle_limit", 50)

    engine = create_async_engine(settings.test_database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def override_session():
        async with session_factory() as session:
            yield session

    market_id = uuid4()
    admin_id = uuid4()
    member_id = uuid4()
    password = "MemberPass123!"
    old_email = f"old-{member_id}@example.com"
    new_email = f"new-{member_id}@example.com"

    app.dependency_overrides[get_catalog_session] = override_session
    try:
        async with session_factory() as session:
            market = Market(id=market_id, name=f"Email Change Market {market_id}", slug=f"ec-{market_id}", language="tr")
            admin_user = User(id=admin_id, email=f"ec-admin-{admin_id}@example.com", is_active=True)
            member_user = User(id=member_id, email=old_email, password_hash=hash_password(password), is_active=True)
            session.add_all([market, admin_user, member_user])
            await session.flush()
            session.add_all(
                [
                    MarketUser(market_id=market_id, user_id=admin_id, role="market_admin", is_active=True),
                    MarketUser(market_id=market_id, user_id=member_id, role="market_staff", is_active=True),
                ]
            )
            await session.commit()
            member_membership_id = (
                await session.scalar(select(MarketUser).where(MarketUser.market_id == market_id, MarketUser.user_id == member_id))
            ).id

        app.dependency_overrides[get_current_user] = _override_user(admin_id)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as async_client:
            requested = await async_client.post(
                f"/api/market-members/{member_membership_id}/email-change",
                headers={"X-Market-Id": str(market_id)},
                json={"email": new_email},
            )
            assert requested.status_code == 200

        # Requirement 1 + 4: creating the pending change must not touch User.email or disturb login.
        async with session_factory() as session:
            member = await session.get(User, member_id)
            assert member.email == old_email

        app.dependency_overrides.pop(get_current_user, None)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as async_client:
            old_login_still_works = await async_client.post(
                "/api/auth/login", json={"email": old_email, "password": password}
            )
            assert old_login_still_works.status_code == 200
            new_email_not_yet_valid = await async_client.post(
                "/api/auth/login", json={"email": new_email, "password": password}
            )
            assert new_email_not_yet_valid.status_code == 401

        # Requirement 3: uniqueness is re-checked at confirm time — another account claims the
        # target address after the request but before confirmation.
        async with session_factory() as session:
            conflicting_user = User(email=new_email, password_hash=hash_password("Whoever123!"), is_active=True)
            session.add(conflicting_user)
            await session.commit()

        raw_token = "known-email-change-token-" + uuid4().hex
        async with session_factory() as session:
            token_row = await session.scalar(select(EmailChangeToken).where(EmailChangeToken.user_id == member_id))
            token_row.token_hash = hash_invitation_token(raw_token)
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as async_client:
            conflicted_confirm = await async_client.post(
                "/api/auth/email-change/confirm", json={"token": raw_token}
            )
            assert conflicted_confirm.status_code == 409

        async with session_factory() as session:
            member = await session.get(User, member_id)
            assert member.email == old_email  # still untouched despite the conflict attempt

        # Clear the conflicting user and retry — now confirmation should succeed.
        async with session_factory() as session:
            await session.execute(User.__table__.delete().where(User.email == new_email, User.id != member_id))
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as async_client:
            confirmed = await async_client.post("/api/auth/email-change/confirm", json={"token": raw_token})
            assert confirmed.status_code == 200
            assert confirmed.json()["email"] == new_email

            # Requirement 2: replaying the now-used token must be inert.
            replay = await async_client.post("/api/auth/email-change/confirm", json={"token": raw_token})
            assert replay.status_code == 409

            old_email_no_longer_logs_in = await async_client.post(
                "/api/auth/login", json={"email": old_email, "password": password}
            )
            assert old_email_no_longer_logs_in.status_code == 401
            new_email_now_logs_in = await async_client.post(
                "/api/auth/login", json={"email": new_email, "password": password}
            )
            assert new_email_now_logs_in.status_code == 200

        # Requirement 2 (expiry half): an expired, unused token must also be inert.
        async with session_factory() as session:
            expired_raw = generate_invitation_token()
            session.add(
                EmailChangeToken(
                    user_id=member_id,
                    new_email=f"unused-{member_id}@example.com",
                    token_hash=hash_invitation_token(expired_raw),
                    expires_at=datetime.now(UTC) - timedelta(minutes=1),
                )
            )
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as async_client:
            expired_attempt = await async_client.post("/api/auth/email-change/confirm", json={"token": expired_raw})
            assert expired_attempt.status_code == 410
    finally:
        app.dependency_overrides.pop(get_catalog_session, None)
        app.dependency_overrides.pop(get_current_user, None)
        await engine.dispose()
