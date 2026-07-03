from collections.abc import AsyncGenerator
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session


async def get_current_market_id(x_market_id: UUID | None = Header(default=None)) -> UUID | None:
    """Temporary tenancy placeholder until real auth resolves the active market."""
    return x_market_id


async def get_required_market_id(
    market_id: UUID | None = Depends(get_current_market_id),
) -> UUID:
    if market_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Market-Id is required for campaign routes.",
        )
    return market_id


async def get_catalog_session() -> AsyncGenerator[AsyncSession, None]:
    try:
        async for session in get_session():
            yield session
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DATABASE_URL is not configured.",
        ) from exc


async def get_campaign_session(
    market_id: UUID = Depends(get_required_market_id),
    session: AsyncSession = Depends(get_catalog_session),
) -> AsyncGenerator[AsyncSession, None]:
    _ = market_id
    yield session
