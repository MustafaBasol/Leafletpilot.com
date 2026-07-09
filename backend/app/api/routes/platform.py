from datetime import timedelta
from re import sub
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_catalog_session, get_current_platform_admin
from app.core.config import settings
from app.core.security import create_platform_access_token, generate_invitation_token, hash_invitation_token, verify_password
from app.models import ActivityLog, Campaign, Market, MarketInvitation, MarketUser, PlatformAdmin, Product, SignupRequest
from app.models.base import utc_now
from app.schemas.common import ListResponse
from app.schemas.platform import (
    LifecycleUpdateRequest,
    PlatformAdminRead,
    PlatformLoginRequest,
    PlatformLoginResponse,
    PlatformMarketDetail,
    PlatformMarketListItem,
    ProvisionMarketRequest,
    ProvisionMarketResponse,
    SignupRequestRead,
    SignupRequestUpdate,
)

router = APIRouter(prefix="/platform", tags=["platform"])


@router.post("/auth/login", response_model=PlatformLoginResponse)
async def platform_login(
    payload: PlatformLoginRequest,
    session: AsyncSession = Depends(get_catalog_session),
) -> PlatformLoginResponse:
    if not settings.platform_admin_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Platform admin devre dışı.")
    admin = await session.scalar(select(PlatformAdmin).where(PlatformAdmin.email == payload.email))
    if admin is None or not admin.is_active or not verify_password(payload.password, admin.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-posta veya şifre hatalı.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    admin.last_login_at = utc_now()
    await session.commit()
    await session.refresh(admin)
    token = create_platform_access_token(str(admin.id), timedelta(minutes=settings.platform_access_token_expire_minutes))
    return PlatformLoginResponse(access_token=token, admin=PlatformAdminRead.model_validate(admin))


@router.get("/auth/me", response_model=PlatformAdminRead)
async def platform_me(admin: PlatformAdmin = Depends(get_current_platform_admin)) -> PlatformAdminRead:
    return PlatformAdminRead.model_validate(admin)


@router.get("/signup-requests", response_model=ListResponse[SignupRequestRead])
async def list_signup_requests(
    status_filter: str | None = Query(default=None, alias="status"),
    search: str | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: PlatformAdmin = Depends(get_current_platform_admin),
    session: AsyncSession = Depends(get_catalog_session),
) -> ListResponse[SignupRequestRead]:
    statement = select(SignupRequest)
    count_statement = select(func.count()).select_from(SignupRequest)
    conditions = []
    if status_filter:
        conditions.append(SignupRequest.status == status_filter)
    if search:
        term = f"%{search.strip().lower()}%"
        conditions.append(
            or_(
                func.lower(SignupRequest.market_name).like(term),
                func.lower(SignupRequest.contact_name).like(term),
                func.lower(SignupRequest.email).like(term),
            )
        )
    for condition in conditions:
        statement = statement.where(condition)
        count_statement = count_statement.where(condition)
    total = await session.scalar(count_statement)
    result = await session.scalars(statement.order_by(SignupRequest.created_at.desc()).limit(limit).offset(offset))
    return ListResponse(items=list(result.all()), total=total or 0, limit=limit, offset=offset)


@router.get("/signup-requests/{request_id}", response_model=SignupRequestRead)
async def get_signup_request(
    request_id: UUID,
    _: PlatformAdmin = Depends(get_current_platform_admin),
    session: AsyncSession = Depends(get_catalog_session),
) -> SignupRequestRead:
    signup_request = await session.get(SignupRequest, request_id)
    if signup_request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Başvuru bulunamadı.")
    return signup_request


@router.patch("/signup-requests/{request_id}", response_model=SignupRequestRead)
async def update_signup_request(
    request_id: UUID,
    payload: SignupRequestUpdate,
    admin: PlatformAdmin = Depends(get_current_platform_admin),
    session: AsyncSession = Depends(get_catalog_session),
) -> SignupRequestRead:
    signup_request = await session.get(SignupRequest, request_id)
    if signup_request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Başvuru bulunamadı.")
    if signup_request.status == "provisioned":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Provision edilmiş başvuru değiştirilemez.")
    if payload.status == "rejected" and not (payload.rejection_reason or "").strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Ret nedeni gerekli.")
    signup_request.status = payload.status
    signup_request.rejection_reason = payload.rejection_reason.strip() if payload.rejection_reason else None
    signup_request.reviewed_by_platform_admin_id = admin.id
    signup_request.reviewed_at = utc_now()
    session.add(
        ActivityLog(
            entity_type="signup_request",
            entity_id=signup_request.id,
            action="signup_request_rejected" if payload.status == "rejected" else "signup_request_reviewed",
            description=f"Signup request {payload.status}",
            metadata_={"status": payload.status},
        )
    )
    await session.commit()
    await session.refresh(signup_request)
    return signup_request


@router.post("/signup-requests/{request_id}/provision", response_model=ProvisionMarketResponse)
async def provision_signup_request(
    request_id: UUID,
    payload: ProvisionMarketRequest,
    admin: PlatformAdmin = Depends(get_current_platform_admin),
    session: AsyncSession = Depends(get_catalog_session),
) -> ProvisionMarketResponse:
    try:
        ZoneInfo(payload.timezone)
    except ZoneInfoNotFoundError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Geçersiz timezone.") from None

    signup_request = await session.scalar(
        select(SignupRequest)
        .options(selectinload(SignupRequest.provisioned_market))
        .where(SignupRequest.id == request_id)
        .with_for_update()
    )
    if signup_request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Başvuru bulunamadı.")
    if signup_request.status == "rejected":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Reddedilmiş başvuru provision edilemez.")
    if signup_request.provisioned_market_id:
        return ProvisionMarketResponse(
            signup_request=SignupRequestRead.model_validate(signup_request),
            market_id=signup_request.provisioned_market_id,
            already_provisioned=True,
        )

    slug = await _unique_market_slug(session, payload.requested_slug or payload.final_market_name)
    now = utc_now()
    market = Market(
        name=payload.final_market_name.strip(),
        slug=slug,
        legal_name=payload.final_market_name.strip(),
        country_code=payload.country_code,
        city=signup_request.city,
        language=payload.preferred_language,
        currency=payload.currency,
        timezone=payload.timezone,
        contact_email=signup_request.email,
        contact_phone=signup_request.phone,
        lifecycle_status="trial",
        trial_ends_at=now + timedelta(days=payload.trial_length_days),
        onboarding_status="not_started",
        onboarding_step=1,
        is_active=True,
    )
    session.add(market)
    await session.flush()

    token = generate_invitation_token()
    invitation = MarketInvitation(
        market_id=market.id,
        email=signup_request.email,
        role="market_admin",
        token_hash=hash_invitation_token(token),
        status="pending",
        expires_at=now + timedelta(days=settings.invitation_expire_days),
        created_by_platform_admin_id=admin.id,
    )
    session.add(invitation)

    signup_request.status = "provisioned"
    signup_request.provisioned_market_id = market.id
    signup_request.reviewed_by_platform_admin_id = admin.id
    signup_request.reviewed_at = now
    signup_request.provisioned_at = now
    session.add(
        ActivityLog(
            market_id=market.id,
            entity_type="signup_request",
            entity_id=signup_request.id,
            action="market_provisioned",
            description=f"Market provisioned for {_mask_email(signup_request.email)}",
            metadata_={"market_id": str(market.id), "signup_request_id": str(signup_request.id)},
        )
    )
    await session.commit()
    await session.refresh(signup_request)
    accept_url = f"{settings.frontend_base_url.rstrip('/')}/#/accept-invitation?token={token}"
    return ProvisionMarketResponse(
        signup_request=SignupRequestRead.model_validate(signup_request),
        market_id=market.id,
        accept_url=accept_url,
    )


@router.get("/markets", response_model=ListResponse[PlatformMarketListItem])
async def list_platform_markets(
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: PlatformAdmin = Depends(get_current_platform_admin),
    session: AsyncSession = Depends(get_catalog_session),
) -> ListResponse[PlatformMarketListItem]:
    total = await session.scalar(select(func.count()).select_from(Market))
    result = await session.scalars(select(Market).order_by(Market.created_at.desc()).limit(limit).offset(offset))
    items = [await _market_item(session, market) for market in result.all()]
    return ListResponse(items=items, total=total or 0, limit=limit, offset=offset)


@router.get("/markets/{market_id}", response_model=PlatformMarketDetail)
async def get_platform_market(
    market_id: UUID,
    _: PlatformAdmin = Depends(get_current_platform_admin),
    session: AsyncSession = Depends(get_catalog_session),
) -> PlatformMarketDetail:
    market = await session.get(Market, market_id)
    if market is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Market bulunamadı.")
    item = await _market_item(session, market)
    return PlatformMarketDetail(**item.model_dump(), **_market_detail_fields(market))


@router.patch("/markets/{market_id}/lifecycle", response_model=PlatformMarketDetail)
async def update_market_lifecycle(
    market_id: UUID,
    payload: LifecycleUpdateRequest,
    admin: PlatformAdmin = Depends(get_current_platform_admin),
    session: AsyncSession = Depends(get_catalog_session),
) -> PlatformMarketDetail:
    market = await session.get(Market, market_id)
    if market is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Market bulunamadı.")
    if payload.lifecycle_status == "archived" and not payload.confirm_archive:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Arşivleme onayı gerekli.")
    if market.lifecycle_status not in {"trial", "active", "suspended"} and payload.lifecycle_status != "archived":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Bu lifecycle geçişi desteklenmiyor.")
    market.lifecycle_status = payload.lifecycle_status
    market.is_active = payload.lifecycle_status != "archived"
    session.add(
        ActivityLog(
            market_id=market.id,
            entity_type="market",
            entity_id=market.id,
            action="market_lifecycle_changed",
            description=f"Lifecycle changed to {payload.lifecycle_status}",
            metadata_={"status": payload.lifecycle_status, "platform_admin_id": str(admin.id)},
        )
    )
    await session.commit()
    await session.refresh(market)
    item = await _market_item(session, market)
    return PlatformMarketDetail(**item.model_dump(), **_market_detail_fields(market))


async def _unique_market_slug(session: AsyncSession, value: str) -> str:
    base = sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-") or "market"
    slug = base[:110]
    suffix = 1
    while await session.scalar(select(Market.id).where(Market.slug == slug)):
        suffix += 1
        slug = f"{base[:104]}-{suffix}"
    return slug


async def _market_item(session: AsyncSession, market: Market) -> PlatformMarketListItem:
    member_count = await session.scalar(select(func.count()).select_from(MarketUser).where(MarketUser.market_id == market.id))
    product_count = await session.scalar(select(func.count()).select_from(Product).where(Product.market_id == market.id))
    campaign_count = await session.scalar(select(func.count()).select_from(Campaign).where(Campaign.market_id == market.id))
    return PlatformMarketListItem(
        id=market.id,
        name=market.name,
        slug=market.slug,
        lifecycle_status=market.lifecycle_status,
        trial_ends_at=market.trial_ends_at,
        onboarding_status=market.onboarding_status,
        member_count=member_count or 0,
        product_count=product_count or 0,
        campaign_count=campaign_count or 0,
        created_at=market.created_at,
    )


def _market_detail_fields(market: Market) -> dict:
    return {
        "legal_name": market.legal_name,
        "country_code": market.country_code,
        "city": market.city,
        "language": market.language,
        "currency": market.currency,
        "timezone": market.timezone,
        "contact_email": market.contact_email,
        "contact_phone": market.contact_phone,
        "primary_color": market.primary_color,
        "secondary_color": market.secondary_color,
        "onboarding_step": market.onboarding_step,
        "onboarding_completed_at": market.onboarding_completed_at,
    }


def _mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}"
