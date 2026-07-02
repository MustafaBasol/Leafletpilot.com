from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    pass


# The scaffold uses SQLAlchemy's async engine with asyncpg so PostgreSQL access is
# ready for webhook and job routes without changing the session dependency later.
engine = create_async_engine(settings.database_url, pool_pre_ping=True) if settings.database_url else None

AsyncSessionLocal = (
    async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    if engine
    else None
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    if AsyncSessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured.")

    async with AsyncSessionLocal() as session:
        yield session
