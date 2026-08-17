from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.api.deps import get_catalog_session, get_current_user
from app.core.config import settings
from app.core.database import Base
from app.main import app
from app.models import Market, MarketUser, TelegramAccount, User


def _override_user(user_id):
    async def override_user():
        return User(id=user_id, email=f"telegram-status-{user_id}@example.com", is_active=True)

    return override_user


@pytest.mark.asyncio
async def test_telegram_status_reports_connected_and_disconnected_when_test_database_url_is_configured() -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed telegram status tests skipped.")

    engine = create_async_engine(settings.test_database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def override_session():
        async with session_factory() as session:
            yield session

    connected_market_id = uuid4()
    disconnected_market_id = uuid4()
    connected_user_id = uuid4()
    disconnected_user_id = uuid4()

    app.dependency_overrides[get_catalog_session] = override_session
    try:
        async with session_factory() as session:
            connected_market = Market(id=connected_market_id, name=f"Connected Market {connected_market_id}", slug=f"tg-connected-{connected_market_id}")
            disconnected_market = Market(id=disconnected_market_id, name=f"Disconnected Market {disconnected_market_id}", slug=f"tg-disconnected-{disconnected_market_id}")
            connected_user = User(id=connected_user_id, email=f"tg-connected-{connected_user_id}@example.com", is_active=True)
            disconnected_user = User(id=disconnected_user_id, email=f"tg-disconnected-{disconnected_user_id}@example.com", is_active=True)
            session.add_all([connected_market, disconnected_market, connected_user, disconnected_user])
            await session.flush()
            session.add_all(
                [
                    MarketUser(market_id=connected_market_id, user_id=connected_user_id, role="market_admin", is_active=True),
                    MarketUser(market_id=disconnected_market_id, user_id=disconnected_user_id, role="market_admin", is_active=True),
                    TelegramAccount(
                        user_id=connected_user_id,
                        telegram_user_id=123456789,
                        username="market_owner",
                        is_active=True,
                    ),
                ]
            )
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as async_client:
            app.dependency_overrides[get_current_user] = _override_user(connected_user_id)
            connected_response = await async_client.get(
                "/api/integrations/telegram/status",
                headers={"X-Market-Id": str(connected_market_id)},
            )
            assert connected_response.status_code == 200
            connected_body = connected_response.json()
            assert connected_body["connected"] is True
            assert connected_body["connected_member_count"] == 1
            assert connected_body["username"] == "market_owner"

            app.dependency_overrides[get_current_user] = _override_user(disconnected_user_id)
            disconnected_response = await async_client.get(
                "/api/integrations/telegram/status",
                headers={"X-Market-Id": str(disconnected_market_id)},
            )
            assert disconnected_response.status_code == 200
            disconnected_body = disconnected_response.json()
            assert disconnected_body["connected"] is False
            assert disconnected_body["connected_member_count"] == 0
            assert disconnected_body["username"] is None
    finally:
        app.dependency_overrides.pop(get_catalog_session, None)
        app.dependency_overrides.pop(get_current_user, None)
        await engine.dispose()
