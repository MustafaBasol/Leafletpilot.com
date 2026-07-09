from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_catalog_session, get_current_user
from app.core.config import settings
from app.core.security import create_access_token, hash_invitation_token, hash_password, verify_password
from app.models import MarketInvitation, MarketUser, User
from app.schemas.auth import AuthMarketRead, AuthSessionRead, AuthUserRead, LoginRequest, LoginResponse
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


@router.post("/accept-invitation", response_model=AuthSessionRead)
async def accept_invitation(
    payload: AcceptInvitationRequest,
    session: AsyncSession = Depends(get_catalog_session),
) -> AuthSessionRead:
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
    return await _reload_session_payload(session, user.id)


@router.post("/accept-invitation-authenticated", response_model=AuthSessionRead)
async def accept_invitation_authenticated(
    payload: AcceptInvitationAuthenticatedRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_catalog_session),
) -> AuthSessionRead:
    invitation = await _get_valid_invitation(session, payload.token)
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
    return await _reload_session_payload(session, current_user.id)


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
        if membership.is_active and membership.market is not None and membership.market.is_active
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


async def _get_valid_invitation(session: AsyncSession, token: str) -> MarketInvitation:
    invitation = await session.scalar(
        select(MarketInvitation).where(MarketInvitation.token_hash == hash_invitation_token(token))
    )
    if invitation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Geçersiz davet.")
    if invitation.status == "revoked":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="İptal edilmiş davet.")
    if invitation.status == "accepted":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Daha önce kullanılmış davet.")
    if invitation.status == "expired" or invitation.expires_at <= datetime.now(UTC):
        invitation.status = "expired"
        await session.commit()
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Süresi dolmuş davet.")
    if invitation.status != "pending":
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
        session.add(
            MarketUser(
                market_id=invitation.market_id,
                user_id=user.id,
                role=invitation.role,
                is_active=True,
            )
        )
    else:
        membership.is_active = True
    invitation.status = "accepted"
    invitation.accepted_by_user_id = user.id
    invitation.accepted_at = datetime.now(UTC)


async def _reload_session_payload(session: AsyncSession, user_id) -> AuthSessionRead:
    user = await session.scalar(
        select(User)
        .options(selectinload(User.market_memberships).selectinload(MarketUser.market))
        .where(User.id == user_id)
    )
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kullanıcı bulunamadı.")
    return _build_session_payload(user)
