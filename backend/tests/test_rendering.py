from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.models import Campaign
from app.services.rendering import (
    MISSING_CHROMIUM_MESSAGE,
    build_export_file_name,
    build_export_storage_key,
    render_error_message,
    normalize_requested_formats,
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
