from fastapi import APIRouter

from app.api.routes.auth import router as auth_router
from app.api.routes.billing import router as billing_router
from app.api.routes.campaigns import router as campaigns_router
from app.api.routes.catalog import router as catalog_router
from app.api.routes.health import router as health_router
from app.api.routes.market_logo import router as market_logo_router
from app.api.routes.onboarding import router as onboarding_router
from app.api.routes.platform import router as platform_router
from app.api.routes.platform_catalog import router as platform_catalog_router
from app.api.routes.platform_billing import router as platform_billing_router
from app.api.routes.platform_catalog_quality import router as platform_catalog_quality_router
from app.api.routes.platform_market_import import router as platform_market_import_router
from app.api.routes.platform_templates import router as platform_templates_router
from app.api.routes.plans import router as plans_router
from app.api.routes.public import router as public_router
from app.api.routes.team import router as team_router
from app.api.routes.platform_whatsapp import router as platform_whatsapp_router
from app.api.routes.telegram import router as telegram_router
from app.api.routes.templates import router as templates_router
from app.api.routes.whatsapp import router as whatsapp_router
from app.api.routes.whatsapp_webhook import router as whatsapp_webhook_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(billing_router)
api_router.include_router(campaigns_router)
api_router.include_router(catalog_router)
api_router.include_router(market_logo_router)
api_router.include_router(templates_router)
api_router.include_router(team_router)
api_router.include_router(plans_router)
api_router.include_router(onboarding_router)
api_router.include_router(public_router)
api_router.include_router(platform_router)
api_router.include_router(platform_billing_router)
# Quality routes are registered before generic catalog product-id routes.
api_router.include_router(platform_catalog_quality_router)
api_router.include_router(platform_catalog_router)
api_router.include_router(platform_market_import_router)
api_router.include_router(platform_templates_router)
api_router.include_router(platform_whatsapp_router)
api_router.include_router(telegram_router)
# Central LeafletPilot WhatsApp channel (Evolution API). Entirely separate
# from the Telegram routes above — no shared router, dependency or state.
api_router.include_router(whatsapp_router)
api_router.include_router(whatsapp_webhook_router)
api_router.include_router(health_router, tags=["health"])
