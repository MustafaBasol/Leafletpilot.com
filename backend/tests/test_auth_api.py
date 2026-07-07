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
from app.core.security import hash_password
from app.main import app
from app.models import Market, MarketUser, User


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
