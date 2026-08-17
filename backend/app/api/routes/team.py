from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_catalog_session, get_current_market_membership, require_market_admin
from app.core.config import settings
from app.core.roles import MarketRole
from app.core.security import generate_invitation_token, hash_invitation_token
from app.models import Market, MarketInvitation, MarketUser, PasswordResetToken, User
from app.models.base import utc_now
from app.schemas.team import (
    MarketInvitationCreate,
    MarketInvitationCreateResponse,
    MarketInvitationRead,
    MarketMemberRead,
    MarketMemberUpdate,
    PasswordResetRequestResponse,
)
from app.services.invitation_email import (
    InvitationDeliveryDisabled,
    InvitationEmailError,
    OwnerInvitationEmail,
    PasswordResetEmail,
    send_owner_invitation_email,
    send_password_reset_email,
)

router = APIRouter(tags=["team"])

# Invitation statuses that block creating a second invitation for the same email+market —
# mirrors the partial unique DB index `uq_market_invitations_pending_market_email`.
ACTIVE_INVITATION_STATUSES = ("pending", "sent", "manual_delivery_required", "failed")
RESENDABLE_INVITATION_STATUSES = ("pending", "sent", "manual_delivery_required", "failed")


@router.get("/market-members", response_model=list[MarketMemberRead])
async def list_market_members(
    membership: MarketUser = Depends(require_market_admin),
    session: AsyncSession = Depends(get_catalog_session),
) -> list[MarketMemberRead]:
    result = await session.scalars(
        select(MarketUser)
        .options(selectinload(MarketUser.user))
        .where(MarketUser.market_id == membership.market_id)
        .join(User)
        .order_by(User.email)
    )
    return [_member_read(item) for item in result.unique().all()]


@router.patch("/market-members/{membership_id}", response_model=MarketMemberRead)
async def update_market_member(
    membership_id: UUID,
    payload: MarketMemberUpdate,
    membership: MarketUser = Depends(require_market_admin),
    session: AsyncSession = Depends(get_catalog_session),
) -> MarketMemberRead:
    target = await session.scalar(
        select(MarketUser)
        .options(selectinload(MarketUser.user))
        .where(MarketUser.id == membership_id, MarketUser.market_id == membership.market_id)
    )
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Üyelik bulunamadı.")
    if target.role == MarketRole.MARKET_ADMIN.value and payload.role != MarketRole.MARKET_ADMIN.value:
        await _ensure_not_last_admin(session, membership.market_id, target.id)
    target.role = payload.role
    await session.commit()
    await session.refresh(target)
    return _member_read(target)


@router.post("/market-members/{membership_id}/password-reset", response_model=PasswordResetRequestResponse)
async def request_member_password_reset(
    membership_id: UUID,
    membership: MarketUser = Depends(require_market_admin),
    session: AsyncSession = Depends(get_catalog_session),
) -> PasswordResetRequestResponse:
    """Admin-triggered password reset. Only ever sends a link — never displays, stores
    retrievably, or returns the member's existing password."""
    target = await session.scalar(
        select(MarketUser)
        .options(selectinload(MarketUser.user))
        .where(MarketUser.id == membership_id, MarketUser.market_id == membership.market_id)
    )
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Üyelik bulunamadı.")
    market = await session.get(Market, membership.market_id)
    if market is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Market bulunamadı.")

    token = generate_invitation_token()
    reset_token = PasswordResetToken(
        user_id=target.user_id,
        token_hash=hash_invitation_token(token),
        expires_at=datetime.now(UTC) + timedelta(minutes=settings.password_reset_expire_minutes),
        created_by_user_id=membership.user_id,
    )
    session.add(reset_token)
    await session.flush()
    delivery = await _send_password_reset_email(target.user.email, market.language, reset_token.expires_at, token)
    await session.commit()
    return PasswordResetRequestResponse(delivery=delivery)


