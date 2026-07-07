from __future__ import annotations

import asyncio
import sys
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.api.deps import get_catalog_session
from app.api.routes.telegram import get_telegram_client
from app.core.config import settings
from app.core.database import Base
from app.integrations.telegram.client import TelegramClient, TelegramClientError
from app.main import app
from app.models import (
    Campaign,
    CampaignFile,
    ExportJob,
    Market,
    MarketUser,
    TelegramAccount,
    TelegramConversationState,
    TelegramUpdate,
    User,
)
from app.models.base import utc_now
from scripts import link_telegram_account


class FakeTelegramClient:
    def __init__(self) -> None:
        self.messages: list[tuple[int, str, dict | None]] = []
        self.documents: list[Path] = []
        self.photos: list[Path] = []
        self.answered_callbacks: list[str] = []
        self.fail_next_document = False
        self.fail_next_photo = False

    async def send_message(self, chat_id, text, *, reply_markup=None):
        self.messages.append((chat_id, text, reply_markup))

    async def edit_message_text(self, chat_id, message_id, text, *, reply_markup=None):
        self.messages.append((chat_id, text, reply_markup))

    async def answer_callback_query(self, callback_query_id, *, text=None):
        self.answered_callbacks.append(callback_query_id)

    async def send_document(self, chat_id, path, *, caption=None):
        if self.fail_next_document:
            self.fail_next_document = False
            raise TelegramClientError("document failed")
        self.documents.append(path)

    async def send_photo(self, chat_id, path, *, caption=None):
        if self.fail_next_photo:
            self.fail_next_photo = False
            raise TelegramClientError("photo failed")
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
async def test_telegram_webhook_rejects_malformed_json_and_bad_content_length(monkeypatch) -> None:
    monkeypatch.setattr(settings, "telegram_bot_enabled", True)
    monkeypatch.setattr(settings, "telegram_webhook_secret", "s" * 40)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        malformed = await client.post(
            "/api/integrations/telegram/webhook",
            headers={"X-Telegram-Bot-Api-Secret-Token": settings.telegram_webhook_secret},
            content=b"{",
        )
        bad_length = await client.post(
            "/api/integrations/telegram/webhook",
            headers={
                "X-Telegram-Bot-Api-Secret-Token": settings.telegram_webhook_secret,
                "Content-Length": "bad",
            },
            content=b"{}",
        )

    assert malformed.status_code == 422
    assert bad_length.status_code == 400


@pytest.mark.asyncio
async def test_telegram_webhook_rejects_oversized_body(monkeypatch) -> None:
    monkeypatch.setattr(settings, "telegram_bot_enabled", True)
    monkeypatch.setattr(settings, "telegram_webhook_secret", "s" * 40)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post(
            "/api/integrations/telegram/webhook",
            headers={"X-Telegram-Bot-Api-Secret-Token": settings.telegram_webhook_secret},
            content=b"x" * (64 * 1024 + 1),
        )

    assert response.status_code == 413


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
            await client.post(
                "/api/integrations/telegram/webhook",
                headers={"X-Telegram-Bot-Api-Secret-Token": settings.telegram_webhook_secret},
                json=_message_update(39, telegram_user_id, telegram_user_id, "/markets"),
            )
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


@pytest.mark.asyncio
async def test_telegram_private_chat_only_and_inactive_account_denied_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed Telegram tests skipped.")

    engine, session_factory, fake = await _install_telegram_test_app(monkeypatch)
    try:
        telegram_user_id, _, _ = await _seed_linked_user(session_factory, role="market_staff")
        headers = {"X-Telegram-Bot-Api-Secret-Token": settings.telegram_webhook_secret}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            group_response = await client.post(
                "/api/integrations/telegram/webhook",
                headers=headers,
                json=_message_update(50, telegram_user_id, -1, "/start", chat_type="group"),
            )
            async with session_factory() as session:
                account = await session.scalar(select(TelegramAccount).where(TelegramAccount.telegram_user_id == telegram_user_id))
                account.is_active = False
                await session.commit()
            inactive_response = await client.post(
                "/api/integrations/telegram/webhook",
                headers=headers,
                json=_message_update(51, telegram_user_id, telegram_user_id, "/start"),
            )

        assert group_response.status_code == 200
        assert inactive_response.status_code == 200
        assert any("sadece ozel sohbetlerde" in message for _, message, _ in fake.messages)
        assert "bagli degil" in fake.messages[-1][1]
    finally:
        await _cleanup_telegram_test_app(engine)


