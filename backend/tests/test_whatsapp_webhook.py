from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

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
from app.core.security import hash_whatsapp_verification_code
from app.integrations.whatsapp.client import EvolutionClientError, EvolutionConnectionState
from app.integrations.whatsapp.schemas import event_key, normalize_evolution_event
from app.integrations.whatsapp.service import (
    INVALID_CODE_REPLY,
    UNVERIFIED_REPLY,
    extract_verification_code,
)
from app.main import app
from app.models import (
    Market,
    MarketUser,
    User,
    UserWhatsAppIdentity,
    WhatsAppIntegrationState,
    WhatsAppVerification,
    WhatsAppWebhookEvent,
)
from app.models.base import utc_now

WEBHOOK_URL = "/api/webhooks/evolution/whatsapp"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "evolution"


class FakeEvolutionClient:
    def __init__(self) -> None:
        self.texts: list[tuple[str, str]] = []
        self.media: list[tuple[str, str]] = []
        self.fail_next_text = False

    async def send_text(self, phone_e164, text):
        if self.fail_next_text:
            self.fail_next_text = False
            raise EvolutionClientError("send failed")
        self.texts.append((phone_e164, text))
        return "wamid.fake"

    async def send_media(self, phone_e164, path, *, media_type, mime_type, file_name, caption=None):
        self.media.append((phone_e164, file_name))
        return "wamid.fake"

    async def fetch_connection_state(self):
        return EvolutionConnectionState(ok=True, state="open")

    async def aclose(self):
        return None


def _load_fixture(name: str) -> dict:
    with (FIXTURES_DIR / name).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _auth_headers() -> dict[str, str]:
    return {"X-Evolution-Webhook-Token": settings.evolution_webhook_secret}


def _set_message_id(payload: dict, message_id: str) -> dict:
    payload["data"]["key"]["id"] = message_id
    return payload


VALID_CODE = "LP-X7K4-M92Q"  # matches messages_upsert_text.json's message body
VALID_CODE_SENDER = "+33600000012"


# ---------------------------------------------------------------------------
# Webhook security / transport (no DB needed)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evolution_webhook_disabled_returns_not_found(monkeypatch) -> None:
    monkeypatch.setattr(settings, "evolution_whatsapp_enabled", False)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post(WEBHOOK_URL, json=_load_fixture("messages_upsert_text.json"))

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_evolution_webhook_rejects_missing_and_wrong_token_without_leaking_details(monkeypatch) -> None:
    monkeypatch.setattr(settings, "evolution_whatsapp_enabled", True)
    monkeypatch.setattr(settings, "evolution_webhook_secret", "w" * 40)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        missing = await client.post(WEBHOOK_URL, json=_load_fixture("messages_upsert_text.json"))
        wrong = await client.post(
            WEBHOOK_URL,
            headers={"X-Evolution-Webhook-Token": "wrong-token"},
            json=_load_fixture("messages_upsert_text.json"),
        )

    assert missing.status_code == 401
    assert wrong.status_code == 401
    for response in (missing, wrong):
        detail = response.json().get("detail", "")
        assert "X-Evolution-Webhook-Token" not in detail
        assert "Authorization" not in detail
        assert "token" not in detail.lower()


@pytest.mark.asyncio
async def test_evolution_webhook_rejects_malformed_json(monkeypatch) -> None:
    monkeypatch.setattr(settings, "evolution_whatsapp_enabled", True)
    monkeypatch.setattr(settings, "evolution_webhook_secret", "w" * 40)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post(WEBHOOK_URL, headers=_auth_headers(), content=b"{")

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_evolution_webhook_rejects_oversized_body_and_bad_content_length(monkeypatch) -> None:
    monkeypatch.setattr(settings, "evolution_whatsapp_enabled", True)
    monkeypatch.setattr(settings, "evolution_webhook_secret", "w" * 40)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        oversized = await client.post(
            WEBHOOK_URL,
            headers=_auth_headers(),
            content=b"x" * (256 * 1024 + 1),
        )
        bad_length = await client.post(
            WEBHOOK_URL,
            headers={**_auth_headers(), "Content-Length": "bad"},
            content=b"{}",
        )

    assert oversized.status_code == 413
    assert bad_length.status_code == 400


