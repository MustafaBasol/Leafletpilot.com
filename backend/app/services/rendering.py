from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models import Campaign, CampaignFile, CampaignItem, ExportJob, Product
from app.services.preview_renderer import (
    render_campaign_preview_html,
)

logger = logging.getLogger(__name__)

MISSING_CHROMIUM_MESSAGE = "Playwright Chromium is not installed. Run: python -m playwright install chromium"
SUPPORTED_EXPORT_FORMATS = {"pdf", "png"}
FORMAT_FILE_TYPES = {
    "pdf": "brochure_pdf",
    "png": "brochure_png",
}
FORMAT_MEDIA_TYPES = {
    "pdf": "application/pdf",
    "png": "image/png",
}


def normalize_requested_formats(requested_formats: list[str] | None) -> list[str]:
    formats = requested_formats or ["pdf", "png"]
    normalized = []
    for item in formats:
        value = str(item).strip().lower()
        if value not in SUPPORTED_EXPORT_FORMATS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unsupported export format: {item}. Supported formats: pdf, png.",
            )
        if value not in normalized:
            normalized.append(value)
    return normalized


def build_export_file_name(campaign: Campaign, file_format: str) -> str:
    safe_title = re.sub(r"[^a-zA-Z0-9._-]+", "-", campaign.title.strip()).strip(".-").lower()
    if not safe_title:
        safe_title = "campaign"
    return f"{safe_title}-{campaign.id}.{file_format}"


def build_export_storage_key(
    *,
    market_id: UUID,
    campaign_id: UUID,
    export_job_id: UUID,
    file_name: str,
) -> str:
    safe_file_name = Path(file_name).name
    if safe_file_name != file_name or not safe_file_name:
        raise ValueError("Invalid export file name.")
    return "/".join(
        [
            "markets",
            str(market_id),
            "campaigns",
            str(campaign_id),
            "exports",
            str(export_job_id),
            safe_file_name,
        ]
    )


def storage_path_for_key(storage_key: str) -> Path:
    parts = Path(storage_key).parts
    if Path(storage_key).is_absolute() or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("Invalid storage key.")

    root = settings.local_storage_path
    path = (root / Path(*parts)).resolve()
    if path != root and root not in path.parents:
        raise ValueError("Storage key escapes local storage directory.")
    return path


async def render_campaign_export(
    session: AsyncSession,
    *,
    market_id: UUID,
    campaign_id: UUID,
    requested_formats: list[str] | None,
    export_job_id: UUID,
    commit: bool = True,
) -> list[CampaignFile]:
    formats = normalize_requested_formats(requested_formats)
    export_job = await session.get(ExportJob, export_job_id)
    if export_job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export job not found.")

    campaign = await _get_campaign_for_render(session, campaign_id, market_id)
    export_job.status = "running"
    export_job.attempts = (export_job.attempts or 0) + 1
    export_job.started_at = datetime.now(UTC)
    export_job.error_message = None
    await session.flush()

    created_files: list[CampaignFile] = []
    try:
        generated_at = datetime.now(UTC).replace(microsecond=0)
        template = campaign.template
        html = render_campaign_preview_html(campaign, template, generated_at=generated_at)

        for file_format in formats:
            file_name = build_export_file_name(campaign, file_format)
            storage_key = build_export_storage_key(
                market_id=market_id,
                campaign_id=campaign_id,
                export_job_id=export_job_id,
                file_name=file_name,
            )
            output_path = storage_path_for_key(storage_key)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            if file_format == "pdf":
                await render_html_to_pdf(html, output_path)
            else:
                await render_html_to_png(html, output_path)
            validate_rendered_file(output_path, file_format)

            campaign_file = CampaignFile(
                campaign_id=campaign.id,
                market_id=campaign.market_id,
                file_type=FORMAT_FILE_TYPES[file_format],
                format=file_format,
                status="ready",
                storage_key=storage_key,
                size_bytes=output_path.stat().st_size,
            )
            session.add(campaign_file)
            created_files.append(campaign_file)

        await session.flush()
        export_job.status = "completed"
        export_job.completed_at = datetime.now(UTC)
        export_job.failed_at = None
        export_job.result_file_ids = [str(file.id) for file in created_files]
        if commit:
            await session.commit()
        else:
            await session.flush()

        for campaign_file in created_files:
            await session.refresh(campaign_file)
        await session.refresh(export_job)
        return created_files
    except Exception as exc:
        error_message = render_error_message(exc)
        logger.exception(
            "Campaign export rendering failed. market_id=%s campaign_id=%s export_job_id=%s",
            market_id,
            campaign_id,
            export_job_id,
        )
        if commit:
            await session.rollback()
            failed_job = await session.get(ExportJob, export_job_id)
            if failed_job is None:
                raise
        else:
            failed_job = export_job
        failed_job.status = "failed"
        failed_job.error_message = error_message
        failed_job.failed_at = datetime.now(UTC)
        failed_job.completed_at = None
        failed_job.result_file_ids = []
        if commit:
            await session.commit()
        else:
            await session.flush()
        await session.refresh(failed_job)
        return []


async def render_html_to_pdf(html: str, output_path: Path) -> None:
    await asyncio.to_thread(render_html_to_pdf_sync, html, output_path)


def render_html_to_pdf_sync(html: str, output_path: Path) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1240, "height": 1754})
            page.set_content(html, wait_until="networkidle")
            page.pdf(path=str(output_path), format="A4", print_background=True)
        finally:
            browser.close()


async def render_html_to_png(html: str, output_path: Path) -> None:
    await asyncio.to_thread(render_html_to_png_sync, html, output_path)


def render_html_to_png_sync(html: str, output_path: Path) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1240, "height": 1754}, device_scale_factor=1)
            page.set_content(html, wait_until="networkidle")
            page.screenshot(path=str(output_path), full_page=True)
        finally:
            browser.close()


def validate_rendered_file(output_path: Path, file_format: str) -> None:
    if not output_path.exists():
        raise RuntimeError(f"Export renderer did not create {file_format.upper()} file.")
    if output_path.stat().st_size <= 0:
        raise RuntimeError(f"Export renderer created an empty {file_format.upper()} file.")
    expected = b"%PDF-" if file_format == "pdf" else b"\x89PNG\r\n\x1a\n"
    if not output_path.read_bytes()[:8].startswith(expected):
        raise RuntimeError(f"Export renderer created an invalid {file_format.upper()} signature.")


def render_error_message(exc: Exception) -> str:
    message = str(exc).strip()
    if is_missing_chromium_error(message):
        return MISSING_CHROMIUM_MESSAGE
    return message or f"{type(exc).__name__}: export rendering failed."


def is_missing_chromium_error(message: str) -> bool:
    normalized = message.lower()
    return (
        "executable doesn't exist" in normalized
        or "browser executable" in normalized
        or "playwright install chromium" in normalized
        or "playwright was just installed or updated" in normalized
    )


async def _get_campaign_for_render(session: AsyncSession, campaign_id: UUID, market_id: UUID) -> Campaign:
    statement = (
        select(Campaign)
        .options(
            selectinload(Campaign.items).selectinload(CampaignItem.matching_suggestions),
            selectinload(Campaign.items).selectinload(CampaignItem.product).selectinload(Product.images),
            selectinload(Campaign.items).selectinload(CampaignItem.product).selectinload(Product.brand),
            selectinload(Campaign.template),
            selectinload(Campaign.market),
        )
        .where(Campaign.id == campaign_id, Campaign.market_id == market_id)
    )
    campaign = await session.scalar(statement)
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found.")
    return campaign
