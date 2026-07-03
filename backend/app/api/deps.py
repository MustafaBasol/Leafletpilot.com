from collections.abc import AsyncGenerator
from uuid import UUID

from fastapi import Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session


async def get_current_market_id(x_market_id: UUID | None = Header(default=None)) -> UUID | None:
    """Temporary tenancy placeholder until real auth resolves the active market."""
    return x_market_id


async def get_catalog_session() -> AsyncGenerator[AsyncSession, None]:
    try:
        async for session in get_session():
            yield session
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DATABASE_URL is not configured.",
        ) from exc