@pytest.mark.asyncio
async def test_telegram_stale_processing_recovery_and_failed_retry_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed Telegram tests skipped.")

    engine, session_factory, fake = await _install_telegram_test_app(monkeypatch)
    try:
        telegram_user_id, _, _ = await _seed_linked_user(session_factory, role="market_staff")
        now = utc_now()
        async with session_factory() as session:
            session.add_all(
                [
                    TelegramUpdate(
                        update_id=60,
                        status="processing",
                        attempt_count=1,
                        processing_started_at=now,
                    ),
                    TelegramUpdate(
                        update_id=61,
                        status="processing",
                        attempt_count=1,
                        processing_started_at=now - timedelta(minutes=6),
                    ),
                    TelegramUpdate(
                        update_id=62,
                        status="failed",
                        attempt_count=1,
                        processing_started_at=now,
                    ),
                    TelegramUpdate(
                        update_id=63,
                        status="completed",
                        attempt_count=1,
                        processing_started_at=now,
                    ),
                ]
            )
            await session.commit()

        headers = {"X-Telegram-Bot-Api-Secret-Token": settings.telegram_webhook_secret}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            recent = await client.post(
                "/api/integrations/telegram/webhook",
                headers=headers,
                json=_message_update(60, telegram_user_id, telegram_user_id, "/status"),
            )
            stale = await client.post(
                "/api/integrations/telegram/webhook",
                headers=headers,
                json=_message_update(61, telegram_user_id, telegram_user_id, "/status"),
            )
            failed = await client.post(
                "/api/integrations/telegram/webhook",
                headers=headers,
                json=_message_update(62, telegram_user_id, telegram_user_id, "/status"),
            )
            completed = await client.post(
                "/api/integrations/telegram/webhook",
                headers=headers,
                json=_message_update(63, telegram_user_id, telegram_user_id, "/status"),
            )

        assert [recent.status_code, stale.status_code, failed.status_code, completed.status_code] == [200, 200, 200, 200]
        async with session_factory() as session:
            recent_record = await session.scalar(select(TelegramUpdate).where(TelegramUpdate.update_id == 60))
            stale_record = await session.scalar(select(TelegramUpdate).where(TelegramUpdate.update_id == 61))
            failed_record = await session.scalar(select(TelegramUpdate).where(TelegramUpdate.update_id == 62))
            completed_record = await session.scalar(select(TelegramUpdate).where(TelegramUpdate.update_id == 63))
        assert recent_record.attempt_count == 1
        assert stale_record.status == "completed"
        assert stale_record.attempt_count == 2
        assert failed_record.status == "completed"
        assert failed_record.attempt_count == 2
        assert completed_record.attempt_count == 1
    finally:
        await _cleanup_telegram_test_app(engine)


@pytest.mark.asyncio
async def test_telegram_unique_update_id_constraint_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed Telegram tests skipped.")

    engine, session_factory, _ = await _install_telegram_test_app(monkeypatch)
    try:
        async with session_factory() as session:
            session.add(TelegramUpdate(update_id=70, status="completed", attempt_count=1))
            await session.commit()
            session.add(TelegramUpdate(update_id=70, status="completed", attempt_count=1))
            with pytest.raises(IntegrityError):
                await session.commit()
    finally:
        await _cleanup_telegram_test_app(engine)


@pytest.mark.asyncio
async def test_telegram_link_script_rejects_unknown_email_when_test_database_url_is_configured(monkeypatch) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed Telegram tests skipped.")

    engine, session_factory, _ = await _install_telegram_test_app(monkeypatch)
    try:
        monkeypatch.setattr(link_telegram_account, "AsyncSessionLocal", session_factory)
        monkeypatch.setattr(
            sys,
            "argv",
            ["link_telegram_account.py", "--email", "missing@example.com", "--telegram-user-id", "12345"],
        )

        exit_code = await link_telegram_account.main()

        assert exit_code == 1
    finally:
        await _cleanup_telegram_test_app(engine)


