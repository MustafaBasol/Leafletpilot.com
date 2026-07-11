import asyncio

import pytest
from sqlalchemy.engine import make_url

from app.core.config import settings


def pytest_collection_modifyitems(config, items):
    if _test_database_reachable():
        return

    # A configured-but-unusable URL must behave like an unavailable test service;
    # otherwise tests that perform their own optional-DB check attempt a doomed
    # connection and obscure the real environment problem.
    settings.test_database_url = None

    skip_db = pytest.mark.skip(reason="TEST_DATABASE_URL is not configured or reachable.")
    for item in items:
        if "when_test_database_url_is_configured" in item.name:
            item.add_marker(skip_db)


def _test_database_reachable() -> bool:
    if not settings.test_database_url:
        return False
    url = make_url(settings.test_database_url)
    try:
        import asyncpg

        async def probe() -> bool:
            connection = await asyncpg.connect(
                user=url.username,
                password=url.password,
                database=url.database,
                host=url.host or "localhost",
                port=url.port or 5432,
                timeout=1,
            )
            await connection.close()
            return True

        return asyncio.run(probe())
    except Exception:
        return False
