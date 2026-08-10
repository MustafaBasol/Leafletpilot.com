from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.core.config import settings
from app.core.database import Base
from app.models import Campaign, CampaignFile, CampaignItem, ExportJob, Market, Template
from app.services.rendering import (
    MISSING_CHROMIUM_MESSAGE,
    build_export_file_name,
    build_export_storage_key,
    normalize_requested_formats,
    render_campaign_export,
    render_error_message,
    storage_path_for_key,
    validate_rendered_file,
)


def test_rendering_builds_safe_file_names() -> None:
    campaign = Campaign(id=uuid4(), market_id=uuid4(), title="../Hafta 28 <Final>")

    assert build_export_file_name(campaign, "pdf") == f"hafta-28-final-{campaign.id}.pdf"


def test_rendering_builds_storage_key_without_absolute_paths() -> None:
    market_id = uuid4()
    campaign_id = uuid4()
    export_job_id = uuid4()

    storage_key = build_export_storage_key(
        market_id=market_id,
        campaign_id=campaign_id,
        export_job_id=export_job_id,
        file_name="campaign.pdf",
    )

    assert storage_key == (
        f"markets/{market_id}/campaigns/{campaign_id}/exports/{export_job_id}/campaign.pdf"
    )

    with pytest.raises(ValueError):
        build_export_storage_key(
            market_id=market_id,
            campaign_id=campaign_id,
            export_job_id=export_job_id,
            file_name="../campaign.pdf",
        )


def test_storage_path_for_key_stays_under_configured_root(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "local_storage_dir", str(tmp_path))

    path = storage_path_for_key("markets/m/campaigns/c/exports/e/file.pdf")

    assert path == tmp_path / "markets" / "m" / "campaigns" / "c" / "exports" / "e" / "file.pdf"

    with pytest.raises(ValueError):
        storage_path_for_key("../outside.pdf")

    with pytest.raises(ValueError):
        storage_path_for_key(str(tmp_path.parent / "outside.pdf"))


def test_normalize_requested_formats_rejects_unsupported_formats() -> None:
    assert normalize_requested_formats(["PDF", "png", "pdf"]) == ["pdf", "png"]

    with pytest.raises(HTTPException) as exc:
        normalize_requested_formats(["pdf", "docx"])

    assert exc.value.status_code == 422


def test_render_error_message_explains_missing_chromium() -> None:
    exc = RuntimeError("Executable doesn't exist at C:\\Users\\example\\chromium.exe")

    assert render_error_message(exc) == MISSING_CHROMIUM_MESSAGE


def test_validate_rendered_file_requires_existing_non_empty_file(tmp_path) -> None:
    missing_path = tmp_path / "missing.pdf"
    empty_path = tmp_path / "empty.pdf"
    ready_path = tmp_path / "ready.pdf"

    empty_path.write_bytes(b"")
    ready_path.write_bytes(b"%PDF-1.4")

    with pytest.raises(RuntimeError, match="did not create PDF"):
        validate_rendered_file(missing_path, "pdf")

    with pytest.raises(RuntimeError, match="empty PDF"):
        validate_rendered_file(empty_path, "pdf")

    validate_rendered_file(ready_path, "pdf")


@pytest.mark.asyncio
async def test_render_campaign_export_marks_job_failed_without_raising_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    """Phase 29: a Chromium/render failure must leave a consistent ExportJob
    status ('failed', no result files) and never expose a raw traceback to the
    caller - render_campaign_export swallows the exception by design so the
    Telegram layer can report a concise Turkish message instead."""
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed rendering test skipped.")

    engine = create_async_engine(settings.test_database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    market_id = uuid4()
    campaign_id = uuid4()
    export_job_id = uuid4()
    async with session_factory() as session:
        market = Market(id=market_id, name="Render Failure Market", slug=f"render-fail-{market_id}")
        template = Template(
            name="Supermarket Promo 4",
            slug="supermarket-promo-4",
            template_type="supermarket",
            is_global=True,
            is_active=True,
            status="published",
            visibility="shared",
            config_json={"layout": "supermarket-promo-4"},
        )
        session.add_all([market, template])
        await session.flush()
        campaign = Campaign(
            id=campaign_id,
            market_id=market_id,
            title="Render Failure Campaign",
            template_id=template.id,
        )
        campaign.items = [
            CampaignItem(
                id=uuid4(),
                market_id=market_id,
                raw_line="Su 5L - 8.90",
                incoming_name="Su 5L",
                price=Decimal("8.90"),
                sort_order=0,
                match_status="not_found",
            )
        ]
        export_job = ExportJob(
            id=export_job_id,
            campaign_id=campaign_id,
            market_id=market_id,
            job_type="final_export",
            status="queued",
            requested_formats=["pdf", "png"],
        )
        session.add_all([campaign, export_job])
        await session.commit()

    def failing_render_campaign_assets_sync(payload, **kwargs):
        raise RuntimeError("Executable doesn't exist at /fake/chromium")

    monkeypatch.setattr("app.services.rendering._render_campaign_assets_sync", failing_render_campaign_assets_sync)

    async with session_factory() as session:
        result = await render_campaign_export(
            session,
            market_id=market_id,
            campaign_id=campaign_id,
            requested_formats=["pdf", "png"],
            export_job_id=export_job_id,
        )

        assert result == []
        refreshed_job = await session.get(ExportJob, export_job_id)
        assert refreshed_job.status == "failed"
        assert refreshed_job.result_file_ids == []
        assert refreshed_job.error_message == MISSING_CHROMIUM_MESSAGE
        assert "Traceback" not in refreshed_job.error_message
        files = (
            await session.scalars(select(CampaignFile).where(CampaignFile.campaign_id == campaign_id))
        ).all()
        assert list(files) == []

    await engine.dispose()