# ---------------------------------------------------------------------------
# Normalizer unit tests (no DB)
# ---------------------------------------------------------------------------


def test_normalize_evolution_event_handles_none_and_non_mapping_and_never_raises() -> None:
    assert normalize_evolution_event(None) is None
    assert normalize_evolution_event("garbage") is None

    assert normalize_evolution_event({}) is not None
    assert normalize_evolution_event({"event": "x"}) is not None
    assert normalize_evolution_event({"data": {"key": None}}) is not None


def test_normalize_evolution_event_extracts_sender_phone_from_s_whatsapp_net_jid() -> None:
    normalized = normalize_evolution_event(_load_fixture("messages_upsert_text.json"))
    assert normalized is not None
    assert normalized.sender_phone_e164 == "+33600000012"


def test_normalize_evolution_event_resolves_lid_sender_via_sender_pn() -> None:
    normalized = normalize_evolution_event(_load_fixture("messages_upsert_lid_sender.json"))
    assert normalized is not None
    assert normalized.sender_phone_e164 == "+33600000013"


def test_normalize_evolution_event_never_falls_back_to_top_level_sender(monkeypatch) -> None:
    payload = _load_fixture("messages_upsert_text.json")
    payload["data"]["key"]["senderPn"] = None
    payload["data"]["key"]["remoteJidAlt"] = None
    payload["data"]["key"]["remoteJid"] = "184620093812345@lid"
    # The platform's own number, exactly as Evolution v2 reports it at the
    # envelope's top level -- must never be attributed as the sender.
    payload["sender"] = "33600000001@s.whatsapp.net"

    normalized = normalize_evolution_event(payload)

    assert normalized is not None
    assert normalized.sender_phone_e164 is None


def test_normalize_evolution_event_flags_group_and_from_me() -> None:
    group = normalize_evolution_event(_load_fixture("messages_upsert_group.json"))
    from_me = normalize_evolution_event(_load_fixture("messages_upsert_from_me.json"))

    assert group is not None and group.is_group is True
    assert from_me is not None and from_me.from_me is True


def test_normalize_evolution_event_extracts_text_from_conversation_and_extended_text() -> None:
    conversation = normalize_evolution_event(_load_fixture("messages_upsert_text.json"))
    extended = normalize_evolution_event(_load_fixture("messages_upsert_extended_text.json"))

    assert conversation is not None and conversation.text == "LP-X7K4-M92Q"
    assert extended is not None and extended.text == "LP-Q9W8-E7R6"


def test_event_key_is_stable_and_differs_by_message_id() -> None:
    first = event_key("leafletpilot", "MESSAGES_UPSERT", "abc123")
    same_again = event_key("leafletpilot", "MESSAGES_UPSERT", "abc123")
    different = event_key("leafletpilot", "MESSAGES_UPSERT", "xyz789")

    assert first == same_again
    assert first != different


def test_extract_verification_code_variants() -> None:
    assert extract_verification_code("Merhaba, kodum LP-X7K4-M92Q") == "LP-X7K4-M92Q"
    assert extract_verification_code("lp x7k4 m92q") == "LP-X7K4-M92Q"
    assert extract_verification_code("Merhaba, listem hazir") is None
    assert extract_verification_code("LP-1234-5678") is None  # '1'/'0' not in the code alphabet


# ---------------------------------------------------------------------------
# DB install / cleanup helpers
# ---------------------------------------------------------------------------


async def _install_whatsapp_test_app(monkeypatch):
    monkeypatch.setattr(settings, "evolution_whatsapp_enabled", True)
    monkeypatch.setattr(settings, "evolution_webhook_secret", "w" * 40)
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


async def _seed_market_and_user(
    session_factory,
    *,
    role: str = "market_admin",
    user_is_active: bool = True,
    membership_is_active: bool = True,
):
    market_id = uuid4()
    user_id = uuid4()
    async with session_factory() as session:
        user = User(id=user_id, email=f"wa-{user_id}@example.com", is_active=user_is_active)
        market = Market(id=market_id, name=f"WA Market {market_id}", slug=f"wa-{market_id}", is_active=True)
        membership = MarketUser(market=market, user=user, role=role, is_active=membership_is_active)
        session.add_all([user, market, membership])
        await session.commit()
    return market_id, user_id


