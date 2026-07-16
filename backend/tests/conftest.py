import asyncio
import inspect
import os

import pytest
import pytest_asyncio
from sqlalchemy.engine import make_url

from app.core.config import settings
from app.core.test_database import cleanup_test_database, validate_test_database_urls


_database_available = False


def _allow_ci_override() -> bool:
    return os.environ.get("CI", "").lower() == "true" and os.environ.get(
        "TEST_DATABASE_ISOLATION_OVERRIDE", ""
    ).lower() == "ci-isolated"


def pytest_configure(config):
    if settings.test_database_url:
        validate_test_database_urls(
            settings.database_url,
            settings.test_database_url,
            environment=settings.environment,
            allow_ci_override=_allow_ci_override(),
        )
        # Make AsyncSessionLocal and the FastAPI app use TEST_DATABASE_URL even
        # when the shell inherited a normal development ENVIRONMENT value.
        settings.environment = "test"
    else:
        # A development DATABASE_URL must never be an implicit integration-test
        # target. Tests with optional database coverage will skip themselves.
        settings.database_url = None


def pytest_collection_modifyitems(config, items):
    global _database_available
    if _test_database_reachable():
        _database_available = True
        return

    # A configured-but-unusable URL must behave like an unavailable test service;
    # otherwise tests that perform their own optional-DB check attempt a doomed
    # connection and obscure the real environment problem.
    settings.test_database_url = None
    _database_available = False

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


def _module_uses_database(module) -> bool:
    try:
        source = inspect.getsource(module)
    except (OSError, TypeError):
        return False
    return "TEST_DATABASE_URL" in source or "AsyncSessionLocal" in source


@pytest_asyncio.fixture(scope="module", autouse=True)
async def isolate_database_between_modules(request):
    if not settings.test_database_url or not _database_available or not _module_uses_database(request.module):
        yield
        return

    await cleanup_test_database(settings.test_database_url)
    try:
        yield
    finally:
        await cleanup_test_database(settings.test_database_url)
