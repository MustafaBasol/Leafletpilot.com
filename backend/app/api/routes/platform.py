from datetime import UTC, datetime, timedelta
from re import sub
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from app.api.deps import get_catalog_session, get_current_platform_admin
from app.core.config import settings
from app.core.lifecycle import can_transition_lifecycle
from app.core.security import create_platform_access_token, generate_invitation_token, hash_invitation_token, verify_password
from app.models import ActivityLog, Campaign, Market, MarketInvitation, MarketUser, PlatformAdmin, PlatformAuditLog, Product, SignupRequest
from app.models.base import utc_now
from app.schemas.common import ListResponse
from app.schemas.platform import (
    LifecycleUpdateRequest,
    OwnerInvitationActionRequest,
    OwnerInvitationActionResponse,
    PlatformAdminRead,
    PlatformAuditLogRead,
    PlatformInvitationSummary,
    PlatformLoginRequest,
    PlatformLoginResponse,
    PlatformMarketDetail,
    PlatformMarketListItem,
    PlatformOverview,
    PlatformReadinessSummary,
    ProvisionMarketRequest,
    ProvisionMarketResponse,
    SignupRequestRead,
    SignupRequestUpdate,
)
from app.services.invitation_email import InvitationEmailError, OwnerInvitationEmail, send_owner_invitation_email

router = APIRouter(prefix="/platform", tags=["platform"])


