from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.api.deps import get_catalog_session
from app.api.routes.telegram import get_telegram_client
from app.core.config import settings
from app.core.database import Base
from app.main import app
from app.models import Campaign, Market, MarketUser, TelegramAccount, TelegramConversationState, TelegramUpdate, User


class FakeTelegramClient:
    def __init__(self) -> None:
        self.messages: list[tuple[int, str, dict | None]] = []
        self.documents: list[Path] = []
        self.photos: list[Path] = []
        self.answered_callbacks: list[str] = []

    async def send_message(self, chat_id, text, *, reply_markup=None):
        self.messages.append((chat_id, text, reply_markup))

    async def edit_message_text(self, chat_id, message_id, text, *, reply_markup=None):
        self.messages.append((chat_id, text, reply_markup))

    async def answer_callback_query(self, callback_query_id, *, text=None):
        self.answered_callbacks.append(callback_query_id)

    async def send_document(self, chat_id, path, *, caption=None):
        self.documents.append(path)

    async def send_photo(self, chat_id, path, *, caption=None):
        self.photos.append(path)

    async def aclose(self):
        return None


def _message_update(update_id: int, telegram_user_id: int, chat_id: int, text: str, *, chat_type: str = "private"):
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "from": {"id": telegram_user_id, "is_bot": False, "first_name": "Demo", "username": "demo"},
            "chat": {"id": chat_id, "type": chat_type},
            "text": text,
            "date": 1,
        },
    }


def _callback_update(update_id: int, telegram_user_id: int, chat_id: int, data: str):
    return {
        "update_id": update_id,
        "callback_query": {
            "id": f"cb-{update_id}",
            "from": {"id": telegram_user_id, "is_bot": False, "first_name": "Demo"},
            "message": {
                "message_id": update_id,
                "chat": {"id": chat_id, "type": "private"},
                "date": 1,
            },
            "data": data,
        },
    }


@pytest.mark.asyncio
async def test_telegram_webhook_disabled_returns_not_found(monkeypatch) -> None:
    monkeypatch.setattr(settings, "telegram_bot_enabled", False)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post("/api/integrations/telegram/webhook", json=_message_update(1, 10, 10, "/start"))

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_telegram_webhook_rejects_missing_and_wrong_secret(monkeypatch) -> None:
    monkeypatch.setattr(settings, "telegram_bot_enabled", True)
    monkeypatch.setattr(settings, "telegram_webhook_secret", "s" * 40)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        missing = await client.post("/api/integrations/telegram/webhook", json=_message_update(1, 10, 10, "/start"))
        wrong = await client.post(
            "/api/integrations/telegram/webhook",
            headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
            json=_message_update(2, 10, 10, "/start"),
        )

    assert missing.status_code == 401
    assert wrong.status_code == 401


@pytest.mark.asyncio
async def test_telegram_unlinked_user_is_denied_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed Telegram tests skipped.")

    engine, session_factory, fake = await _install_telegram_test_app(monkeypatch)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.post(
                "/api/integrations/telegram/webhook",
                headers={"X-Telegram-Bot-Api-Secret-Token": settings.telegram_webhook_secret},
                json=_message_update(10, 999, 999, "/start"),
            )

        assert response.status_code == 200
        assert "bagli degil" in fake.messages[-1][1]
    finally:
        await _cleanup_telegram_test_app(engine)


@pytest.mark.asyncio
async def test_telegram_start_auto_selects_single_market_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed Telegram tests skipped.")

    engine, session_factory, fake = await _install_telegram_test_app(monkeypatch)
    try:
        telegram_user_id, market_id, _ = await _seed_linked_user(session_factory, role="market_staff")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.post(
                "/api/integrations/telegram/webhook",
                headers={"X-Telegram-Bot-Api-Secret-Token": settings.telegram_webhook_secret},
                json=_message_update(11, telegram_user_id, telegram_user_id, "/start"),
            )

        assert response.status_code == 200
        async with session_factory() as session:
            state = await session.scalar(
                select(TelegramConversationState).where(
                    TelegramConversationState.telegram_user_id == telegram_user_id
                )
            )
        assert state is not None
        assert state.selected_market_id == market_id
        assert "Secili market" in fake.messages[-1][1]
    finally:
        await _cleanup_telegram_test_app(engine)


