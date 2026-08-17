from __future__ import annotations

import asyncio
import copy
import json
from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401
from app.api.deps import get_catalog_session
from app.api.routes.whatsapp_webhook import get_evolution_webhook_client
from app.core.config import settings
from app.core.database import Base
from app.integrations.whatsapp.commands import _normalize_command
from app.main import app
from app.models import (
    ActivityLog,
    Campaign,
    ExportJob,
    Market,
    MarketUser,
    User,
    UserWhatsAppIdentity,
    WhatsAppSession,
)
from app.models.base import utc_now
from app.services.phone import mask_phone

WEBHOOK_URL = "/api/webhooks/evolution/whatsapp"
WEBHOOK_TOKEN_HEADER = "X-Evolution-Webhook-Token"
WEBHOOK_SECRET = "w" * 40
DEFAULT_PHONE = "+33600000012"
DEFAULT_JID = "33600000012@s.whatsapp.net"

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "evolution"
_TEXT_FIXTURE = json.loads((FIXTURE_DIR / "messages_upsert_text.json").read_text())


class FakeEvolutionClient:
    def __init__(self) -> None:
        self.texts: list[tuple[str, str]] = []
        self.media: list[tuple[str, str]] = []

    async def send_text(self, phone_e164: str, text: str) -> str | None:
        self.texts.append((phone_e164, text))
        return "fake-message-id"

    async def send_media(
        self,
        phone_e164: str,
        path,
        *,
        media_type: str,
        mime_type: str,
        file_name: str,
        caption: str | None = None,
    ) -> str | None:
        self.media.append((phone_e164, media_type))
        return "fake-media-id"

    async def fetch_connection_state(self):
        raise NotImplementedError("not exercised by command tests")

    async def aclose(self) -> None:
        return None


def _text_payload(message_id: str, text: str, *, jid: str = DEFAULT_JID) -> dict:
    payload = copy.deepcopy(_TEXT_FIXTURE)
    payload["data"]["key"]["id"] = message_id
    payload["data"]["key"]["remoteJid"] = jid
    payload["data"]["key"]["senderPn"] = jid
    payload["data"]["key"]["remoteJidAlt"] = jid
    payload["data"]["message"]["conversation"] = text
    return payload


async def _post(client: AsyncClient, message_id: str, text: str, *, jid: str = DEFAULT_JID):
    return await client.post(
        WEBHOOK_URL,
        headers={WEBHOOK_TOKEN_HEADER: WEBHOOK_SECRET},
        json=_text_payload(message_id, text, jid=jid),
    )


