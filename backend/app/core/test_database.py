from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool


EXPECTED_MANUAL_ACCEPTANCE_DATABASE = "leafletpilot_test"
EXPECTED_TEST_DATABASE = "leafletpilot_test_suite"


class DatabaseIsolationError(RuntimeError):
    """Raised when a test run could write to the manual acceptance database."""


def database_identity(database_url: str) -> tuple[str, int, str]:
    url = make_url(database_url)
    host = (url.host or "localhost").lower()
    if host in {"localhost", "127.0.0.1", "::1"}:
        host = "local"
    return (
        host,
        (url.port or 5432),
        (url.database or "").lower(),
    )


def validate_test_database_urls(
    database_url: str | None,
    test_database_url: str | None,
    *,
    environment: str,
    allow_ci_override: bool = False,
) -> None:
    if not test_database_url:
        raise DatabaseIsolationError(
            "DB-mutating backend tests require TEST_DATABASE_URL; refusing to fall back to DATABASE_URL."
        )
    if not database_url:
        raise DatabaseIsolationError(
            "DB-mutating backend tests require DATABASE_URL so the test database can be compared explicitly."
        )

    test_url = make_url(test_database_url)
    if database_identity(database_url) == database_identity(test_database_url):
        if allow_ci_override and environment.lower() in {"test", "testing"}:
            return
        raise DatabaseIsolationError(
            "TEST_DATABASE_URL resolves to the same database as DATABASE_URL. "
            "Use a dedicated database such as leafletpilot_test_suite; the manual acceptance "
            "database leafletpilot_test is never valid for backend tests."
        )

    if (test_url.database or "").lower() == EXPECTED_MANUAL_ACCEPTANCE_DATABASE:
        raise DatabaseIsolationError(
            "TEST_DATABASE_URL points to leafletpilot_test, the manual acceptance database. "
            "Use leafletpilot_test_suite or another dedicated test database."
        )


def application_database_url(*, database_url: str | None, test_database_url: str | None, environment: str) -> str | None:
    if environment.lower() in {"test", "testing"}:
        return test_database_url
    return database_url


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


async def cleanup_test_database(test_database_url: str) -> None:
    engine = create_async_engine(test_database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            tables = (
                await connection.execute(
                    text(
                        "SELECT tablename FROM pg_catalog.pg_tables "
                        "WHERE schemaname = 'public' AND tablename <> 'alembic_version'"
                    )
                )
            ).scalars().all()
            if tables:
                qualified = ", ".join(f"public.{_quote_identifier(name)}" for name in tables)
                await connection.execute(text(f"TRUNCATE TABLE {qualified} RESTART IDENTITY CASCADE"))
    finally:
        await engine.dispose()
