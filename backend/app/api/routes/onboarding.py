from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.api.deps import DeferredCatalogSession, get_deferred_catalog_session, require_market_admin
from app.models import ActivityLog, Market, MarketUser, PlatformAuditLog, Product, Template
from app.models.base import utc_now
from app.schemas.onboarding import (
    OnboardingBrandUpdate,
    OnboardingProfileUpdate,
    OnboardingStateRead,
    OnboardingTemplateUpdate,
)

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.get("", response_model=OnboardingStateRead)
async def get_onboarding_state(membership: MarketUser = Depends(require_market_admin)) -> OnboardingStateRead:
    return _read(membership.market)


@router.patch("/profile", response_model=OnboardingStateRead)
async def update_onboarding_profile(
    payload: OnboardingProfileUpdate,
    membership: MarketUser = Depends(require_market_admin),
    deferred_session: DeferredCatalogSession = Depends(get_deferred_catalog_session),
) -> OnboardingStateRead:
    session = await deferred_session.get()
    market = membership.market
    market.name = payload.display_name.strip()
    market.legal_name = payload.legal_name.strip() if payload.legal_name else market.legal_name
    market.country_code = payload.country_code
    market.city = payload.city.strip() if payload.city else None
    market.language = payload.language.strip().lower()
    market.currency = payload.currency
    market.timezone = payload.timezone.strip()
    market.contact_email = payload.contact_email.strip().lower() if payload.contact_email else None
    market.contact_phone = payload.contact_phone.strip() if payload.contact_phone else None
    _advance(market, 2)
    await session.commit()
    await session.refresh(market)
    return _read(market)


@router.patch("/brand", response_model=OnboardingStateRead)
async def update_onboarding_brand(
    payload: OnboardingBrandUpdate,
    membership: MarketUser = Depends(require_market_admin),
    deferred_session: DeferredCatalogSession = Depends(get_deferred_catalog_session),
) -> OnboardingStateRead:
    session = await deferred_session.get()
    market = membership.market
    market.primary_color = payload.primary_color
    market.secondary_color = payload.secondary_color
    _advance(market, 3)
    await session.commit()
    await session.refresh(market)
    return _read(market)


@router.patch("/template", response_model=OnboardingStateRead)
async def update_onboarding_template(
    payload: OnboardingTemplateUpdate,
    membership: MarketUser = Depends(require_market_admin),
    deferred_session: DeferredCatalogSession = Depends(get_deferred_catalog_session),
) -> OnboardingStateRead:
    session = await deferred_session.get()
    market = membership.market
    if payload.default_template_id is not None:
        template = await session.scalar(
            select(Template).where(
                Template.id == payload.default_template_id,
                Template.market_id == membership.market_id,
                Template.is_active.is_(True),
            )
        )
        if template is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Şablon bulunamadı.")
    market.default_template_id = payload.default_template_id
    _advance(market, 4)
    await session.commit()
    await session.refresh(market)
    return _read(market)


@router.post("/complete", response_model=OnboardingStateRead)
async def complete_onboarding(
    membership: MarketUser = Depends(require_market_admin),
    deferred_session: DeferredCatalogSession = Depends(get_deferred_catalog_session),
) -> OnboardingStateRead:
    session = await deferred_session.get()
    market = membership.market
    market.onboarding_status = "completed"
    market.onboarding_step = 4
    market.onboarding_completed_at = utc_now()
    session.add(
        ActivityLog(
            market_id=market.id,
            user_id=membership.user_id,
            entity_type="market",
            entity_id=market.id,
            action="onboarding_completed",
            description="Market onboarding completed",
            metadata_={"step": 4},
        )
    )
    session.add(
        PlatformAuditLog(
            actor_platform_admin_id=None,
            action="onboarding_completed",
            target_type="market",
            target_id=market.id,
            metadata_={"step": 4},
        )
    )
    product_count = await session.scalar(select(Product.id).where(Product.market_id == market.id).limit(1))
    if product_count is not None and market.lifecycle_status in {"trial", "active"}:
        session.add(
            PlatformAuditLog(
                actor_platform_admin_id=None,
                action="market_became_ready",
                target_type="market",
                target_id=market.id,
                metadata_={"source": "onboarding_completed"},
            )
        )
    await session.commit()
    await session.refresh(market)
    return _read(market)


def _advance(market: Market, next_step: int) -> None:
    if market.onboarding_status == "not_started":
        market.onboarding_status = "in_progress"
    market.onboarding_step = max(market.onboarding_step or 1, next_step)


def _read(market: Market) -> OnboardingStateRead:
    return OnboardingStateRead(
        market_id=market.id,
        display_name=market.name,
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
        default_template_id=market.default_template_id,
        onboarding_status=market.onboarding_status,
        onboarding_step=market.onboarding_step,
        onboarding_completed_at=market.onboarding_completed_at,
    )
