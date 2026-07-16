from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.test_database import (
    DatabaseIsolationError,
    cleanup_test_database,
    validate_test_database_urls,
)
from app.models import Market, MarketProduct, Product


def test_same_database_url_is_rejected_for_mutating_tests() -> None:
    with pytest.raises(DatabaseIsolationError, match="same database"):
        validate_test_database_urls(
            "postgresql+asyncpg://user:pass@localhost:5432/leafletpilot_test",
            "postgresql+asyncpg://user:pass@127.0.0.1:5432/leafletpilot_test",
            environment="test",
        )


def test_dedicated_test_database_is_accepted() -> None:
    validate_test_database_urls(
        "postgresql+asyncpg://user:pass@localhost:5432/leafletpilot_test",
        "postgresql+asyncpg://user:pass@localhost:5432/leafletpilot_test_suite",
        environment="test",
    )


def test_same_database_is_only_allowed_for_explicit_ci_override() -> None:
    validate_test_database_urls(
        "postgresql+asyncpg://user:pass@localhost:5432/leafletpilot_test",
        "postgresql+asyncpg://user:pass@127.0.0.1:5432/leafletpilot_test",
        environment="test",
        allow_ci_override=True,
    )


@pytest.mark.asyncio
async def test_cleanup_removes_catalog_rows_after_exception() -> None:
    if not settings.test_database_url or AsyncSessionLocal is None:
        pytest.skip("TEST_DATABASE_URL is not configured")

    market_id = uuid4()
    product_id = uuid4()
    async with AsyncSessionLocal() as session:
        session.add(Market(id=market_id, name=f"Isolation Market {market_id}", slug=f"isolation-{market_id}"))
        session.add(Product(id=product_id, name="Isolation Product", is_global=True, market_id=None))
        await session.flush()
        session.add(MarketProduct(market_id=market_id, product_id=product_id, regular_price="1.00"))
        await session.commit()

    try:
        raise RuntimeError("intentional fixture-finalizer failure simulation")
    except RuntimeError:
        pass
    finally:
        await cleanup_test_database(settings.test_database_url)

    async with AsyncSessionLocal() as session:
        assert await session.scalar(select(func.count()).select_from(Product)) == 0
        assert await session.scalar(select(func.count()).select_from(MarketProduct)) == 0
