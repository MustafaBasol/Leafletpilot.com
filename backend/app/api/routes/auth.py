from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_catalog_session, get_current_user
from app.api.routes.public import _is_throttled
from app.core.config import settings
from app.core.security import create_access_token, hash_invitation_token, hash_password, verify_password
from app.models import ActivityLog, Market, MarketInvitation, MarketUser, PlatformAuditLog, User
from app.models.base import utc_now
from app.schemas.auth import AuthMarketRead, AuthSessionRead, AuthUserRead, InvitationPreviewRequest, InvitationPreviewResponse, LoginRequest, LoginResponse
from app.schemas.team import AcceptInvitationAuthenticatedRequest, AcceptInvitationRequest

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    session: AsyncSession = Depends(get_catalog_session),
) -> LoginResponse:
    user = await _get_user_by_email(session, payload.email)
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-posta veya şifre hatalı.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        str(user.id),
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )
    session_payload = _build_session_payload(user)
    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        user=session_payload.user,
        markets=session_payload.markets,
    )


@router.get("/me", response_model=AuthSessionRead)
async def me(current_user: User = Depends(get_current_user)) -> AuthSessionRead:
    return _build_session_payload(current_user)


@router.post("/invitation-preview", response_model=InvitationPreviewResponse)
async def invitation_preview(
    payload: InvitationPreviewRequest,
    request: Request,
    session: AsyncSession = Depends(get_catalog_session),
) -> InvitationPreviewResponse:
    if await _is_throttled(session, request, payload.token[-16:]):
        await session.commit()
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many invitation attempts.")
    invitation = await _get_invitation_by_token(session, payload.token, lock=False)
    if invitation is None:
        await session.commit()
        return InvitationPreviewResponse(status="invalid")
    normalized = _validate_invitation_state(invitation)
    await session.commit()
    if normalized != "valid":
        return InvitationPreviewResponse(status=normalized)
    market = await session.get(Market, invitation.market_id)
    existing_user = await _get_user_by_email(session, invitation.email)
    return InvitationPreviewResponse(
        status="valid",
        email=invitation.email,
        market_name=market.name if market else None,
        role=invitation.role,
        expires_at=invitation.expires_at,
        requires_existing_login=existing_user is not None,
    )


@router.post("/accept-invitation", response_model=LoginResponse)
async def accept_invitation(
    payload: AcceptInvitationRequest,
    request: Request,
    session: AsyncSession = Depends(get_catalog_session),
) -> LoginResponse:
    if await _is_throttled(session, request, payload.token[-16:]):
        await session.commit()
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many invitation attempts.")
    invitation = await _get_valid_invitation(session, payload.token)
    existing_user = await _get_user_by_email(session, invitation.email)
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bu e-posta zaten kayıtlı. Mevcut kullanıcı giriş yapmalı.",
        )

    user = User(
        email=invitation.email,
        full_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password),
        is_active=True,
    )
    session.add(user)
    await session.flush()
    await _accept_invitation_for_user(session, invitation, user)
    await session.commit()
    return await _reload_login_response(session, user.id)


@router.post("/accept-invitation-authenticated", response_model=LoginResponse)
async def accept_invitation_authenticated(
    payload: AcceptInvitationAuthenticatedRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_catalog_session),
) -> AuthSessionRead:
    invitation = await _get_valid_invitation(session, payload.token, accepted_user_id=current_user.id)
    if invitation.status == "accepted" and invitation.accepted_by_user_id == current_user.id:
        return await _reload_login_response(session, current_user.id)
    if current_user.email.lower() != invitation.email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "invitation_email_mismatch",
                "message": "Davet e-postası oturumla eşleşmiyor.",
            },
        )
    await _accept_invitation_for_user(session, invitation, current_user)
    await session.commit()
    return await _reload_login_response(session, current_user.id)


async def _get_user_by_email(session: AsyncSession, email: str) -> User | None:
    return await session.scalar(
        select(User)
        .options(selectinload(User.market_memberships).selectinload(MarketUser.market))
        .where(User.email == email.lower())
    )


def _build_session_payload(user: User) -> AuthSessionRead:
    memberships = [
        membership
        for membership in user.market_memberships
        if (
            membership.is_active
            and membership.market is not None
            and membership.market.is_active
            and membership.market.lifecycle_status in {"trial", "active"}
        )
    ]
    markets = [
        AuthMarketRead(
            id=membership.market.id,
            name=membership.market.name,
            slug=membership.market.slug,
            role=membership.role,
            is_active=membership.market.is_active,
            lifecycle_status=membership.market.lifecycle_status,
            onboarding_status=membership.market.onboarding_status,
            onboarding_step=membership.market.onboarding_step,
        )
        for membership in memberships
    ]
    return AuthSessionRead(user=AuthUserRead.model_validate(user), markets=markets)


