from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_catalog_session,
    get_current_market_id,
    get_current_user,
    require_market_role,
)
from app.core.roles import MarketRole
from app.models import Market, User
from app.schemas.market import BrochurePreferences, MarketSettingsRead, MarketSettingsUpdate

# FastAPI dependency declarations intentionally use parameter defaults.
# ruff: noqa: B008

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/market/settings", tags=["market"])


def _read(market: Market) -> MarketSettingsRead:
    return MarketSettingsRead(
        id=market.id, name=market.name, address_line_1=market.address_line_1, address_line_2=market.address_line_2,
        postal_code=market.postal_code, city=market.city, country_code=market.country_code, phone=market.contact_phone,
        website_url=market.website_url, instagram_url=market.instagram_url, facebook_url=market.facebook_url,
        brochure_preferences=BrochurePreferences(
            show_logo=market.brochure_show_logo, show_address=market.brochure_show_address,
            show_phone=market.brochure_show_phone, show_website=market.brochure_show_website,
            show_instagram=market.brochure_show_instagram, show_facebook=market.brochure_show_facebook,
        ),
        has_logo=bool(market.logo_storage_key), logo_mime_type=market.logo_mime_type,
    )


async def _market(session: AsyncSession, market_id: UUID, *, lock: bool = False) -> Market:
    statement = select(Market).where(Market.id == market_id)
    if lock:
        statement = statement.with_for_update()
    market = await session.scalar(statement)
    if market is None:
        raise HTTPException(status_code=404, detail="Market not found.")
    return market


@router.get("", response_model=MarketSettingsRead)
async def get_settings(
    market_id: UUID = Depends(get_current_market_id), session: AsyncSession = Depends(get_catalog_session),
) -> MarketSettingsRead:
    return _read(await _market(session, market_id))


@router.patch("", response_model=MarketSettingsRead)
async def update_settings(
    payload: MarketSettingsUpdate,
    market_id: UUID = Depends(require_market_role(MarketRole.MARKET_ADMIN)),
    actor: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_catalog_session),
) -> MarketSettingsRead:
    market = await _market(session, market_id, lock=True)
    changed: list[str] = []
    for field, value in payload.model_dump(exclude_unset=True, exclude={"brochure_preferences"}).items():
        attribute = "contact_phone" if field == "phone" else field
        if getattr(market, attribute) != value:
            setattr(market, attribute, value)
            changed.append(field)
    if payload.brochure_preferences is not None:
        for field, value in payload.brochure_preferences.model_dump(exclude_unset=True).items():
            attribute = f"brochure_{field}"
            if getattr(market, attribute) != value:
                setattr(market, attribute, value)
                changed.append(attribute)
    await session.commit()
    await session.refresh(market)
    logger.info("market.settings.updated market_id=%s user_id=%s changed_fields=%s", market_id, actor.id, sorted(changed))
    return _read(market)