@pytest.mark.asyncio
async def test_telegram_link_script_is_idempotent_and_rejects_duplicate_telegram_id_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed Telegram tests skipped.")

    engine, session_factory, _ = await _install_telegram_test_app(monkeypatch)
    try:
        async with session_factory() as session:
            user = User(id=uuid4(), email="link@example.com", is_active=True)
            other_user = User(id=uuid4(), email="other-link@example.com", is_active=True)
            session.add_all([user, other_user])
            await session.commit()
        monkeypatch.setattr(link_telegram_account, "AsyncSessionLocal", session_factory)
        monkeypatch.setattr(
            sys,
            "argv",
            ["link_telegram_account.py", "--email", "link@example.com", "--telegram-user-id", "12345"],
        )

        first = await link_telegram_account.main()
        second = await link_telegram_account.main()

        monkeypatch.setattr(
            sys,
            "argv",
            ["link_telegram_account.py", "--email", "other-link@example.com", "--telegram-user-id", "12345"],
        )
        duplicate = await link_telegram_account.main()

        assert first == 0
        assert second == 0
        assert duplicate == 3
        async with session_factory() as session:
            count = await session.scalar(select(func.count()).select_from(TelegramAccount))
        assert count == 1
    finally:
        await _cleanup_telegram_test_app(engine)


@pytest.mark.asyncio
async def test_telegram_export_replay_reuses_job_and_does_not_resend_completed_files_when_test_database_url_is_configured(
    monkeypatch, tmp_path
) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed Telegram tests skipped.")

    monkeypatch.setattr(settings, "local_storage_dir", str(tmp_path))
    engine, session_factory, fake = await _install_telegram_test_app(monkeypatch)
    try:
        telegram_user_id, market_id, _ = await _seed_linked_user(session_factory, role="market_admin")
        await _prepare_campaign_ready_for_export(session_factory, telegram_user_id, market_id)
        export_calls: list[str] = []

        async def fake_create_export_job(session, campaign_id, payload, market_id_arg, *, commit=True, after_flush=None):
            export_calls.append(str(campaign_id))
            job = ExportJob(campaign_id=campaign_id, market_id=market_id_arg, job_type="final_export", status="completed", requested_formats=["pdf", "png"])
            session.add(job)
            await session.flush()
            if after_flush is not None:
                await after_flush(job)
                await session.flush()
            pdf = _write_export_file(tmp_path, market_id_arg, campaign_id, job.id, "pdf")
            png = _write_export_file(tmp_path, market_id_arg, campaign_id, job.id, "png")
            pdf_file = CampaignFile(campaign_id=campaign_id, market_id=market_id_arg, file_type="brochure_pdf", format="pdf", status="ready", storage_key=pdf, size_bytes=1)
            png_file = CampaignFile(campaign_id=campaign_id, market_id=market_id_arg, file_type="brochure_png", format="png", status="ready", storage_key=png, size_bytes=1)
            session.add_all([pdf_file, png_file])
            await session.flush()
            job.result_file_ids = [str(pdf_file.id), str(png_file.id)]
            await session.flush()
            return job

        monkeypatch.setattr("app.integrations.telegram.service.campaign_service.create_export_job", fake_create_export_job)
        headers = {"X-Telegram-Bot-Api-Secret-Token": settings.telegram_webhook_secret}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            first = await client.post(
                "/api/integrations/telegram/webhook",
                headers=headers,
                json=_callback_update(80, telegram_user_id, telegram_user_id, "export:confirm"),
            )
            replay = await client.post(
                "/api/integrations/telegram/webhook",
                headers=headers,
                json=_callback_update(81, telegram_user_id, telegram_user_id, "export:confirm"),
            )

        assert first.status_code == 200
        assert replay.status_code == 200
        assert len(export_calls) == 1
        assert len(fake.documents) == 1
        assert len(fake.photos) == 1
        assert "zaten tamamlandi" in fake.messages[-1][1]
    finally:
        await _cleanup_telegram_test_app(engine)


