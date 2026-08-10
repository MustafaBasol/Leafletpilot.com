from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select, text

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models import Template
from app.services.template_presets import SUPERMARKET_PRESETS

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": settings.app_name,
    }


@router.get("/health/db")
async def database_health() -> dict[str, str]:
    if AsyncSessionLocal is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DATABASE_URL is not configured.",
        )

    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not reachable.",
        ) from exc

    return {
        "status": "ok",
        "service": settings.app_name,
        "database": "ok",
    }


@router.get("/health/readiness")
async def readiness() -> dict[str, object]:
    """First-customer readiness snapshot: DB, storage, Telegram config, and the
    published supermarket presets the automated Telegram flow depends on.

    Deliberately excludes an actual Chromium launch/render (too slow for a
    hot health check); use `scripts/readiness_check.py` for that before a
    production deploy.
    """
    checks: dict[str, dict[str, object]] = {
        "database": await _check_database(),
        "storage": _check_storage(),
        "telegram_config": _check_telegram_config(),
        "supermarket_templates": await _check_supermarket_templates(),
    }
    all_ok = all(check["ok"] for check in checks.values())
    body = {"status": "ok" if all_ok else "degraded", "service": settings.app_name, "checks": checks}
    if not all_ok:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=body)
    return body


async def _check_database() -> dict[str, object]:
    if AsyncSessionLocal is None:
        return {"ok": False, "detail": "DATABASE_URL is not configured."}
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        return {"ok": False, "detail": "Database is not reachable."}
    return {"ok": True}


def _check_storage() -> dict[str, object]:
    try:
        root = settings.local_storage_path
        root.mkdir(parents=True, exist_ok=True)
        probe = root / f".readiness-{uuid4()}.tmp"
        probe.write_bytes(b"ok")
        probe.unlink()
    except OSError:
        return {"ok": False, "detail": "Local storage path is not writable."}
    return {"ok": True}


def _check_telegram_config() -> dict[str, object]:
    if not settings.telegram_bot_enabled:
        return {"ok": True, "enabled": False}
    # Settings() already validates token/secret/webhook-url presence and
    # shape at process startup when telegram_bot_enabled is true, so if the
    # app booted, these are known-present. Report booleans only, never values.
    return {
        "ok": True,
        "enabled": True,
        "bot_token_configured": bool(settings.telegram_bot_token.strip()),
        "webhook_secret_configured": bool(settings.telegram_webhook_secret.strip()),
        "webhook_base_url_configured": bool(settings.telegram_webhook_base_url.strip()),
    }


async def _check_supermarket_templates() -> dict[str, object]:
    if AsyncSessionLocal is None:
        return {"ok": False, "detail": "DATABASE_URL is not configured."}
    slugs = sorted(str(preset["slug"]) for preset in SUPERMARKET_PRESETS.values())
    try:
        async with AsyncSessionLocal() as session:
            published = await session.scalars(
                select(Template.slug).where(
                    Template.slug.in_(slugs),
                    Template.market_id.is_(None),
                    Template.is_active.is_(True),
                    Template.status == "published",
                )
            )
            published_slugs = set(published.all())
    except Exception:
        return {"ok": False, "detail": "Could not query template presets."}
    missing = [slug for slug in slugs if slug not in published_slugs]
    if missing:
        return {"ok": False, "detail": f"Missing published global presets: {', '.join(missing)}"}
    return {"ok": True, "published_presets": slugs}