@router.post("/auth/login", response_model=PlatformLoginResponse)
async def platform_login(
    payload: PlatformLoginRequest,
    session: AsyncSession = Depends(get_catalog_session),
) -> PlatformLoginResponse:
    if not settings.platform_admin_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Platform admin is disabled.")
    admin = await session.scalar(select(PlatformAdmin).where(PlatformAdmin.email == payload.email))
    if admin is None or not admin.is_active or not verify_password(payload.password, admin.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
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


@router.get("/overview", response_model=PlatformOverview)
async def platform_overview(
    _: PlatformAdmin = Depends(get_current_platform_admin),
    session: AsyncSession = Depends(get_catalog_session),
) -> PlatformOverview:
    pending_signup_count = await session.scalar(
        select(func.count()).select_from(SignupRequest).where(SignupRequest.status.in_(("pending", "reviewing", "approved")))
    )
    readiness = await _readiness_counts(session)
    return PlatformOverview(
        pending_signup_count=pending_signup_count or 0,
        markets_awaiting_owner=readiness.get("awaiting_owner", 0),
        markets_onboarding=readiness.get("onboarding", 0),
        ready_markets=readiness.get("ready", 0),
        suspended_markets=readiness.get("suspended", 0),
        recent_activity=await _recent_audit(session),
    )


@router.get("/audit", response_model=ListResponse[PlatformAuditLogRead])
async def list_platform_audit(
    target_type: str | None = None,
    target_id: UUID | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: PlatformAdmin = Depends(get_current_platform_admin),
    session: AsyncSession = Depends(get_catalog_session),
) -> ListResponse[PlatformAuditLogRead]:
    statement = select(PlatformAuditLog)
    count_statement = select(func.count()).select_from(PlatformAuditLog)
    if target_type:
        statement = statement.where(PlatformAuditLog.target_type == target_type)
        count_statement = count_statement.where(PlatformAuditLog.target_type == target_type)
    if target_id:
        statement = statement.where(PlatformAuditLog.target_id == target_id)
        count_statement = count_statement.where(PlatformAuditLog.target_id == target_id)
    total = await session.scalar(count_statement)
    result = await session.scalars(statement.order_by(PlatformAuditLog.created_at.desc()).limit(limit).offset(offset))
    return ListResponse(items=list(result.all()), total=total or 0, limit=limit, offset=offset)


@router.get("/signup-requests", response_model=ListResponse[SignupRequestRead])
async def list_signup_requests(
    status_filter: str | None = Query(default=None, alias="status"),
    search: str | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: PlatformAdmin = Depends(get_current_platform_admin),
    session: AsyncSession = Depends(get_catalog_session),
) -> ListResponse[SignupRequestRead]:
    if status_filter == "under_review":
        status_filter = "reviewing"
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signup request not found.")
    return signup_request


@router.patch("/signup-requests/{request_id}", response_model=SignupRequestRead)
async def update_signup_request(
    request_id: UUID,
    payload: SignupRequestUpdate,
    admin: PlatformAdmin = Depends(get_current_platform_admin),
    session: AsyncSession = Depends(get_catalog_session),
) -> SignupRequestRead:
    signup_request = await session.get(SignupRequest, request_id, with_for_update=True)
    if signup_request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signup request not found.")
    if signup_request.status == "provisioned":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Provisioned signup requests cannot be changed.")
    if signup_request.status == "rejected" and payload.status != "rejected":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Rejected signup requests cannot be reopened.")
    if payload.status == "rejected" and not (payload.rejection_reason or "").strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Rejection reason is required.")
    if payload.status != "rejected" and payload.rejection_reason:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Rejection reason is only valid when rejecting.")

    signup_request.status = payload.status
    signup_request.review_notes = payload.review_notes.strip() if payload.review_notes else None
    signup_request.rejection_reason = payload.rejection_reason.strip() if payload.rejection_reason else None
    signup_request.reviewed_by_platform_admin_id = admin.id
    signup_request.reviewed_at = utc_now()
    action = {
        "reviewing": "signup_request_review_started",
        "approved": "signup_request_approved",
        "rejected": "signup_request_rejected",
    }[payload.status]
    _add_activity(session, None, "signup_request", signup_request.id, action, {"status": payload.status})
    _add_platform_audit(
        session,
        admin,
        action,
        "signup_request",
        signup_request.id,
        {"status": payload.status, "has_review_notes": bool(signup_request.review_notes)},
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
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid timezone.") from None

    signup_request = await session.scalar(
        select(SignupRequest)
        .options(selectinload(SignupRequest.provisioned_market))
        .where(SignupRequest.id == request_id)
        .with_for_update()
    )
    if signup_request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signup request not found.")
    if signup_request.status == "rejected":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Rejected signup requests cannot be provisioned.")
    if signup_request.status not in {"approved", "provisioned"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Approve the signup request before provisioning.")
    if signup_request.provisioned_market_id:
        return ProvisionMarketResponse(
            signup_request=SignupRequestRead.model_validate(signup_request),
            market_id=signup_request.provisioned_market_id,
            already_provisioned=True,
        )

    slug = await _market_slug(session, payload.requested_slug or payload.final_market_name, explicit=bool(payload.requested_slug))
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
        lifecycle_updated_at=now,
        lifecycle_updated_by_platform_admin_id=admin.id,
        lifecycle_reason="Initial pilot provisioning",
        trial_ends_at=now + timedelta(days=payload.trial_length_days),
        onboarding_status="not_started",
        onboarding_step=1,
        is_active=True,
    )
    session.add(market)
    await session.flush()

    token, invitation = _new_owner_invitation(market.id, signup_request.email, admin.id, now)
    session.add(invitation)
    await session.flush()
    await _send_owner_invitation(session, admin, market, invitation, token, resend=False)

    signup_request.status = "provisioned"
    signup_request.provisioned_market_id = market.id
    signup_request.reviewed_by_platform_admin_id = admin.id
    signup_request.reviewed_at = now
    signup_request.provisioned_at = now
    _add_activity(session, market.id, "signup_request", signup_request.id, "market_provisioned", {"market_id": str(market.id)})
    _add_platform_audit(
        session,
        admin,
        "market_provisioned",
        "signup_request",
        signup_request.id,
        {"market_id": str(market.id), "signup_request_id": str(signup_request.id)},
    )
    _add_platform_audit(session, admin, "invitation_created", "market_invitation", invitation.id, {"market_id": str(market.id)})
    await session.commit()
    await session.refresh(signup_request)
    return ProvisionMarketResponse(
        signup_request=SignupRequestRead.model_validate(signup_request),
        market_id=market.id,
    )


@router.get("/markets", response_model=ListResponse[PlatformMarketListItem])
async def list_platform_markets(
    lifecycle_status: str | None = None,
    readiness: str | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: PlatformAdmin = Depends(get_current_platform_admin),
    session: AsyncSession = Depends(get_catalog_session),
) -> ListResponse[PlatformMarketListItem]:
    counts = _market_counts_subquery()
    latest_invitation, latest_invitation_subquery = _latest_owner_invitation_subquery()
    readiness_state = _readiness_state_expression(counts)
    base_conditions = []
    if lifecycle_status:
        base_conditions.append(Market.lifecycle_status == lifecycle_status)
    if readiness:
        base_conditions.append(readiness_state == readiness)

    total_from_clause = Market.__table__.outerjoin(counts, counts.c.market_id == Market.id)
    from_clause = (
        Market.__table__
        .outerjoin(counts, counts.c.market_id == Market.id)
        .outerjoin(latest_invitation_subquery, latest_invitation_subquery.c.market_id == Market.id)
        .outerjoin(latest_invitation, latest_invitation.id == latest_invitation_subquery.c.invitation_id)
    )
    total_statement = select(func.count()).select_from(total_from_clause)
    statement = (
        select(
            Market,
            latest_invitation,
            func.coalesce(counts.c.member_count, 0).label("member_count"),
            func.coalesce(counts.c.active_user_count, 0).label("active_user_count"),
            func.coalesce(counts.c.product_count, 0).label("product_count"),
            func.coalesce(counts.c.campaign_count, 0).label("campaign_count"),
        )
        .select_from(from_clause)
        .order_by(Market.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    for condition in base_conditions:
        total_statement = total_statement.where(condition)
        statement = statement.where(condition)

    total = await session.scalar(total_statement)
    rows = (await session.execute(statement)).all()
    items = [
        _market_item_from_counts(
            market,
            invitation,
            member_count=member_count,
            active_user_count=active_user_count,
            product_count=product_count,
            campaign_count=campaign_count,
        )
        for market, invitation, member_count, active_user_count, product_count, campaign_count in rows
    ]
    return ListResponse(items=items, total=total or 0, limit=limit, offset=offset)


@router.get("/markets/{market_id}", response_model=PlatformMarketDetail)
async def get_platform_market(
    market_id: UUID,
    _: PlatformAdmin = Depends(get_current_platform_admin),
    session: AsyncSession = Depends(get_catalog_session),
) -> PlatformMarketDetail:
    market = await session.get(Market, market_id)
    if market is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Market not found.")
    return await _market_detail(session, market)


@router.patch("/markets/{market_id}/lifecycle", response_model=PlatformMarketDetail)
async def update_market_lifecycle(
    market_id: UUID,
    payload: LifecycleUpdateRequest,
    admin: PlatformAdmin = Depends(get_current_platform_admin),
    session: AsyncSession = Depends(get_catalog_session),
) -> PlatformMarketDetail:
    market = await session.get(Market, market_id, with_for_update=True)
    if market is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Market not found.")
    if payload.lifecycle_status in {"suspended", "archived"} and not (payload.reason or "").strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="A reason is required.")
    if payload.lifecycle_status == "archived" and not payload.confirm_archive:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Archive confirmation is required.")
    if not can_transition_lifecycle(market.lifecycle_status, payload.lifecycle_status):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Unsupported lifecycle transition.")
    if market.lifecycle_status == payload.lifecycle_status:
        return await _market_detail(session, market)

    market.lifecycle_status = payload.lifecycle_status
    market.is_active = payload.lifecycle_status in {"trial", "active"}
    market.lifecycle_reason = payload.reason.strip() if payload.reason else None
    market.lifecycle_updated_at = utc_now()
    market.lifecycle_updated_by_platform_admin_id = admin.id
    action = {
        "active": "market_resumed",
        "suspended": "market_suspended",
        "archived": "market_archived",
    }[payload.lifecycle_status]
    _add_activity(session, market.id, "market", market.id, action, {"status": payload.lifecycle_status})
    _add_platform_audit(
        session,
        admin,
        action,
        "market",
        market.id,
        {"status": payload.lifecycle_status, "has_reason": bool(market.lifecycle_reason)},
    )
    await session.commit()
    await session.refresh(market)
    return await _market_detail(session, market)


@router.post("/markets/{market_id}/owner-invitation", response_model=OwnerInvitationActionResponse)
async def create_owner_invitation(
    market_id: UUID,
    payload: OwnerInvitationActionRequest,
    admin: PlatformAdmin = Depends(get_current_platform_admin),
    session: AsyncSession = Depends(get_catalog_session),
) -> OwnerInvitationActionResponse:
    market = await session.get(Market, market_id, with_for_update=True)
    if market is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Market not found.")
    pending = await _active_owner_invitation(session, market.id)
    if pending is not None:
        return OwnerInvitationActionResponse(invitation=_invitation_summary(pending))
    email = payload.email or market.contact_email
    if not email:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Owner email is required.")
    now = utc_now()
    token, invitation = _new_owner_invitation(market.id, email, admin.id, now)
    session.add(invitation)
    await session.flush()
    await _send_owner_invitation(session, admin, market, invitation, token, resend=False)
    _add_platform_audit(session, admin, "invitation_created", "market_invitation", invitation.id, {"market_id": str(market.id)})
    await session.commit()
    await session.refresh(invitation)
    return OwnerInvitationActionResponse(invitation=_invitation_summary(invitation))


@router.post("/markets/{market_id}/owner-invitation/rotate", response_model=OwnerInvitationActionResponse)
async def rotate_owner_invitation(
    market_id: UUID,
    payload: OwnerInvitationActionRequest,
    admin: PlatformAdmin = Depends(get_current_platform_admin),
    session: AsyncSession = Depends(get_catalog_session),
) -> OwnerInvitationActionResponse:
    market = await session.get(Market, market_id, with_for_update=True)
    if market is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Market not found.")
    pending = await _active_owner_invitation(session, market.id)
    if pending is not None:
        pending.status = "revoked"
        pending.revoked_at = utc_now()
    email = payload.email or (pending.email if pending else market.contact_email)
    if not email:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Owner email is required.")
    now = utc_now()
    token, invitation = _new_owner_invitation(market.id, email, admin.id, now)
    session.add(invitation)
    await session.flush()
    await _send_owner_invitation(session, admin, market, invitation, token, resend=True)
    _add_platform_audit(session, admin, "invitation_resent", "market_invitation", invitation.id, {"market_id": str(market.id)})
    await session.commit()
    await session.refresh(invitation)
    return OwnerInvitationActionResponse(invitation=_invitation_summary(invitation))


@router.post("/markets/{market_id}/owner-invitation/revoke", response_model=PlatformInvitationSummary)
async def revoke_owner_invitation(
    market_id: UUID,
    admin: PlatformAdmin = Depends(get_current_platform_admin),
    session: AsyncSession = Depends(get_catalog_session),
) -> PlatformInvitationSummary:
    invitation = await _effective_owner_invitation(session, market_id)
    if invitation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No effective owner invitation found.")
    invitation.status = "revoked"
    invitation.revoked_at = utc_now()
    _add_platform_audit(session, admin, "invitation_revoked", "market_invitation", invitation.id, {"market_id": str(market_id)})
    await session.commit()
    await session.refresh(invitation)
    return _invitation_summary(invitation)


async def _market_slug(session: AsyncSession, value: str, *, explicit: bool) -> str:
    base = sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-") or "market"
    slug = base[:110]
    if not await session.scalar(select(Market.id).where(Market.slug == slug)):
        return slug
    if explicit:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Requested market slug is already in use.")
    suffix = 2
    while suffix < 100:
        candidate = f"{base[:104]}-{suffix}"
        if not await session.scalar(select(Market.id).where(Market.slug == candidate)):
            return candidate
        suffix += 1
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Could not resolve a safe market slug.")


async def _market_item(session: AsyncSession, market: Market) -> PlatformMarketListItem:
    member_count = await session.scalar(select(func.count()).select_from(MarketUser).where(MarketUser.market_id == market.id))
    product_count = await session.scalar(select(func.count()).select_from(Product).where(Product.market_id == market.id))
    campaign_count = await session.scalar(select(func.count()).select_from(Campaign).where(Campaign.market_id == market.id))
    invitation = await _owner_invitation(session, market.id)
    readiness = await _readiness_summary(session, market, invitation=invitation)
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
        readiness=readiness,
        owner_invitation=_invitation_summary(invitation) if invitation else None,
        created_at=market.created_at,
    )


def _market_item_from_counts(
    market: Market,
    invitation: MarketInvitation | None,
    *,
    member_count: int,
    active_user_count: int,
    product_count: int,
    campaign_count: int,
) -> PlatformMarketListItem:
    readiness = _readiness_summary_from_counts(
        market,
        invitation,
        active_user_count=active_user_count,
        product_count=product_count,
    )
    return PlatformMarketListItem(
        id=market.id,
        name=market.name,
        slug=market.slug,
        lifecycle_status=market.lifecycle_status,
        trial_ends_at=market.trial_ends_at,
        onboarding_status=market.onboarding_status,
        member_count=member_count,
        product_count=product_count,
        campaign_count=campaign_count,
        readiness=readiness,
        owner_invitation=_invitation_summary(invitation) if invitation else None,
        created_at=market.created_at,
    )


async def _market_detail(session: AsyncSession, market: Market) -> PlatformMarketDetail:
    item = await _market_item(session, market)
    return PlatformMarketDetail(
        **item.model_dump(),
        legal_name=market.legal_name,
        country_code=market.country_code,
        city=market.city,
        language=market.language,
        currency=market.currency,
        timezone=market.timezone,
        contact_email=market.contact_email,
        contact_phone=market.contact_phone,
        primary_color=market.primary_color,
        secondary_color=market.secondary_color,
        onboarding_step=market.onboarding_step,
        onboarding_completed_at=market.onboarding_completed_at,
        lifecycle_reason=market.lifecycle_reason,
        lifecycle_updated_at=market.lifecycle_updated_at,
        lifecycle_updated_by_platform_admin_id=market.lifecycle_updated_by_platform_admin_id,
        recent_activity=await _recent_audit(session, target_type="market", target_id=market.id),
    )


async def _readiness_summary(
    session: AsyncSession,
    market: Market,
    *,
    invitation: MarketInvitation | None = None,
) -> PlatformReadinessSummary:
    if invitation is None:
        invitation = await _owner_invitation(session, market.id)
    active_users = await session.scalar(
        select(func.count()).select_from(MarketUser).where(MarketUser.market_id == market.id, MarketUser.is_active.is_(True))
    )
    product_count = await session.scalar(select(func.count()).select_from(Product).where(Product.market_id == market.id))
    return _readiness_summary_from_counts(
        market,
        invitation,
        active_user_count=active_users or 0,
        product_count=product_count or 0,
    )


def _readiness_summary_from_counts(
    market: Market,
    invitation: MarketInvitation | None,
    *,
    active_user_count: int,
    product_count: int,
) -> PlatformReadinessSummary:
    blockers = []
    has_active_user = bool(active_user_count)
    has_effective_invitation = invitation is not None and _invitation_is_effective(invitation)
    setup_complete = market.onboarding_status == "completed" and bool(product_count)
    if market.lifecycle_status in {"suspended", "archived"}:
        state = "suspended" if market.lifecycle_status == "suspended" else "blocked"
        blockers.append(f"Market lifecycle is {market.lifecycle_status}.")
    elif not has_active_user:
        state = "awaiting_owner"
        if not has_effective_invitation:
            blockers.append("No active owner user or effective owner invitation.")
    elif not setup_complete:
        state = "onboarding"
        blockers.append("Required market setup is not complete.")
    else:
        state = "ready"
    last_activity_at = max(
        [value for value in (market.updated_at, invitation.updated_at if invitation else None) if value is not None],
        default=None,
    )
    return PlatformReadinessSummary(
        state=state,
        blockers=blockers,
        has_active_market_user=has_active_user,
        required_setup_complete=setup_complete,
        last_activity_at=last_activity_at,
    )


def _market_counts_subquery():
    member_counts = (
        select(
            MarketUser.market_id.label("market_id"),
            func.count(MarketUser.id).label("member_count"),
            func.sum(case((MarketUser.is_active.is_(True), 1), else_=0)).label("active_user_count"),
        )
        .group_by(MarketUser.market_id)
        .subquery()
    )
    product_counts = (
        select(Product.market_id.label("market_id"), func.count(Product.id).label("product_count"))
        .group_by(Product.market_id)
        .subquery()
    )
    campaign_counts = (
        select(Campaign.market_id.label("market_id"), func.count(Campaign.id).label("campaign_count"))
        .group_by(Campaign.market_id)
        .subquery()
    )
    return (
        select(
            Market.id.label("market_id"),
            func.coalesce(member_counts.c.member_count, 0).label("member_count"),
            func.coalesce(member_counts.c.active_user_count, 0).label("active_user_count"),
            func.coalesce(product_counts.c.product_count, 0).label("product_count"),
            func.coalesce(campaign_counts.c.campaign_count, 0).label("campaign_count"),
        )
        .select_from(Market)
        .outerjoin(member_counts, member_counts.c.market_id == Market.id)
        .outerjoin(product_counts, product_counts.c.market_id == Market.id)
        .outerjoin(campaign_counts, campaign_counts.c.market_id == Market.id)
        .subquery()
    )


def _latest_owner_invitation_subquery():
    ranked = (
        select(
            MarketInvitation.id.label("invitation_id"),
            MarketInvitation.market_id.label("market_id"),
            func.row_number()
            .over(partition_by=MarketInvitation.market_id, order_by=MarketInvitation.created_at.desc())
            .label("rank"),
        )
        .where(MarketInvitation.role == "market_admin")
        .subquery()
    )
    latest = (
        select(ranked.c.market_id, ranked.c.invitation_id)
        .where(ranked.c.rank == 1)
        .subquery()
    )
    return aliased(MarketInvitation), latest


def _readiness_state_expression(counts):
    return case(
        (Market.lifecycle_status == "suspended", "suspended"),
        (Market.lifecycle_status == "archived", "blocked"),
        (func.coalesce(counts.c.active_user_count, 0) == 0, "awaiting_owner"),
        (
            or_(Market.onboarding_status != "completed", func.coalesce(counts.c.product_count, 0) == 0),
            "onboarding",
        ),
        else_="ready",
    )


async def _readiness_counts(session: AsyncSession) -> dict[str, int]:
    counts = _market_counts_subquery()
    readiness_state = _readiness_state_expression(counts).label("readiness_state")
    rows = (
        await session.execute(
            select(readiness_state, func.count())
            .select_from(Market)
            .outerjoin(counts, counts.c.market_id == Market.id)
            .group_by(readiness_state)
        )
    ).all()
    return {state: count for state, count in rows}


async def _owner_invitation(session: AsyncSession, market_id: UUID) -> MarketInvitation | None:
    return await session.scalar(
        select(MarketInvitation)
        .where(MarketInvitation.market_id == market_id, MarketInvitation.role == "market_admin")
        .order_by(MarketInvitation.created_at.desc())
    )


async def _effective_owner_invitation(session: AsyncSession, market_id: UUID) -> MarketInvitation | None:
    invitation = await session.scalar(
        select(MarketInvitation)
        .where(
            MarketInvitation.market_id == market_id,
            MarketInvitation.role == "market_admin",
            MarketInvitation.status.in_(("pending", "sent")),
        )
        .order_by(MarketInvitation.created_at.desc())
        .with_for_update()
    )
    if invitation is not None and invitation.expires_at <= datetime.now(UTC):
        invitation.status = "expired"
        return None
    return invitation


async def _active_owner_invitation(session: AsyncSession, market_id: UUID) -> MarketInvitation | None:
    invitation = await session.scalar(
        select(MarketInvitation)
        .where(
            MarketInvitation.market_id == market_id,
            MarketInvitation.role == "market_admin",
            MarketInvitation.status.in_(("pending", "sent", "failed")),
        )
        .order_by(MarketInvitation.created_at.desc())
        .with_for_update()
    )
    if invitation is not None and invitation.expires_at <= datetime.now(UTC):
        invitation.status = "expired"
        return None
    return invitation


def _new_owner_invitation(market_id: UUID, email: str, admin_id: UUID, now: datetime) -> tuple[str, MarketInvitation]:
    token = generate_invitation_token()
    invitation = MarketInvitation(
        market_id=market_id,
        email=email.strip().lower(),
        role="market_admin",
        token_hash=hash_invitation_token(token),
        status="pending",
        expires_at=now + timedelta(days=settings.invitation_expire_days),
        created_by_platform_admin_id=admin_id,
        send_count=0,
    )
    return token, invitation


async def _send_owner_invitation(
    session: AsyncSession,
    admin: PlatformAdmin,
    market: Market,
    invitation: MarketInvitation,
    token: str,
    *,
    resend: bool,
) -> None:
    try:
        await send_owner_invitation_email(
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
        _add_platform_audit(
            session,
            admin,
            "invitation_send_failed",
            "market_invitation",
            invitation.id,
            {"market_id": str(market.id), "resend": resend, "error": str(exc)},
        )
        return
    invitation.status = "sent"
    invitation.last_sent_at = utc_now()
    invitation.send_count = (invitation.send_count or 0) + 1
    invitation.last_send_error = None
    _add_platform_audit(
        session,
        admin,
        "invitation_sent",
        "market_invitation",
        invitation.id,
        {"market_id": str(market.id), "resend": resend},
    )


def _invitation_summary(invitation: MarketInvitation) -> PlatformInvitationSummary:
    return PlatformInvitationSummary(
        id=invitation.id,
        email=invitation.email,
        role=invitation.role,
        status=invitation.status,
        expires_at=invitation.expires_at,
        accepted_at=invitation.accepted_at,
        revoked_at=invitation.revoked_at,
        last_sent_at=invitation.last_sent_at,
        send_count=invitation.send_count or 0,
        created_at=invitation.created_at,
        delivery_status=_invitation_delivery_status(invitation),
        last_send_error=invitation.last_send_error,
        is_effective=_invitation_is_effective(invitation),
    )


def _invitation_is_effective(invitation: MarketInvitation) -> bool:
    return invitation.status in {"pending", "sent"} and invitation.expires_at > datetime.now(UTC)


def _invitation_delivery_status(invitation: MarketInvitation) -> str:
    if invitation.status == "failed":
        return "failed"
    if invitation.last_sent_at:
        return "sent"
    if invitation.status in {"accepted", "revoked", "expired"}:
        return invitation.status
    return "pending"


def _accept_url(token: str) -> str:
    return f"{settings.frontend_base_url.rstrip('/')}/#/accept-invitation?token={token}"


def _add_platform_audit(
    session: AsyncSession,
    admin: PlatformAdmin | None,
    action: str,
    target_type: str,
    target_id: UUID | None,
    metadata: dict | None = None,
) -> None:
    session.add(
        PlatformAuditLog(
            actor_platform_admin_id=admin.id if admin else None,
            action=action,
            target_type=target_type,
            target_id=target_id,
            metadata_=metadata or {},
        )
    )


def _add_activity(
    session: AsyncSession,
    market_id: UUID | None,
    entity_type: str,
    entity_id: UUID | None,
    action: str,
    metadata: dict | None = None,
) -> None:
    session.add(
        ActivityLog(
            market_id=market_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            description=action.replace("_", " "),
            metadata_=metadata or {},
        )
    )


async def _recent_audit(
    session: AsyncSession,
    *,
    target_type: str | None = None,
    target_id: UUID | None = None,
    limit: int = 10,
) -> list[PlatformAuditLog]:
    statement = select(PlatformAuditLog)
    if target_type:
        statement = statement.where(PlatformAuditLog.target_type == target_type)
    if target_id:
        statement = statement.where(PlatformAuditLog.target_id == target_id)
    result = await session.scalars(statement.order_by(PlatformAuditLog.created_at.desc()).limit(limit))
    return list(result.all())
