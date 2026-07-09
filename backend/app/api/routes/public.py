from datetime import timedelta

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
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

    throttle_key = _build_throttle_key(request, payload.email)
    if await _is_throttled(session, throttle_key):
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


def _build_throttle_key(request: Request, email: str) -> str:
    host = request.client.host if request.client else "unknown"
    return hash_signup_throttle_key(f"{host.lower()}:{email.lower()}")


async def _is_throttled(session: AsyncSession, key_hash: str) -> bool:
    now = utc_now()
    window_start = now - timedelta(minutes=settings.public_signup_throttle_window_minutes)
    throttle = await session.scalar(
        select(SignupThrottle)
        .where(SignupThrottle.key_hash == key_hash, SignupThrottle.window_started_at >= window_start)
        .order_by(SignupThrottle.window_started_at.desc())
        .with_for_update()
    )
    if throttle is None:
        session.add(SignupThrottle(key_hash=key_hash, window_started_at=now, request_count=1))
        return False
    throttle.request_count += 1
    return throttle.request_count > settings.public_signup_throttle_limit


def _mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}"
