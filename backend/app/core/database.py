from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.test_database import application_database_url


class Base(DeclarativeBase):
    pass


# The scaffold uses SQLAlchemy's async engine with asyncpg so PostgreSQL access is
# ready for webhook and job routes without changing the session dependency later.
resolved_database_url = application_database_url(
    database_url=settings.database_url,
    test_database_url=settings.test_database_url,
    environment=settings.environment,
)

engine = (
    create_async_engine(
        resolved_database_url,
        pool_pre_ping=True,
        poolclass=NullPool if settings.environment.lower() in {"test", "testing"} or settings.test_database_url else None,
    )
    if resolved_database_url
    else None
)

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
