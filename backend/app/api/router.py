from fastapi import APIRouter

from app.api.routes.auth import router as auth_router
from app.api.routes.campaigns import router as campaigns_router
from app.api.routes.catalog import router as catalog_router
from app.api.routes.health import router as health_router
from app.api.routes.team import router as team_router
from app.api.routes.telegram import router as telegram_router
from app.api.routes.templates import router as templates_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(campaigns_router)
api_router.include_router(catalog_router)
api_router.include_router(templates_router)
api_router.include_router(team_router)
api_router.include_router(telegram_router)
api_router.include_router(health_router, tags=["health"])