async def _get_invitation_by_token(session: AsyncSession, token: str, *, lock: bool) -> MarketInvitation | None:
    statement = select(MarketInvitation).where(MarketInvitation.token_hash == hash_invitation_token(token))
    if lock:
        statement = statement.with_for_update()
    return await session.scalar(statement)


def _validate_invitation_state(invitation: MarketInvitation) -> str:
    if invitation.status == "revoked":
        return "revoked"
    if invitation.status == "accepted":
        return "accepted"
    if invitation.status == "expired" or invitation.expires_at <= datetime.now(UTC):
        invitation.status = "expired"
        return "expired"
    if invitation.status == "failed":
        return "failed"
    if invitation.status not in {"pending", "sent"}:
        return "invalid"
    return "valid"


async def _get_valid_invitation(session: AsyncSession, token: str, accepted_user_id=None) -> MarketInvitation:
    invitation = await _get_invitation_by_token(session, token, lock=True)
    if invitation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Geçersiz davet.")
    state = _validate_invitation_state(invitation)
    if state == "valid":
        return invitation
    if state == "revoked":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="İptal edilmiş davet.")
    if state == "accepted":
        if accepted_user_id is not None and invitation.accepted_by_user_id == accepted_user_id:
            return invitation
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Daha önce kullanılmış davet.")
    if state == "expired":
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Süresi dolmuş davet.")
    if state == "failed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Davet e-postası gönderilemedi. Yeniden gönderim gerekli.")
    if state != "valid":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Davet kullanılamaz.")
    return invitation


async def _accept_invitation_for_user(
    session: AsyncSession,
    invitation: MarketInvitation,
    user: User,
) -> None:
    membership = await session.scalar(
        select(MarketUser).where(
            MarketUser.market_id == invitation.market_id,
            MarketUser.user_id == user.id,
        )
    )
    if membership is None:
        market = await session.get(Market, invitation.market_id)
        session.add(
            MarketUser(
                market_id=invitation.market_id,
                user_id=user.id,
                role=invitation.role,
                is_active=True,
            )
        )
        session.add(
            ActivityLog(
                market_id=invitation.market_id,
                user_id=user.id,
                entity_type="market_user",
                entity_id=user.id,
                action="owner_membership_created" if invitation.role == "market_admin" else "market_membership_created",
                description="Invitation membership created",
                metadata_={"role": invitation.role},
            )
        )
        session.add(
            PlatformAuditLog(
                actor_platform_admin_id=None,
                action="owner_membership_created" if invitation.role == "market_admin" else "market_membership_created",
                target_type="market",
                target_id=invitation.market_id,
                metadata_={"invitation_id": str(invitation.id), "role": invitation.role},
            )
        )
        if market is not None and market.onboarding_status == "not_started":
            market.onboarding_status = "in_progress"
            session.add(
                PlatformAuditLog(
                    actor_platform_admin_id=None,
                    action="onboarding_started",
                    target_type="market",
                    target_id=market.id,
                    metadata_={"invitation_id": str(invitation.id)},
                )
            )
    else:
        membership.is_active = True
        membership.role = invitation.role
    invitation.status = "accepted"
    invitation.accepted_by_user_id = user.id
    invitation.accepted_at = datetime.now(UTC)
    session.add(
        PlatformAuditLog(
            actor_platform_admin_id=None,
            action="invitation_accepted",
            target_type="market_invitation",
            target_id=invitation.id,
            metadata_={"market_id": str(invitation.market_id)},
        )
    )


async def _reload_session_payload(session: AsyncSession, user_id) -> AuthSessionRead:
    user = await session.scalar(
        select(User)
        .options(selectinload(User.market_memberships).selectinload(MarketUser.market))
        .where(User.id == user_id)
    )
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kullanıcı bulunamadı.")
    return _build_session_payload(user)


async def _reload_login_response(session: AsyncSession, user_id) -> LoginResponse:
    session_payload = await _reload_session_payload(session, user_id)
    access_token = create_access_token(
        str(session_payload.user.id),
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )
    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        user=session_payload.user,
        markets=session_payload.markets,
    )