@router.post(
    "/market-invitations",
    response_model=MarketInvitationCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_market_invitation(
    payload: MarketInvitationCreate,
    membership: MarketUser = Depends(require_market_admin),
    session: AsyncSession = Depends(get_catalog_session),
) -> MarketInvitationCreateResponse:
    email = payload.email.strip().lower()
    existing = await session.scalar(
        select(MarketInvitation).where(
            MarketInvitation.market_id == membership.market_id,
            MarketInvitation.email == email,
            MarketInvitation.status.in_(ACTIVE_INVITATION_STATUSES),
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bu e-posta için zaten aktif bir davet var. Mevcut daveti yeniden gönderebilir veya iptal edebilirsiniz.",
        )
    market = await session.get(Market, membership.market_id)
    if market is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Market bulunamadı.")
    token = generate_invitation_token()
    invitation = MarketInvitation(
        market_id=membership.market_id,
        email=email,
        role=payload.role,
        token_hash=hash_invitation_token(token),
        status="pending",
        expires_at=datetime.now(UTC) + timedelta(days=settings.invitation_expire_days),
        created_by_user_id=membership.user_id,
        send_count=0,
    )
    session.add(invitation)
    await session.flush()
    await _send_market_invitation(session, market, invitation, token)
    await session.commit()
    await session.refresh(invitation)
    accept_url = _accept_url(token)
    return MarketInvitationCreateResponse(
        **MarketInvitationRead.model_validate(invitation).model_dump(),
        invite_token=token,
        accept_url=accept_url,
    )


@router.post("/market-invitations/{invitation_id}/resend", response_model=MarketInvitationCreateResponse)
async def resend_market_invitation(
    invitation_id: UUID,
    membership: MarketUser = Depends(require_market_admin),
    session: AsyncSession = Depends(get_catalog_session),
) -> MarketInvitationCreateResponse:
    invitation = await session.scalar(
        select(MarketInvitation).where(
            MarketInvitation.id == invitation_id,
            MarketInvitation.market_id == membership.market_id,
        )
    )
    if invitation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Davet bulunamadı.")
    if invitation.status not in RESENDABLE_INVITATION_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bu davet yeniden gönderilemez.",
        )
    market = await session.get(Market, membership.market_id)
    if market is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Market bulunamadı.")
    # Plaintext tokens are never persisted (only their hash), so resending mints a fresh
    # token for the SAME invitation row rather than reusing an unrecoverable one — this also
    # refreshes the expiry and invalidates any previously-shared (possibly stale) link.
    token = generate_invitation_token()
    invitation.token_hash = hash_invitation_token(token)
    invitation.expires_at = datetime.now(UTC) + timedelta(days=settings.invitation_expire_days)
    await _send_market_invitation(session, market, invitation, token)
    await session.commit()
    await session.refresh(invitation)
    accept_url = _accept_url(token)
    return MarketInvitationCreateResponse(
        **MarketInvitationRead.model_validate(invitation).model_dump(),
        invite_token=token,
        accept_url=accept_url,
    )


@router.get("/market-invitations", response_model=list[MarketInvitationRead])
async def list_market_invitations(
    membership: MarketUser = Depends(require_market_admin),
    session: AsyncSession = Depends(get_catalog_session),
) -> list[MarketInvitationRead]:
    await _expire_pending_invitations(session, membership.market_id)
    result = await session.scalars(
        select(MarketInvitation)
        .where(MarketInvitation.market_id == membership.market_id)
        .order_by(MarketInvitation.created_at.desc())
    )
    return list(result.all())


@router.post("/market-invitations/{invitation_id}/revoke", response_model=MarketInvitationRead)
async def revoke_market_invitation(
    invitation_id: UUID,
    membership: MarketUser = Depends(require_market_admin),
    session: AsyncSession = Depends(get_catalog_session),
) -> MarketInvitationRead:
    invitation = await session.scalar(
        select(MarketInvitation).where(
            MarketInvitation.id == invitation_id,
            MarketInvitation.market_id == membership.market_id,
        )
    )
    if invitation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Davet bulunamadı.")
    if invitation.status not in ACTIVE_INVITATION_STATUSES:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Yalnızca aktif bir davet iptal edilebilir.")
    invitation.status = "revoked"
    invitation.revoked_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(invitation)
    return invitation


def _accept_url(token: str) -> str:
    return f"{settings.frontend_base_url.rstrip('/')}/#/accept-invitation?token={token}"


def _reset_password_url(token: str) -> str:
    return f"{settings.frontend_base_url.rstrip('/')}/#/reset-password?token={token}"


async def _send_password_reset_email(to_email: str, language: str, expires_at: datetime, token: str) -> str:
    """Attempt delivery and return the outcome as a string ('sent'/'manual_delivery_required'/
    'failed') — mirrors _send_market_invitation's status semantics. The reset token row is
    already flushed regardless of outcome, so a delivery failure never loses it; the admin
    can just trigger the action again to mint (and try sending) a fresh token."""
    try:
        delivery_result = await send_password_reset_email(
            PasswordResetEmail(
                to_email=to_email,
                reset_url=_reset_password_url(token),
                expires_at=expires_at,
                language=language,
            )
        )
    except InvitationEmailError:
        return "failed"
    if isinstance(delivery_result, InvitationDeliveryDisabled):
        return "manual_delivery_required"
    return "sent"


async def _send_market_invitation(
    session: AsyncSession,
    market: Market,
    invitation: MarketInvitation,
    token: str,
) -> None:
    """Attempt delivery and persist the outcome on the (already-flushed) invitation row.

    Mirrors platform.py's _send_owner_invitation status-transition pattern. A send failure
    never loses the invitation record — it's flushed/committed regardless of outcome, just
    with status set to reflect what actually happened, so it stays visible and resendable.
    """
    try:
        delivery_result = await send_owner_invitation_email(
            OwnerInvitationEmail(
                to_email=invitation.email,
                market_name=market.name,
                role=invitation.role,
                accept_url=_accept_url(token),
                expires_at=invitation.expires_at,
                language=market.language,
            )
        )
    except InvitationEmailError as exc:
        invitation.status = "failed"
        invitation.last_send_error = str(exc)
        return
    if isinstance(delivery_result, InvitationDeliveryDisabled):
        invitation.status = "manual_delivery_required"
        invitation.last_send_error = None
        return
    invitation.status = "sent"
    invitation.last_sent_at = utc_now()
    invitation.send_count = (invitation.send_count or 0) + 1
    invitation.last_send_error = None


async def _ensure_not_last_admin(session: AsyncSession, market_id: UUID, target_id: UUID) -> None:
    active_admins = await session.scalar(
        select(func.count()).select_from(MarketUser).where(
            MarketUser.market_id == market_id,
            MarketUser.role == MarketRole.MARKET_ADMIN.value,
            MarketUser.is_active.is_(True),
            MarketUser.id != target_id,
        )
    )
    if not active_admins:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Son aktif market yöneticisi değiştirilemez.",
        )


async def _expire_pending_invitations(session: AsyncSession, market_id: UUID) -> None:
    # Covers every status the create/resend duplicate-check treats as "active" — otherwise an
    # unresent "sent"/"manual_delivery_required"/"failed" invitation whose token lapses would
    # permanently block re-inviting that email (the DB unique index blocks it too).
    result = await session.scalars(
        select(MarketInvitation).where(
            MarketInvitation.market_id == market_id,
            MarketInvitation.status.in_(ACTIVE_INVITATION_STATUSES),
            MarketInvitation.expires_at <= datetime.now(UTC),
        )
    )
    expired = list(result.all())
    for invitation in expired:
        invitation.status = "expired"
    if expired:
        await session.commit()


def _member_read(membership: MarketUser) -> MarketMemberRead:
    return MarketMemberRead(
        membership_id=membership.id,
        user_id=membership.user_id,
        email=membership.user.email,
        full_name=membership.user.full_name,
        role=membership.role,
        is_active=membership.is_active,
        created_at=membership.created_at,
    )