@pytest.mark.asyncio
async def test_telegram_export_send_failure_retries_existing_files_when_test_database_url_is_configured(
    monkeypatch, tmp_path
) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed Telegram tests skipped.")

    monkeypatch.setattr(settings, "local_storage_dir", str(tmp_path))
    engine, session_factory, fake = await _install_telegram_test_app(monkeypatch)
    try:
        telegram_user_id, market_id, _ = await _seed_linked_user(session_factory, role="market_staff")
        await _prepare_campaign_ready_for_export(session_factory, telegram_user_id, market_id)
        export_calls: list[str] = []

        async def fake_create_export_job(session, campaign_id, payload, market_id_arg, *, commit=True, after_flush=None):
            export_calls.append(str(campaign_id))
            job = ExportJob(campaign_id=campaign_id, market_id=market_id_arg, job_type="final_export", status="completed", requested_formats=["pdf", "png"])
            session.add(job)
            await session.flush()
            if after_flush is not None:
                await after_flush(job)
                await session.flush()
            pdf = _write_export_file(tmp_path, market_id_arg, campaign_id, job.id, "pdf")
            png = _write_export_file(tmp_path, market_id_arg, campaign_id, job.id, "png")
            pdf_file = CampaignFile(campaign_id=campaign_id, market_id=market_id_arg, file_type="brochure_pdf", format="pdf", status="ready", storage_key=pdf, size_bytes=1)
            png_file = CampaignFile(campaign_id=campaign_id, market_id=market_id_arg, file_type="brochure_png", format="png", status="ready", storage_key=png, size_bytes=1)
            session.add_all([pdf_file, png_file])
            await session.flush()
            job.result_file_ids = [str(pdf_file.id), str(png_file.id)]
            await session.flush()
            return job

        monkeypatch.setattr("app.integrations.telegram.service.campaign_service.create_export_job", fake_create_export_job)
        fake.fail_next_photo = True
        headers = {"X-Telegram-Bot-Api-Secret-Token": settings.telegram_webhook_secret}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            failed = await client.post(
                "/api/integrations/telegram/webhook",
                headers=headers,
                json=_callback_update(90, telegram_user_id, telegram_user_id, "export:confirm"),
            )
            retried = await client.post(
                "/api/integrations/telegram/webhook",
                headers=headers,
                json=_callback_update(91, telegram_user_id, telegram_user_id, "export:confirm"),
            )

        assert failed.status_code == 200
        assert retried.status_code == 200
        assert len(export_calls) == 1
        assert len(fake.documents) == 1
        assert len(fake.photos) == 1
    finally:
        await _cleanup_telegram_test_app(engine)


@pytest.mark.asyncio
async def test_telegram_concurrent_title_updates_create_one_campaign_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed Telegram tests skipped.")

    engine, session_factory, fake = await _install_telegram_test_app(monkeypatch)
    try:
        telegram_user_id, market_id, _ = await _seed_linked_user(session_factory, role="market_staff")
        async with session_factory() as session:
            account = await session.scalar(
                select(TelegramAccount).where(TelegramAccount.telegram_user_id == telegram_user_id)
            )
            session.add(
                TelegramConversationState(
                    telegram_account_id=account.id,
                    user_id=account.user_id,
                    telegram_user_id=telegram_user_id,
                    chat_id=telegram_user_id,
                    selected_market_id=market_id,
                    state="awaiting_title",
                    pending_raw_text="Milk 1L - 1.29",
                )
            )
            await session.commit()

        headers = {"X-Telegram-Bot-Api-Secret-Token": settings.telegram_webhook_secret}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client_one:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client_two:
                first, second = await asyncio.gather(
                    client_one.post(
                        "/api/integrations/telegram/webhook",
                        headers=headers,
                        json=_message_update(1000, telegram_user_id, telegram_user_id, "Weekly Deals"),
                    ),
                    client_two.post(
                        "/api/integrations/telegram/webhook",
                        headers=headers,
                        json=_message_update(1001, telegram_user_id, telegram_user_id, "Weekly Deals"),
                    ),
                )

        assert first.status_code == 200
        assert second.status_code == 200
        async with session_factory() as session:
            campaign_count = await session.scalar(
                select(func.count()).select_from(Campaign).where(Campaign.market_id == market_id)
            )
            state = await session.scalar(
                select(TelegramConversationState).where(
                    TelegramConversationState.telegram_user_id == telegram_user_id
                )
            )
            updates = (
                await session.scalars(
                    select(TelegramUpdate).where(TelegramUpdate.update_id.in_([1000, 1001]))
                )
            ).all()

        assert campaign_count == 1
        assert state.state == "awaiting_confirmation"
        assert state.campaign_id is not None
        assert sorted(update.status for update in updates) == ["completed", "completed"]
        assert sum(1 for _, message, _ in fake.messages if "Kampanya olusturuldu" in message) == 1
        assert any("zaten islendi" in message for _, message, _ in fake.messages)
    finally:
        await _cleanup_telegram_test_app(engine)