@pytest.mark.asyncio
async def test_telegram_viewer_cannot_start_new_campaign_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed Telegram tests skipped.")

    engine, session_factory, fake = await _install_telegram_test_app(monkeypatch)
    try:
        telegram_user_id, _, _ = await _seed_linked_user(session_factory, role="viewer")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            headers = {"X-Telegram-Bot-Api-Secret-Token": settings.telegram_webhook_secret}
            await client.post(
                "/api/integrations/telegram/webhook",
                headers=headers,
                json=_message_update(20, telegram_user_id, telegram_user_id, "/start"),
            )
            response = await client.post(
                "/api/integrations/telegram/webhook",
                headers=headers,
                json=_message_update(21, telegram_user_id, telegram_user_id, "/new"),
            )

        assert response.status_code == 200
        assert "market_admin veya market_staff" in fake.messages[-1][1]
    finally:
        await _cleanup_telegram_test_app(engine)


@pytest.mark.asyncio
async def test_telegram_staff_creates_campaign_and_duplicate_update_is_idempotent_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed Telegram tests skipped.")

    engine, session_factory, fake = await _install_telegram_test_app(monkeypatch)
    try:
        telegram_user_id, market_id, _ = await _seed_linked_user(session_factory, role="market_staff")
        headers = {"X-Telegram-Bot-Api-Secret-Token": settings.telegram_webhook_secret}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            await client.post(
                "/api/integrations/telegram/webhook",
                headers=headers,
                json=_message_update(30, telegram_user_id, telegram_user_id, "/start"),
            )
            await client.post(
                "/api/integrations/telegram/webhook",
                headers=headers,
                json=_message_update(31, telegram_user_id, telegram_user_id, "/new"),
            )
            await client.post(
                "/api/integrations/telegram/webhook",
                headers=headers,
                json=_message_update(32, telegram_user_id, telegram_user_id, "Milk 1L - 1.29"),
            )
            created = await client.post(
                "/api/integrations/telegram/webhook",
                headers=headers,
                json=_message_update(33, telegram_user_id, telegram_user_id, "Weekly Deals"),
            )
            duplicate = await client.post(
                "/api/integrations/telegram/webhook",
                headers=headers,
                json=_message_update(33, telegram_user_id, telegram_user_id, "Weekly Deals"),
            )

        assert created.status_code == 200
        assert duplicate.status_code == 200
        async with session_factory() as session:
            count = await session.scalar(select(func.count()).select_from(Campaign).where(Campaign.market_id == market_id))
            update_count = await session.scalar(select(func.count()).select_from(TelegramUpdate).where(TelegramUpdate.update_id == 33))
        assert count == 1
        assert update_count == 1
        assert any("Kampanya olusturuldu" in message for _, message, _ in fake.messages)
    finally:
        await _cleanup_telegram_test_app(engine)


@pytest.mark.asyncio
async def test_telegram_callback_is_answered_and_forged_market_rejected_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed Telegram tests skipped.")

    engine, session_factory, fake = await _install_telegram_test_app(monkeypatch)
    try:
        telegram_user_id, _, _ = await _seed_linked_user(session_factory, role="market_admin")
        forged_market_id = uuid4()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.post(
                "/api/integrations/telegram/webhook",
                headers={"X-Telegram-Bot-Api-Secret-Token": settings.telegram_webhook_secret},
                json=_callback_update(40, telegram_user_id, telegram_user_id, f"market:{forged_market_id}"),
            )

        assert response.status_code == 200
        assert fake.answered_callbacks == ["cb-40"]
        assert "yetkiniz yok" in fake.messages[-1][1]
    finally:
        await _cleanup_telegram_test_app(engine)


async def _install_telegram_test_app(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_enabled", True)
    monkeypatch.setattr(settings, "telegram_webhook_secret", "s" * 40)
    engine = create_async_engine(settings.test_database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    async def override_session():
        async with session_factory() as session:
            yield session

    fake = FakeTelegramClient()

    async def override_client():
        yield fake

    app.dependency_overrides[get_catalog_session] = override_session
    app.dependency_overrides[get_telegram_client] = override_client
    return engine, session_factory, fake


async def _cleanup_telegram_test_app(engine) -> None:
    app.dependency_overrides.pop(get_catalog_session, None)
    app.dependency_overrides.pop(get_telegram_client, None)
    await engine.dispose()


async def _seed_linked_user(session_factory, *, role: str):
    market_id = uuid4()
    user_id = uuid4()
    telegram_user_id = int(str(uuid4().int)[:12])
    async with session_factory() as session:
        user = User(id=user_id, email=f"telegram-{user_id}@example.com", is_active=True)
        market = Market(id=market_id, name=f"Telegram Market {market_id}", slug=f"tg-{market_id}")
        account = TelegramAccount(user=user, telegram_user_id=telegram_user_id, is_active=True)
        membership = MarketUser(market=market, user=user, role=role, is_active=True)
        session.add_all([user, market, account, membership])
        await session.commit()
    return telegram_user_id, market_id, user_id
