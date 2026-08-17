"""Market-scoped endpoints for the central LeafletPilot WhatsApp channel.

Thin routing layer only: every rule (IDOR guards, admin-or-self authorization,
rate limiting, code generation, audit logging) lives in
`app/services/whatsapp_identity.py`. Routes here do dependency wiring,
request/response shaping, and commit the transaction the service staged.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

import phonenumbers
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_catalog_session, get_current_market_membership
from app.core.config import settings
from app.core.roles import MarketRole
from app.models import MarketUser
from app.schemas.whatsapp import (
    WhatsAppChannelStatusRead,
    WhatsAppRevokeRequest,
    WhatsAppVerificationCreateRequest,
    WhatsAppVerificationCreateResponse,
    WhatsAppVerificationRead,
)
from app.services.whatsapp_identity import (
    build_whatsapp_deep_link,
    cancel_verification,
    get_verification,
    list_market_whatsapp_status,
    request_verification,
    revoke_membership_whatsapp,
)

router = APIRouter(prefix="/integrations/whatsapp", tags=["whatsapp"])


@router.get("/status", response_model=WhatsAppChannelStatusRead)
async def get_whatsapp_status(
    membership: MarketUser = Depends(get_current_market_membership),
    session: AsyncSession = Depends(get_catalog_session),
) -> WhatsAppChannelStatusRead:
    can_manage_members = membership.role == MarketRole.MARKET_ADMIN.value
    members = await list_market_whatsapp_status(
        session,
        membership.market_id,
        current_user_id=membership.user_id,
        can_manage=can_manage_members,
    )
    official_number = settings.leafletpilot_whatsapp_number.strip() or None
    return WhatsAppChannelStatusRead(
        enabled=settings.evolution_whatsapp_enabled,
        configured=bool(official_number),
        official_number=official_number,
        official_number_display=_format_official_number(official_number),
        verification_expire_minutes=settings.whatsapp_verification_expire_minutes,
        resend_cooldown_seconds=settings.whatsapp_verification_resend_cooldown_seconds,
        can_manage_members=can_manage_members,
        members=members,
    )


@router.post(
    "/verifications",
    response_model=WhatsAppVerificationCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_whatsapp_verification(
    payload: WhatsAppVerificationCreateRequest,
    membership: MarketUser = Depends(get_current_market_membership),
    session: AsyncSession = Depends(get_catalog_session),
) -> WhatsAppVerificationCreateResponse:
    verification, code = await request_verification(
        session,
        market_id=membership.market_id,
        membership_id=payload.membership_id,
        actor_user_id=membership.user_id,
        actor_is_market_admin=membership.role == MarketRole.MARKET_ADMIN.value,
        claimed_phone=payload.phone,
        market_country_code=membership.market.country_code,
    )
    await session.commit()
    await session.refresh(verification)

    official_number = settings.leafletpilot_whatsapp_number.strip()
    resend_available_at = verification.created_at + timedelta(
        seconds=settings.whatsapp_verification_resend_cooldown_seconds
    )
    return WhatsAppVerificationCreateResponse(
        verification_id=verification.id,
        membership_id=verification.membership_id,
        user_id=verification.user_id,
        code=code,
        expires_at=verification.expires_at,
        official_number=official_number,
        official_number_display=_format_official_number(official_number) or official_number,
        whatsapp_deep_link=build_whatsapp_deep_link(official_number, code),
        resend_available_at=resend_available_at,
    )


@router.get("/verifications/{verification_id}", response_model=WhatsAppVerificationRead)
async def get_whatsapp_verification(
    verification_id: UUID,
    membership: MarketUser = Depends(get_current_market_membership),
    session: AsyncSession = Depends(get_catalog_session),
) -> WhatsAppVerificationRead:
    return await get_verification(
        session,
        verification_id,
        market_id=membership.market_id,
        actor_user_id=membership.user_id,
        actor_is_market_admin=membership.role == MarketRole.MARKET_ADMIN.value,
    )


@router.post(
    "/verifications/{verification_id}/cancel",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def cancel_whatsapp_verification(
    verification_id: UUID,
    membership: MarketUser = Depends(get_current_market_membership),
    session: AsyncSession = Depends(get_catalog_session),
) -> None:
    await cancel_verification(
        session,
        verification_id,
        market_id=membership.market_id,
        actor_user_id=membership.user_id,
        actor_is_market_admin=membership.role == MarketRole.MARKET_ADMIN.value,
    )
    await session.commit()


@router.post(
    "/members/{membership_id}/revoke",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_whatsapp_member(
    membership_id: UUID,
    payload: WhatsAppRevokeRequest,
    membership: MarketUser = Depends(get_current_market_membership),
    session: AsyncSession = Depends(get_catalog_session),
) -> None:
    await revoke_membership_whatsapp(
        session,
        market_id=membership.market_id,
        membership_id=membership_id,
        actor_user_id=membership.user_id,
        actor_is_market_admin=membership.role == MarketRole.MARKET_ADMIN.value,
        reason=payload.reason,
    )
    await session.commit()


def _format_official_number(number_e164: str | None) -> str | None:
    """Human-spaced rendering, e.g. "+33 6 12 34 56 78". Falls back to the raw
    E.164 string whenever libphonenumber can't confidently parse/format it."""
    if not number_e164:
        return None
    try:
        parsed = phonenumbers.parse(number_e164, None)
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
    except phonenumbers.NumberParseException:
        return number_e164