@pytest.mark.asyncio
async def test_telegram_concurrent_export_confirms_create_one_job_and_one_delivery_when_test_database_url_is_configured(
    monkeypatch,
    tmp_path,
) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed Telegram tests skipped.")

    monkeypatch.setattr(settings, "local_storage_dir", str(tmp_path))

    async def fake_pdf(html, output_path):
        output_path.write_bytes(b"%PDF-1.4\n")

    async def fake_png(html, output_path):
        output_path.write_bytes(b"\x89PNG\r\n\x1a\n")

    monkeypatch.setattr("app.services.rendering.render_html_to_pdf", fake_pdf)
    monkeypatch.setattr("app.services.rendering.render_html_to_png", fake_png)

    engine, session_factory, fake = await _install_telegram_test_app(monkeypatch)
    try:
        telegram_user_id, market_id, _ = await _seed_linked_user(session_factory, role="market_admin")
        campaign_id = await _prepare_campaign_ready_for_export(session_factory, telegram_user_id, market_id)

        headers = {"X-Telegram-Bot-Api-Secret-Token": settings.telegram_webhook_secret}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client_one:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client_two:
                first, second = await asyncio.gather(
                    client_one.post(
                        "/api/integrations/telegram/webhook",
                        headers=headers,
                        json=_callback_update(1010, telegram_user_id, telegram_user_id, "export:confirm"),
                    ),
                    client_two.post(
                        "/api/integrations/telegram/webhook",
                        headers=headers,
                        json=_callback_update(1011, telegram_user_id, telegram_user_id, "export:confirm"),
                    ),
                )

        assert first.status_code == 200
        assert second.status_code == 200
        async with session_factory() as session:
            job_count = await session.scalar(
                select(func.count()).select_from(ExportJob).where(ExportJob.campaign_id == campaign_id)
            )
            state = await session.scalar(
                select(TelegramConversationState).where(
                    TelegramConversationState.telegram_user_id == telegram_user_id
                )
            )
            updates = (
                await session.scalars(
                    select(TelegramUpdate).where(TelegramUpdate.update_id.in_([1010, 1011]))
                )
            ).all()

        assert job_count == 1
        assert len(fake.documents) == 1
        assert len(fake.photos) == 1
        assert state.state == "completed"
        assert state.export_job_id is not None
        assert state.export_document_sent_at is not None
        assert state.export_photo_sent_at is not None
        assert state.export_files_sent_at is not None
        assert sorted(update.status for update in updates) == ["completed", "completed"]
    finally:
        await _cleanup_telegram_test_app(engine)


@pytest.mark.asyncio
async def test_telegram_client_timeout_does_not_retry_send_operations() -> None:
    calls = 0

    async def handler(request):
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("timeout", request=request)

    client = TelegramClient(token="123:secret", http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    with pytest.raises(TelegramClientError):
        await client.send_message(1, "hello")

    assert calls == 1


@pytest.mark.asyncio
async def test_telegram_client_timeout_does_not_retry_document_or_photo(tmp_path) -> None:
    calls = 0
    path = tmp_path / "file.bin"
    path.write_bytes(b"x")

    async def handler(request):
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("timeout", request=request)

    client = TelegramClient(token="123:secret", http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    with pytest.raises(TelegramClientError):
        await client.send_document(1, path)
    with pytest.raises(TelegramClientError):
        await client.send_photo(1, path)

    assert calls == 2


@pytest.mark.asyncio
async def test_telegram_client_redacts_token_from_api_errors() -> None:
    token = "123:secret-token"

    async def handler(request):
        return httpx.Response(200, json={"ok": False, "description": f"bad token {token}"})

    client = TelegramClient(token=token, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    with pytest.raises(TelegramClientError) as exc_info:
        await client.send_message(1, "hello")

    assert token not in str(exc_info.value)


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


async def _prepare_campaign_ready_for_export(session_factory, telegram_user_id, market_id):
    async with session_factory() as session:
        account = await session.scalar(select(TelegramAccount).where(TelegramAccount.telegram_user_id == telegram_user_id))
        campaign = Campaign(market_id=market_id, title="Weekly Deals", channel="telegram", source_type="text")
        session.add(campaign)
        await session.flush()
        state = TelegramConversationState(
            telegram_account_id=account.id,
            user_id=account.user_id,
            telegram_user_id=telegram_user_id,
            chat_id=telegram_user_id,
            selected_market_id=market_id,
            state="awaiting_confirmation",
            campaign_id=campaign.id,
            pending_title=campaign.title,
        )
        session.add(state)
        await session.commit()
        return campaign.id


def _write_export_file(tmp_path: Path, market_id, campaign_id, job_id, file_format: str) -> str:
    storage_key = f"markets/{market_id}/campaigns/{campaign_id}/exports/{job_id}/campaign.{file_format}"
    path = tmp_path / storage_key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    return storage_key
