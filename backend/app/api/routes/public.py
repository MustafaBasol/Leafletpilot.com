from datetime import UTC, datetime, timedelta
from ipaddress import ip_address, ip_network

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_catalog_session
from app.core.config import settings
from app.core.security import hash_signup_throttle_key
from app.models import ActivityLog, SignupRequest, SignupThrottle
from app.models.base import utc_now
from app.schemas.platform import PublicSignupAccepted, PublicSignupRequestCreate

router = APIRouter(prefix="/public", tags=["public"])


@router.post("/signup-requests", response_model=PublicSignupAccepted, status_code=status.HTTP_202_ACCEPTED)
async def create_public_signup_request(
    payload: PublicSignupRequestCreate,
    request: Request,
    session: AsyncSession = Depends(get_catalog_session),
) -> PublicSignupAccepted:
    accepted = PublicSignupAccepted()
    if payload.website:
        return accepted
    if not payload.consent_accepted:
        from fastapi import HTTPException

        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Onay gerekli.")

    if await _is_throttled(session, request, payload.email):
        await session.commit()
        return accepted

    now = utc_now()
    signup_request = SignupRequest(
        market_name=payload.market_name.strip(),
        contact_name=payload.contact_name.strip(),
        email=payload.email,
        phone=payload.phone.strip() if payload.phone else None,
        country_code=payload.country_code,
        city=payload.city.strip() if payload.city else None,
        preferred_language=payload.preferred_language.strip().lower(),
        expected_campaigns_per_month=payload.expected_campaigns_per_month,
        notes=payload.notes.strip() if payload.notes else None,
        consent_accepted=True,
        consent_accepted_at=now,
        status="pending",
    )
    session.add(signup_request)
    await session.flush()
    session.add(
        ActivityLog(
            entity_type="signup_request",
            entity_id=signup_request.id,
            action="signup_request_received",
            description=f"Signup request received for {_mask_email(payload.email)}",
            metadata_={"email_domain": payload.email.split("@")[-1], "country_code": payload.country_code},
        )
    )
    await session.commit()
    return accepted


async def _is_throttled(session: AsyncSession, request: Request, email: str) -> bool:
    now = utc_now()
    window_seconds = settings.public_signup_throttle_window_minutes * 60
    window_bucket = int(now.timestamp()) // window_seconds
    window_started_at = datetime.fromtimestamp(window_bucket * window_seconds, tz=UTC)
    cutoff_bucket = window_bucket - 48
    await session.execute(delete(SignupThrottle).where(SignupThrottle.window_bucket < cutoff_bucket))

    address = _client_address(request)
    counts = [
        await _increment_throttle(session, "ip", address, window_bucket, window_started_at),
        await _increment_throttle(session, "email", email.strip().lower(), window_bucket, window_started_at),
    ]
    return any(count > settings.public_signup_throttle_limit for count in counts)


async def _increment_throttle(
    session: AsyncSession,
    key_type: str,
    raw_value: str,
    window_bucket: int,
    window_started_at: datetime,
) -> int:
    key_hash = hash_signup_throttle_key(f"{key_type}:{raw_value}")
    statement = (
        insert(SignupThrottle)
        .values(
            key_type=key_type,
            key_hash=key_hash,
            window_bucket=window_bucket,
            window_started_at=window_started_at,
            request_count=1,
        )
        .on_conflict_do_update(
            constraint="uq_signup_throttles_type_key_bucket",
            set_={
                "request_count": SignupThrottle.request_count + 1,
                "updated_at": utc_now(),
            },
        )
        .returning(SignupThrottle.request_count)
    )
    return int(await session.scalar(statement) or 1)


def _client_address(request: Request) -> str:
    direct = request.client.host if request.client else "unknown"
    if not settings.trusted_proxy_ips or not _is_trusted_proxy(direct):
        return direct.lower()
    forwarded_for = request.headers.get("x-forwarded-for", "")
    first_forwarded = forwarded_for.split(",", 1)[0].strip()
    if not first_forwarded:
        return direct.lower()
    try:
        return str(ip_address(first_forwarded))
    except ValueError:
        return direct.lower()


def _is_trusted_proxy(value: str) -> bool:
    try:
        candidate = ip_address(value)
    except ValueError:
        return False
    for configured in settings.trusted_proxy_ips:
        try:
            if candidate in ip_network(configured, strict=False):
                return True
        except ValueError:
            if configured == value:
                return True
    return False


def _mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}"
