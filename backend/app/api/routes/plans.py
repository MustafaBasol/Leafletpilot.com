from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_catalog_session, get_current_market_membership
from app.models import Campaign, MarketUser
from app.schemas.plans import MarketPlanUsageRead
from app.services.entitlements import resolve_capabilities, resolve_plan_code
from app.services.plans import get_plan

router = APIRouter(prefix="/market", tags=["plans"])


@router.get("/plan", response_model=MarketPlanUsageRead)
async def get_my_market_plan(
    membership: MarketUser = Depends(get_current_market_membership),
    session: AsyncSession = Depends(get_catalog_session),
) -> MarketPlanUsageRead:
    market = membership.market
    capabilities = resolve_capabilities(market)
    plan = get_plan(market.subscription_plan)
    month_start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    campaigns_this_month = await session.scalar(
        select(func.count(Campaign.id)).where(
            Campaign.market_id == market.id,
            Campaign.created_at >= month_start,
            Campaign.status != "cancelled",
        )
    )
    return MarketPlanUsageRead(
        code=resolve_plan_code(market),
        name=plan.name,
        monthly_price=plan.monthly_price,
        currency=plan.currency,
        monthly_campaigns_limit=capabilities.monthly_campaigns_limit,
        monthly_campaigns_used=campaigns_this_month or 0,
        monthly_exports_limit=capabilities.monthly_exports_limit,
        private_products_limit=capabilities.private_products_limit,
        private_templates_limit=capabilities.private_templates_limit,
        branding_assets_limit=capabilities.branding_assets_limit,
        export_formats=list(capabilities.export_formats),
        support_tier=plan.support_tier,
    )