async def _install_whatsapp_test_app(monkeypatch):
    monkeypatch.setattr(settings, "evolution_whatsapp_enabled", True)
    monkeypatch.setattr(settings, "evolution_webhook_secret", WEBHOOK_SECRET)
    monkeypatch.setattr(settings, "evolution_instance_name", "test-instance")
    monkeypatch.setattr(settings, "leafletpilot_whatsapp_number", "+33600000001")

    engine = create_async_engine(settings.test_database_url, pool_pre_ping=True, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    async def override_session():
        async with session_factory() as session:
            yield session

    fake = FakeEvolutionClient()

    async def override_client():
        yield fake

    app.dependency_overrides[get_catalog_session] = override_session
    app.dependency_overrides[get_evolution_webhook_client] = override_client
    return engine, session_factory, fake


async def _cleanup_whatsapp_test_app(engine) -> None:
    app.dependency_overrides.pop(get_catalog_session, None)
    app.dependency_overrides.pop(get_evolution_webhook_client, None)
    await engine.dispose()


async def _seed_verified_user(
    session_factory,
    *,
    market_count: int = 1,
    role: str = "market_staff",
    phone_e164: str = DEFAULT_PHONE,
    jid: str = DEFAULT_JID,
):
    """Seeds one verified WhatsApp identity with N active market memberships.

    Markets are given strictly increasing `created_at` values so the ordering
    `_active_memberships` relies on (created_at asc) is deterministic instead
    of depending on same-millisecond insert timing.
    """
    user_id = uuid4()
    identity_id = uuid4()
    base_time = utc_now()
    market_ids: list[UUID] = []
    async with session_factory() as session:
        user = User(id=user_id, email=f"wa-{user_id}@example.com", is_active=True)
        identity = UserWhatsAppIdentity(
            id=identity_id,
            user_id=user_id,
            phone_e164=phone_e164,
            whatsapp_jid=jid,
            status="verified",
            verified_source="evolution_whatsapp",
            verified_at=utc_now(),
        )
        session.add_all([user, identity])
        for index in range(market_count):
            market_id = uuid4()
            created_at = base_time + timedelta(seconds=index)
            market = Market(
                id=market_id,
                name=f"WA Market {index + 1} {market_id}",
                slug=f"wa-market-{market_id}",
                lifecycle_status="active",
                is_active=True,
                created_at=created_at,
                updated_at=created_at,
            )
            membership = MarketUser(
                market=market,
                user=user,
                role=role,
                is_active=True,
                created_at=created_at,
                updated_at=created_at,
            )
            session.add_all([market, membership])
            market_ids.append(market_id)
        await session.commit()
    return user_id, identity_id, market_ids


async def _get_session_row(session_factory, identity_id) -> WhatsAppSession | None:
    async with session_factory() as session:
        return await session.scalar(
            select(WhatsAppSession).where(WhatsAppSession.identity_id == identity_id)
        )


async def _set_session_fields(session_factory, identity_id, **fields) -> None:
    async with session_factory() as session:
        row = await session.scalar(
            select(WhatsAppSession).where(WhatsAppSession.identity_id == identity_id)
        )
        for key, value in fields.items():
            setattr(row, key, value)
        await session.commit()


# --- market resolution ------------------------------------------------------


@pytest.mark.asyncio
async def test_whatsapp_single_market_auto_resolves_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    engine, session_factory, fake = await _install_whatsapp_test_app(monkeypatch)
    try:
        _, identity_id, market_ids = await _seed_verified_user(session_factory, market_count=1)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await _post(client, "wc-1", "durum")

        assert response.status_code == 200
        assert not any("numarasını gönderin" in text for _, text in fake.texts)
        session_row = await _get_session_row(session_factory, identity_id)
        assert session_row.active_market_id == market_ids[0]
        assert session_row.state == "idle"
        async with session_factory() as session:
            market = await session.get(Market, market_ids[0])
        assert market.name in fake.texts[-1][1]
    finally:
        await _cleanup_whatsapp_test_app(engine)


@pytest.mark.asyncio
async def test_whatsapp_multi_market_prompts_and_never_guesses_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    engine, session_factory, fake = await _install_whatsapp_test_app(monkeypatch)
    try:
        _, identity_id, market_ids = await _seed_verified_user(session_factory, market_count=3)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await _post(client, "wc-2", "merhaba")

        assert response.status_code == 200
        reply = fake.texts[-1][1]
        assert "1." in reply and "2." in reply and "3." in reply
        session_row = await _get_session_row(session_factory, identity_id)
        assert session_row.state == "awaiting_market"
        assert session_row.active_market_id is None
        assert session_row.market_choice_json is not None
        assert set(session_row.market_choice_json.keys()) == {"1", "2", "3"}
        assert set(session_row.market_choice_json.values()) == {str(m) for m in market_ids}
    finally:
        await _cleanup_whatsapp_test_app(engine)


@pytest.mark.asyncio
async def test_whatsapp_selecting_by_number_works_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    engine, session_factory, fake = await _install_whatsapp_test_app(monkeypatch)
    try:
        _, identity_id, market_ids = await _seed_verified_user(session_factory, market_count=3)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            await _post(client, "wc-3a", "merhaba")
            session_row = await _get_session_row(session_factory, identity_id)
            second_market_id = UUID(session_row.market_choice_json["2"])

            response = await _post(client, "wc-3b", "2")

        assert response.status_code == 200
        session_row = await _get_session_row(session_factory, identity_id)
        assert session_row.active_market_id == second_market_id
        assert session_row.state == "idle"

        async with session_factory() as session:
            log = await session.scalar(
                select(ActivityLog).where(ActivityLog.action == "WHATSAPP_ACTIVE_MARKET_CHANGED")
            )
        assert log is not None
        masked = log.metadata_["sender_phone_masked"]
        assert "*" in masked
        assert DEFAULT_PHONE not in masked
        assert json.dumps(log.metadata_).count(DEFAULT_PHONE) == 0
    finally:
        await _cleanup_whatsapp_test_app(engine)


@pytest.mark.asyncio
async def test_whatsapp_out_of_range_selection_is_rejected_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    engine, session_factory, fake = await _install_whatsapp_test_app(monkeypatch)
    try:
        _, identity_id, _ = await _seed_verified_user(session_factory, market_count=3)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            await _post(client, "wc-4a", "merhaba")
            response = await _post(client, "wc-4b", "99")

        assert response.status_code == 200
        assert "Geçersiz seçim" in fake.texts[-1][1]
        session_row = await _get_session_row(session_factory, identity_id)
        assert session_row.active_market_id is None
    finally:
        await _cleanup_whatsapp_test_app(engine)


@pytest.mark.asyncio
async def test_whatsapp_cannot_select_a_market_with_no_membership_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    engine, session_factory, fake = await _install_whatsapp_test_app(monkeypatch)
    try:
        _, identity_id, _ = await _seed_verified_user(session_factory, market_count=3)
        foreign_market_id = uuid4()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            await _post(client, "wc-5a", "merhaba")

            session_row = await _get_session_row(session_factory, identity_id)
            tampered = dict(session_row.market_choice_json)
            tampered["1"] = str(foreign_market_id)
            await _set_session_fields(session_factory, identity_id, market_choice_json=tampered)

            response = await _post(client, "wc-5b", "1")

        assert response.status_code == 200
        assert "Geçersiz seçim" in fake.texts[-1][1]
        session_row = await _get_session_row(session_factory, identity_id)
        assert session_row.active_market_id != foreign_market_id
        assert session_row.active_market_id is None
    finally:
        await _cleanup_whatsapp_test_app(engine)


@pytest.mark.asyncio
async def test_whatsapp_market_degistir_reprompts_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    engine, session_factory, fake = await _install_whatsapp_test_app(monkeypatch)
    try:
        _, identity_id, market_ids = await _seed_verified_user(session_factory, market_count=3)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            await _post(client, "wc-6a", "merhaba")
            await _post(client, "wc-6b", "1")
            response = await _post(client, "wc-6c", "market değiştir")

        assert response.status_code == 200
        reply = fake.texts[-1][1]
        assert "1." in reply and "2." in reply and "3." in reply
        session_row = await _get_session_row(session_factory, identity_id)
        assert session_row.state == "awaiting_market"
    finally:
        await _cleanup_whatsapp_test_app(engine)


# --- authorization recomputed per message -----------------------------------


@pytest.mark.asyncio
async def test_whatsapp_membership_removed_mid_session_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    engine, session_factory, fake = await _install_whatsapp_test_app(monkeypatch)
    try:
        _, identity_id, market_ids = await _seed_verified_user(session_factory, market_count=1)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            await _post(client, "wc-7a", "durum")

            async with session_factory() as session:
                membership = await session.scalar(
                    select(MarketUser).where(MarketUser.market_id == market_ids[0])
                )
                membership.is_active = False
                await session.commit()

            response = await _post(client, "wc-7b", "durum")

        assert response.status_code == 200
        assert "aktif bir market erişiminiz yok" in fake.texts[-1][1]
        session_row = await _get_session_row(session_factory, identity_id)
        assert session_row.active_market_id is None
    finally:
        await _cleanup_whatsapp_test_app(engine)


@pytest.mark.asyncio
async def test_whatsapp_suspended_and_archived_markets_deny_access_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    for variant in ("suspended_lifecycle", "archived_lifecycle", "inactive_flag"):
        engine, session_factory, fake = await _install_whatsapp_test_app(monkeypatch)
        try:
            _, identity_id, market_ids = await _seed_verified_user(session_factory, market_count=1)

            async with session_factory() as session:
                market = await session.get(Market, market_ids[0])
                if variant == "suspended_lifecycle":
                    market.lifecycle_status = "suspended"
                elif variant == "archived_lifecycle":
                    market.lifecycle_status = "archived"
                else:
                    market.is_active = False
                await session.commit()

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
                response = await _post(client, f"wc-8-{variant}", "durum")

            assert response.status_code == 200
            assert "aktif bir market erişiminiz yok" in fake.texts[-1][1]
            session_row = await _get_session_row(session_factory, identity_id)
            assert session_row.active_market_id is None
            async with session_factory() as session:
                campaign_count = await session.scalar(
                    select(func.count()).select_from(Campaign).where(Campaign.market_id == market_ids[0])
                )
            assert campaign_count == 0
        finally:
            await _cleanup_whatsapp_test_app(engine)


@pytest.mark.asyncio
async def test_whatsapp_viewer_cannot_create_campaign_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    engine, session_factory, fake = await _install_whatsapp_test_app(monkeypatch)
    try:
        _, identity_id, market_ids = await _seed_verified_user(session_factory, market_count=1, role="viewer")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await _post(client, "wc-10", "Süt 1L - 1,29")

        assert response.status_code == 200
        assert "market yöneticisi veya personel" in fake.texts[-1][1]
        async with session_factory() as session:
            campaign_count = await session.scalar(
                select(func.count()).select_from(Campaign).where(Campaign.market_id == market_ids[0])
            )
        assert campaign_count == 0
    finally:
        await _cleanup_whatsapp_test_app(engine)


@pytest.mark.asyncio
async def test_whatsapp_disabled_leafletpilot_user_gets_generic_reply_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    engine, session_factory, fake = await _install_whatsapp_test_app(monkeypatch)
    try:
        user_id, identity_id, _ = await _seed_verified_user(session_factory, market_count=1)
        async with session_factory() as session:
            user = await session.get(User, user_id)
            user.is_active = False
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await _post(client, "wc-11", "durum")

        assert response.status_code == 200
        assert "doğrulanmamış" in fake.texts[-1][1]
        session_row = await _get_session_row(session_factory, identity_id)
        assert session_row is None
    finally:
        await _cleanup_whatsapp_test_app(engine)


@pytest.mark.asyncio
async def test_whatsapp_revoked_identity_gets_generic_reply_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    engine, session_factory, fake = await _install_whatsapp_test_app(monkeypatch)
    try:
        _, identity_id, _ = await _seed_verified_user(session_factory, market_count=1)
        async with session_factory() as session:
            identity = await session.get(UserWhatsAppIdentity, identity_id)
            identity.status = "revoked"
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await _post(client, "wc-12", "durum")

        assert response.status_code == 200
        assert "doğrulanmamış" in fake.texts[-1][1]
        session_row = await _get_session_row(session_factory, identity_id)
        assert session_row is None
    finally:
        await _cleanup_whatsapp_test_app(engine)


# --- simple commands ---------------------------------------------------------


@pytest.mark.asyncio
async def test_whatsapp_help_command_and_diacritic_variant_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    engine, session_factory, fake = await _install_whatsapp_test_app(monkeypatch)
    try:
        await _seed_verified_user(session_factory, market_count=1)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            first = await _post(client, "wc-13a", "yardım")
            second = await _post(client, "wc-13b", "yardim")

        assert first.status_code == 200
        assert second.status_code == 200
        assert "LeafletPilot WhatsApp komutları" in fake.texts[-2][1]
        assert "LeafletPilot WhatsApp komutları" in fake.texts[-1][1]
    finally:
        await _cleanup_whatsapp_test_app(engine)


@pytest.mark.asyncio
async def test_whatsapp_cancel_with_no_active_draft_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    engine, session_factory, fake = await _install_whatsapp_test_app(monkeypatch)
    try:
        _, identity_id, _ = await _seed_verified_user(session_factory, market_count=1)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await _post(client, "wc-14", "iptal")

        assert response.status_code == 200
        assert "iptal edildi" in fake.texts[-1][1]
        session_row = await _get_session_row(session_factory, identity_id)
        assert session_row.state == "idle"
    finally:
        await _cleanup_whatsapp_test_app(engine)


# --- confirmation binding -----------------------------------------------------


@pytest.mark.asyncio
async def test_whatsapp_stale_confirmation_cannot_execute_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    engine, session_factory, fake = await _install_whatsapp_test_app(monkeypatch)
    try:
        _, identity_id, market_ids = await _seed_verified_user(session_factory, market_count=1)
        campaign_id = uuid4()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            # Establish the session row first.
            await _post(client, "wc-15a", "durum")
            await _set_session_fields(
                session_factory,
                identity_id,
                pending_action="final_export",
                pending_action_market_id=market_ids[0],
                pending_action_payload={"campaign_id": str(campaign_id)},
                pending_action_expires_at=utc_now() - timedelta(minutes=1),
            )

            response = await _post(client, "wc-15b", "ONAYLA")

        assert response.status_code == 200
        assert "süresi doldu" in fake.texts[-1][1]
        async with session_factory() as session:
            export_count = await session.scalar(select(func.count()).select_from(ExportJob))
        assert export_count == 0
        session_row = await _get_session_row(session_factory, identity_id)
        assert session_row.pending_action is None
    finally:
        await _cleanup_whatsapp_test_app(engine)


@pytest.mark.asyncio
async def test_whatsapp_confirmation_bound_to_market_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    engine, session_factory, fake = await _install_whatsapp_test_app(monkeypatch)
    try:
        _, identity_id, market_ids = await _seed_verified_user(session_factory, market_count=1)
        foreign_market_id = uuid4()
        campaign_id = uuid4()
        async with session_factory() as session:
            # A real Market row (whatsapp_sessions.pending_action_market_id is
            # FK-constrained) that this user has no membership in.
            session.add(
                Market(
                    id=foreign_market_id,
                    name="Foreign Market",
                    slug=f"wa-foreign-{foreign_market_id}",
                    lifecycle_status="active",
                    is_active=True,
                )
            )
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            await _post(client, "wc-16a", "durum")
            await _set_session_fields(
                session_factory,
                identity_id,
                pending_action="final_export",
                pending_action_market_id=foreign_market_id,
                pending_action_payload={"campaign_id": str(campaign_id)},
                pending_action_expires_at=utc_now() + timedelta(minutes=10),
            )

            response = await _post(client, "wc-16b", "ONAYLA")

        assert response.status_code == 200
        assert "market erişiminiz değişti" in fake.texts[-1][1]
        async with session_factory() as session:
            export_count = await session.scalar(select(func.count()).select_from(ExportJob))
        assert export_count == 0
        session_row = await _get_session_row(session_factory, identity_id)
        assert session_row.pending_action is None
    finally:
        await _cleanup_whatsapp_test_app(engine)


@pytest.mark.asyncio
async def test_whatsapp_confirmation_bound_to_campaign_market_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    engine, session_factory, fake = await _install_whatsapp_test_app(monkeypatch)
    try:
        _, identity_id, market_ids = await _seed_verified_user(session_factory, market_count=1)
        other_market_id = uuid4()
        async with session_factory() as session:
            other_market = Market(
                id=other_market_id,
                name="Other Market",
                slug=f"wa-other-{other_market_id}",
                lifecycle_status="active",
                is_active=True,
            )
            campaign = Campaign(
                market_id=other_market_id,
                title="Belongs to other market",
                channel="whatsapp",
                source_type="text",
            )
            session.add_all([other_market, campaign])
            await session.commit()
            campaign_id = campaign.id

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            await _post(client, "wc-17a", "durum")
            await _set_session_fields(
                session_factory,
                identity_id,
                pending_action="final_export",
                pending_action_market_id=market_ids[0],
                pending_action_payload={"campaign_id": str(campaign_id)},
                pending_action_expires_at=utc_now() + timedelta(minutes=10),
            )

            response = await _post(client, "wc-17b", "ONAYLA")

        assert response.status_code == 200
        assert "bu markete ait değil" in fake.texts[-1][1]
        async with session_factory() as session:
            export_count = await session.scalar(select(func.count()).select_from(ExportJob))
        assert export_count == 0
    finally:
        await _cleanup_whatsapp_test_app(engine)


@pytest.mark.asyncio
async def test_whatsapp_confirm_with_nothing_pending_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    engine, session_factory, fake = await _install_whatsapp_test_app(monkeypatch)
    try:
        _, identity_id, _ = await _seed_verified_user(session_factory, market_count=1)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            await _post(client, "wc-18a", "durum")
            response = await _post(client, "wc-18b", "ONAYLA")

        assert response.status_code == 200
        assert "Onay bekleyen bir işlem yok" in fake.texts[-1][1]
        async with session_factory() as session:
            export_count = await session.scalar(select(func.count()).select_from(ExportJob))
        assert export_count == 0
    finally:
        await _cleanup_whatsapp_test_app(engine)


@pytest.mark.asyncio
async def test_whatsapp_turkish_casing_is_recognised_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    # Pure unit check of the normalizer, pinned alongside the DB-backed
    # behavioural checks below.
    assert _normalize_command("ONAYLA") == "onayla"
    assert _normalize_command("Onayla") == "onayla"
    assert _normalize_command("onayla") == "onayla"
    assert _normalize_command("İPTAL") == "iptal"
    assert _normalize_command("iptal") == "iptal"

    engine, session_factory, fake = await _install_whatsapp_test_app(monkeypatch)
    try:
        _, identity_id, market_ids = await _seed_verified_user(session_factory, market_count=1)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            await _post(client, "wc-19a", "durum")

            for variant, message_id in (("onayla", "wc-19b"), ("ONAYLA", "wc-19c"), ("Onayla", "wc-19d")):
                await _set_session_fields(
                    session_factory,
                    identity_id,
                    pending_action="final_export",
                    pending_action_market_id=market_ids[0],
                    pending_action_payload={"campaign_id": str(uuid4())},
                    pending_action_expires_at=utc_now() - timedelta(minutes=1),
                )
                response = await _post(client, message_id, variant)
                assert response.status_code == 200
                assert "süresi doldu" in fake.texts[-1][1]

            iptal_response = await _post(client, "wc-19e", "İPTAL")
            assert "iptal edildi" in fake.texts[-1][1]
            lower_iptal_response = await _post(client, "wc-19f", "iptal")
            assert "iptal edildi" in fake.texts[-1][1]

        assert iptal_response.status_code == 200
        assert lower_iptal_response.status_code == 200
    finally:
        await _cleanup_whatsapp_test_app(engine)


# --- concurrency ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_whatsapp_concurrent_market_selections_leave_consistent_state_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    engine, session_factory, fake = await _install_whatsapp_test_app(monkeypatch)
    try:
        _, identity_id, market_ids = await _seed_verified_user(session_factory, market_count=2)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            await _post(client, "wc-20a", "merhaba")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client_one:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client_two:
                first, second = await asyncio.gather(
                    _post(client_one, "wc-20b", "1"),
                    _post(client_two, "wc-20c", "2"),
                )

        assert first.status_code == 200
        assert second.status_code == 200
        session_row = await _get_session_row(session_factory, identity_id)
        assert session_row.active_market_id in set(market_ids)
        assert session_row.state == "idle"
        assert session_row.market_choice_json is None
    finally:
        await _cleanup_whatsapp_test_app(engine)