async def _seed_pending_verification(
    session_factory,
    *,
    user_id,
    market_id,
    code: str,
    claimed_phone_e164: str | None = None,
    expires_at=None,
):
    verification_id = uuid4()
    async with session_factory() as session:
        session.add(
            WhatsAppVerification(
                id=verification_id,
                user_id=user_id,
                market_id=market_id,
                code_hash=hash_whatsapp_verification_code(code),
                claimed_phone_e164=claimed_phone_e164,
                status="pending",
                expires_at=expires_at or (utc_now() + timedelta(minutes=10)),
            )
        )
        await session.commit()
    return verification_id


async def _deliver(client, payload, *, message_id: str | None = None):
    if message_id is not None:
        _set_message_id(payload, message_id)
    return await client.post(WEBHOOK_URL, headers=_auth_headers(), json=payload)


# ---------------------------------------------------------------------------
# Ignore rules (DB-backed)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evolution_from_me_message_with_valid_code_is_ignored_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    engine, session_factory, fake = await _install_whatsapp_test_app(monkeypatch)
    try:
        market_id, user_id = await _seed_market_and_user(session_factory)
        verification_id = await _seed_pending_verification(
            session_factory, user_id=user_id, market_id=market_id, code="LP-Z5X4-C3V2"
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await _deliver(client, _load_fixture("messages_upsert_from_me.json"))

        assert response.status_code == 200
        assert fake.texts == []
        async with session_factory() as session:
            verification = await session.get(WhatsAppVerification, verification_id)
        assert verification.status == "pending"
    finally:
        await _cleanup_whatsapp_test_app(engine)


@pytest.mark.asyncio
async def test_evolution_group_message_is_ignored_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    engine, session_factory, fake = await _install_whatsapp_test_app(monkeypatch)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await _deliver(client, _load_fixture("messages_upsert_group.json"))

        assert response.status_code == 200
        assert fake.texts == []
    finally:
        await _cleanup_whatsapp_test_app(engine)


@pytest.mark.asyncio
async def test_evolution_delivery_receipt_and_presence_update_are_ignored_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    engine, session_factory, fake = await _install_whatsapp_test_app(monkeypatch)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            receipt = await client.post(
                WEBHOOK_URL, headers=_auth_headers(), json=_load_fixture("messages_update_receipt.json")
            )
            presence = await client.post(
                WEBHOOK_URL, headers=_auth_headers(), json=_load_fixture("presence_update.json")
            )

        assert receipt.status_code == 200
        assert presence.status_code == 200
        assert fake.texts == []
    finally:
        await _cleanup_whatsapp_test_app(engine)


@pytest.mark.asyncio
async def test_evolution_message_upsert_with_no_text_is_ignored_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    engine, session_factory, fake = await _install_whatsapp_test_app(monkeypatch)
    try:
        payload = _load_fixture("messages_upsert_text.json")
        payload["data"]["message"] = {}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await _deliver(client, payload)

        assert response.status_code == 200
        assert fake.texts == []
    finally:
        await _cleanup_whatsapp_test_app(engine)


@pytest.mark.asyncio
async def test_evolution_message_from_platform_own_number_is_ignored_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    engine, session_factory, fake = await _install_whatsapp_test_app(monkeypatch)
    try:
        payload = _load_fixture("messages_upsert_text.json")
        own_jid = "33600000001@s.whatsapp.net"  # settings.leafletpilot_whatsapp_number
        payload["data"]["key"]["remoteJid"] = own_jid
        payload["data"]["key"]["remoteJidAlt"] = own_jid
        payload["data"]["key"]["senderPn"] = own_jid

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await _deliver(client, payload)

        assert response.status_code == 200
        assert fake.texts == []
    finally:
        await _cleanup_whatsapp_test_app(engine)


# ---------------------------------------------------------------------------
# Idempotency (DB-backed)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evolution_duplicate_delivery_is_idempotent_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    engine, session_factory, fake = await _install_whatsapp_test_app(monkeypatch)
    try:
        market_id, user_id = await _seed_market_and_user(session_factory)
        verification_id = await _seed_pending_verification(
            session_factory, user_id=user_id, market_id=market_id, code=VALID_CODE
        )
        payload = _load_fixture("messages_upsert_text.json")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            first = await client.post(WEBHOOK_URL, headers=_auth_headers(), json=payload)
            first_text_count = len(fake.texts)
            second = await client.post(WEBHOOK_URL, headers=_auth_headers(), json=payload)

        assert first.status_code == 200
        assert second.status_code == 200
        assert len(fake.texts) == first_text_count  # no additional outbound message

        async with session_factory() as session:
            verification = await session.get(WhatsAppVerification, verification_id)
            identity_count = await session.scalar(
                select(func.count()).select_from(UserWhatsAppIdentity).where(UserWhatsAppIdentity.user_id == user_id)
            )
            events = (
                await session.scalars(
                    select(WhatsAppWebhookEvent).where(
                        WhatsAppWebhookEvent.event_key == event_key("leafletpilot", "MESSAGES_UPSERT", "3EB0C767D26B8A3F1B23")
                    )
                )
            ).all()

        assert verification.status == "verified"
        assert identity_count == 1
        assert len(events) == 1
        assert events[0].status == "completed"
    finally:
        await _cleanup_whatsapp_test_app(engine)


# ---------------------------------------------------------------------------
# Verification by webhook (DB-backed)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evolution_verification_happy_path_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    engine, session_factory, fake = await _install_whatsapp_test_app(monkeypatch)
    try:
        market_id, user_id = await _seed_market_and_user(session_factory)
        verification_id = await _seed_pending_verification(
            session_factory, user_id=user_id, market_id=market_id, code=VALID_CODE
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await _deliver(client, _load_fixture("messages_upsert_text.json"))

        assert response.status_code == 200
        async with session_factory() as session:
            verification = await session.get(WhatsAppVerification, verification_id)
            identity = await session.scalar(
                select(UserWhatsAppIdentity).where(UserWhatsAppIdentity.user_id == user_id)
            )

        assert verification.status == "verified"
        assert verification.resolved_phone_e164 == VALID_CODE_SENDER
        assert verification.consumed_at is not None
        assert identity is not None
        assert identity.status == "verified"
        assert identity.phone_e164 == VALID_CODE_SENDER
        assert identity.verified_source == "evolution_whatsapp"
        assert any(phone == VALID_CODE_SENDER and "doğrulandı" in text for phone, text in fake.texts)
    finally:
        await _cleanup_whatsapp_test_app(engine)


@pytest.mark.asyncio
async def test_evolution_verification_sender_is_authoritative_over_claimed_phone_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    engine, session_factory, fake = await _install_whatsapp_test_app(monkeypatch)
    try:
        market_id, user_id = await _seed_market_and_user(session_factory)
        await _seed_pending_verification(
            session_factory,
            user_id=user_id,
            market_id=market_id,
            code=VALID_CODE,
            claimed_phone_e164="+33699999999",
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await _deliver(client, _load_fixture("messages_upsert_text.json"))

        assert response.status_code == 200
        async with session_factory() as session:
            identity = await session.scalar(
                select(UserWhatsAppIdentity).where(UserWhatsAppIdentity.user_id == user_id)
            )
            identity_count = await session.scalar(select(func.count()).select_from(UserWhatsAppIdentity))

        assert identity is not None
        assert identity.phone_e164 == VALID_CODE_SENDER  # real sender, not the claimed number
        assert identity_count == 1  # no other user's record was touched
        assert any("farklı" in text for _phone, text in fake.texts)
    finally:
        await _cleanup_whatsapp_test_app(engine)


@pytest.mark.asyncio
async def test_evolution_unknown_code_reply_matches_never_existed_code_reply_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    engine, session_factory, fake = await _install_whatsapp_test_app(monkeypatch)
    try:
        market_id, user_id = await _seed_market_and_user(session_factory)
        await _seed_pending_verification(session_factory, user_id=user_id, market_id=market_id, code=VALID_CODE)

        wrong_but_shaped_like_a_real_code = _load_fixture("messages_upsert_text.json")
        wrong_but_shaped_like_a_real_code["data"]["message"]["conversation"] = "LP-9K8H-7G6F"
        never_existed = _load_fixture("messages_upsert_text.json")
        never_existed["data"]["message"]["conversation"] = "LP-2Q3W-4E5R"

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            first = await _deliver(client, wrong_but_shaped_like_a_real_code, message_id="msg-wrong-code")
            second = await _deliver(client, never_existed, message_id="msg-never-existed")

        assert first.status_code == 200
        assert second.status_code == 200
        async with session_factory() as session:
            identity_count = await session.scalar(select(func.count()).select_from(UserWhatsAppIdentity))
        assert identity_count == 0
        assert len(fake.texts) == 2
        assert fake.texts[0][1] == INVALID_CODE_REPLY
        assert fake.texts[1][1] == INVALID_CODE_REPLY
        assert fake.texts[0][1] == fake.texts[1][1]
    finally:
        await _cleanup_whatsapp_test_app(engine)


@pytest.mark.asyncio
async def test_evolution_replay_of_consumed_code_gets_generic_invalid_reply_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    engine, session_factory, fake = await _install_whatsapp_test_app(monkeypatch)
    try:
        market_id, user_id = await _seed_market_and_user(session_factory)
        await _seed_pending_verification(session_factory, user_id=user_id, market_id=market_id, code=VALID_CODE)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            first = await _deliver(client, _load_fixture("messages_upsert_text.json"), message_id="msg-first")
            replay = await _deliver(client, _load_fixture("messages_upsert_text.json"), message_id="msg-replay")

        assert first.status_code == 200
        assert replay.status_code == 200
        async with session_factory() as session:
            identity_count = await session.scalar(
                select(func.count()).select_from(UserWhatsAppIdentity).where(UserWhatsAppIdentity.user_id == user_id)
            )
        assert identity_count == 1  # no second identity
        assert fake.texts[-1][1] == INVALID_CODE_REPLY
    finally:
        await _cleanup_whatsapp_test_app(engine)


@pytest.mark.asyncio
async def test_evolution_expired_code_marks_verification_expired_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    engine, session_factory, fake = await _install_whatsapp_test_app(monkeypatch)
    try:
        market_id, user_id = await _seed_market_and_user(session_factory)
        verification_id = await _seed_pending_verification(
            session_factory,
            user_id=user_id,
            market_id=market_id,
            code=VALID_CODE,
            expires_at=utc_now() - timedelta(minutes=1),
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await _deliver(client, _load_fixture("messages_upsert_text.json"))

        assert response.status_code == 200
        async with session_factory() as session:
            verification = await session.get(WhatsAppVerification, verification_id)
            identity_count = await session.scalar(
                select(func.count()).select_from(UserWhatsAppIdentity).where(UserWhatsAppIdentity.user_id == user_id)
            )
        assert verification.status == "expired"
        assert identity_count == 0
    finally:
        await _cleanup_whatsapp_test_app(engine)


@pytest.mark.asyncio
async def test_evolution_verification_attempt_count_when_test_database_url_is_configured(monkeypatch) -> None:
    """`whatsapp_verification_max_attempts` is enforced across deliveries.

    A phone collision is the one RECOVERABLE failure: the code was right, it
    just arrived from the wrong handset, so the challenge deliberately stays
    `pending` and the user can resend from the correct phone inside the same
    window. `attempt_count` is what bounds that, and it is the only path on
    which the attempt limit is reachable — every other failure (disabled
    account, revoked membership, expiry) is terminal by nature.
    """
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    engine, session_factory, fake = await _install_whatsapp_test_app(monkeypatch)
    monkeypatch.setattr(settings, "whatsapp_verification_max_attempts", 2)
    try:
        # User A is already verified on the phone the code will be delivered from.
        market_a, user_a = await _seed_market_and_user(session_factory)
        async with session_factory() as session:
            session.add(
                UserWhatsAppIdentity(
                    user_id=user_a,
                    phone_e164=VALID_CODE_SENDER,
                    whatsapp_jid=f"{VALID_CODE_SENDER.lstrip('+')}@s.whatsapp.net",
                    status="verified",
                    verified_source="evolution_whatsapp",
                )
            )
            await session.commit()

        market_b, user_b = await _seed_market_and_user(session_factory)
        verification_id = await _seed_pending_verification(
            session_factory, user_id=user_b, market_id=market_b, code=VALID_CODE
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            first = await _deliver(client, _load_fixture("messages_upsert_text.json"), message_id="attempt-1")
            assert first.status_code == 200

            async with session_factory() as session:
                after_first = await session.get(WhatsAppVerification, verification_id)
                assert after_first.status == "pending", "a wrong-handset collision must stay retryable"
                assert after_first.failure_reason == "phone_already_linked"
                assert after_first.attempt_count == 1

            second = await _deliver(client, _load_fixture("messages_upsert_text.json"), message_id="attempt-2")
            assert second.status_code == 200

            async with session_factory() as session:
                after_second = await session.get(WhatsAppVerification, verification_id)
                assert after_second.status == "pending"
                assert after_second.attempt_count == 2

            # attempt_count now exceeds whatsapp_verification_max_attempts=2.
            third = await _deliver(client, _load_fixture("messages_upsert_text.json"), message_id="attempt-3")
            assert third.status_code == 200

        async with session_factory() as session:
            verification = await session.get(WhatsAppVerification, verification_id)

        assert verification.status == "failed"
        assert verification.failure_reason == "attempt_limit"
        assert verification.attempt_count == 3
        assert fake.texts[-1][1] == INVALID_CODE_REPLY
    finally:
        await _cleanup_whatsapp_test_app(engine)


@pytest.mark.asyncio
async def test_evolution_phone_collision_protects_existing_identity_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    engine, session_factory, fake = await _install_whatsapp_test_app(monkeypatch)
    try:
        market_a, user_a = await _seed_market_and_user(session_factory)
        async with session_factory() as session:
            identity_a = UserWhatsAppIdentity(
                user_id=user_a,
                phone_e164=VALID_CODE_SENDER,
                whatsapp_jid=f"{VALID_CODE_SENDER.lstrip('+')}@s.whatsapp.net",
                status="verified",
                verified_source="evolution_whatsapp",
            )
            session.add(identity_a)
            await session.commit()
            await session.refresh(identity_a)
            identity_a_id = identity_a.id

        market_b, user_b = await _seed_market_and_user(session_factory)
        verification_id = await _seed_pending_verification(
            session_factory, user_id=user_b, market_id=market_b, code=VALID_CODE
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await _deliver(client, _load_fixture("messages_upsert_text.json"))

        assert response.status_code == 200
        async with session_factory() as session:
            verification_b = await session.get(WhatsAppVerification, verification_id)
            identity_b = await session.scalar(
                select(UserWhatsAppIdentity).where(UserWhatsAppIdentity.user_id == user_b)
            )
            identity_a_after = await session.get(UserWhatsAppIdentity, identity_a_id)

        assert identity_b is None  # user B got no identity
        # Recoverable failure: the challenge stays live so B can resend from
        # their own handset, but B is emphatically NOT verified onto A's phone.
        assert verification_b.status == "pending"
        assert verification_b.failure_reason == "phone_already_linked"
        assert identity_a_after is not None
        assert identity_a_after.id == identity_a_id
        assert identity_a_after.user_id == user_a
        assert identity_a_after.status == "verified"  # completely unchanged
        assert any("başka bir LeafletPilot kullanıcısına bağlı" in text for _phone, text in fake.texts)
    finally:
        await _cleanup_whatsapp_test_app(engine)


@pytest.mark.asyncio
async def test_evolution_membership_revoked_between_request_and_reply_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    engine, session_factory, fake = await _install_whatsapp_test_app(monkeypatch)
    try:
        market_id, user_id = await _seed_market_and_user(session_factory)
        verification_id = await _seed_pending_verification(
            session_factory, user_id=user_id, market_id=market_id, code=VALID_CODE
        )

        async with session_factory() as session:
            membership = await session.scalar(select(MarketUser).where(MarketUser.user_id == user_id))
            membership.is_active = False
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await _deliver(client, _load_fixture("messages_upsert_text.json"))

        assert response.status_code == 200
        async with session_factory() as session:
            verification = await session.get(WhatsAppVerification, verification_id)
            identity_count = await session.scalar(
                select(func.count()).select_from(UserWhatsAppIdentity).where(UserWhatsAppIdentity.user_id == user_id)
            )
        assert verification.status == "failed"
        assert verification.failure_reason == "membership_revoked"
        assert identity_count == 0
    finally:
        await _cleanup_whatsapp_test_app(engine)


@pytest.mark.asyncio
async def test_evolution_disabled_user_verification_fails_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    engine, session_factory, fake = await _install_whatsapp_test_app(monkeypatch)
    try:
        market_id, user_id = await _seed_market_and_user(session_factory)
        verification_id = await _seed_pending_verification(
            session_factory, user_id=user_id, market_id=market_id, code=VALID_CODE
        )

        async with session_factory() as session:
            user = await session.get(User, user_id)
            user.is_active = False
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await _deliver(client, _load_fixture("messages_upsert_text.json"))

        assert response.status_code == 200
        async with session_factory() as session:
            verification = await session.get(WhatsAppVerification, verification_id)
            identity_count = await session.scalar(
                select(func.count()).select_from(UserWhatsAppIdentity).where(UserWhatsAppIdentity.user_id == user_id)
            )
        assert verification.failure_reason == "user_inactive"
        assert identity_count == 0
    finally:
        await _cleanup_whatsapp_test_app(engine)


# ---------------------------------------------------------------------------
# Unverified sender (DB-backed)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evolution_unverified_sender_gets_generic_reply_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    engine, session_factory, fake = await _install_whatsapp_test_app(monkeypatch)
    try:
        payload = _load_fixture("messages_upsert_text.json")
        payload["data"]["message"]["conversation"] = "merhaba"

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await _deliver(client, payload)

        assert response.status_code == 200
        assert fake.texts[-1][1] == UNVERIFIED_REPLY
    finally:
        await _cleanup_whatsapp_test_app(engine)


@pytest.mark.asyncio
async def test_evolution_unverified_sender_generic_reply_is_rate_limited_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    engine, session_factory, fake = await _install_whatsapp_test_app(monkeypatch)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            for index in range(6):
                payload = _load_fixture("messages_upsert_text.json")
                payload["data"]["message"]["conversation"] = "merhaba"
                response = await _deliver(client, payload, message_id=f"unverified-{index}")
                assert response.status_code == 200

        assert len(fake.texts) < 6
    finally:
        await _cleanup_whatsapp_test_app(engine)


# ---------------------------------------------------------------------------
# Outbound failure handling (DB-backed)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evolution_outbound_send_failure_does_not_lose_inbound_verification_state_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed WhatsApp tests skipped.")

    engine, session_factory, fake = await _install_whatsapp_test_app(monkeypatch)
    try:
        market_id, user_id = await _seed_market_and_user(session_factory)
        verification_id = await _seed_pending_verification(
            session_factory, user_id=user_id, market_id=market_id, code=VALID_CODE
        )
        payload = _load_fixture("messages_upsert_text.json")
        fake.fail_next_text = True

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await _deliver(client, payload)

        assert response.status_code == 200
        async with session_factory() as session:
            verification = await session.get(WhatsAppVerification, verification_id)
            state = await session.scalar(
                select(WhatsAppIntegrationState).where(
                    WhatsAppIntegrationState.instance_name == settings.evolution_instance_name
                )
            )

        assert verification.status == "verified"  # inbound state survives an outbound failure
        assert state is not None
        # The failure must still be visible to Platform Admin afterwards. One
        # inbound message triggers several sends (confirmation, then the
        # welcome/market prompt), and only the first was made to fail — so
        # this also pins that a later SUCCESSFUL send does not wipe the
        # error. `last_outbound_error` is the LAST error, not the current one.
        assert isinstance(state.last_outbound_error, str) and state.last_outbound_error
        assert state.last_outbound_error_at is not None
        # A later send did succeed, so the success timestamp is also recorded.
        assert state.last_outbound_at is not None
    finally:
        await _cleanup_whatsapp_test_app(engine)
