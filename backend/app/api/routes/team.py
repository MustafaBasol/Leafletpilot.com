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
from app.models import MarketInvitation, MarketUser, User
from app.schemas.team import (
    MarketInvitationCreate,
    MarketInvitationCreateResponse,
    MarketInvitationRead,
    MarketMemberRead,
    MarketMemberUpdate,
)

router = APIRouter(tags=["team"])


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
            MarketInvitation.status == "pending",
            MarketInvitation.expires_at > datetime.now(UTC),
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bu e-posta için bekleyen bir davet zaten var.",
        )
    token = generate_invitation_token()
    invitation = MarketInvitation(
        market_id=membership.market_id,
        email=email,
        role=payload.role,
        token_hash=hash_invitation_token(token),
        status="pending",
        expires_at=datetime.now(UTC) + timedelta(days=settings.invitation_expire_days),
        created_by_user_id=membership.user_id,
    )
    session.add(invitation)
    await session.commit()
    await session.refresh(invitation)
    accept_url = f"{settings.frontend_base_url.rstrip('/')}/#/accept-invitation?token={token}"
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
    if invitation.status != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Yalnızca bekleyen davet iptal edilebilir.")
    invitation.status = "revoked"
    invitation.revoked_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(invitation)
    return invitation


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
    result = await session.scalars(
        select(MarketInvitation).where(
            MarketInvitation.market_id == market_id,
            MarketInvitation.status == "pending",
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
