from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_catalog_session, get_current_user
from app.core.config import settings
from app.core.security import create_access_token, verify_password
from app.models import MarketUser, User
from app.schemas.auth import AuthMarketRead, AuthSessionRead, AuthUserRead, LoginRequest, LoginResponse

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
        )
        for membership in memberships
    ]
    return AuthSessionRead(user=AuthUserRead.model_validate(user), markets=markets)
