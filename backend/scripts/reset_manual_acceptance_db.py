"""Reset and reseed the local manual-acceptance database.

This command intentionally has no database URL argument. It only operates on
DATABASE_URL from the backend environment after strict development/local/name
checks and an explicit confirmation flag.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.core.test_database import EXPECTED_MANUAL_ACCEPTANCE_DATABASE  # noqa: E402


def validate_target() -> str:
    if settings.is_production:
        raise RuntimeError("Refusing to reset a production database.")
    if (settings.environment or "").lower() not in {"development", "dev", "local"}:
        raise RuntimeError("ENVIRONMENT must be development/local for this reset command.")
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required and must point to the local manual database.")

    url = make_url(settings.database_url)
    host = (url.host or "").lower()
    if host not in {"localhost", "127.0.0.1", "::1"}:
        raise RuntimeError("Refusing non-local database host; expected localhost or 127.0.0.1.")
    if (url.database or "").lower() != EXPECTED_MANUAL_ACCEPTANCE_DATABASE:
        raise RuntimeError(
            f"Refusing database {url.database!r}; expected {EXPECTED_MANUAL_ACCEPTANCE_DATABASE!r}."
        )
    return settings.database_url


async def reset_schema(database_url: str) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            await connection.execute(text("CREATE SCHEMA public"))
    finally:
        await engine.dispose()


def run_checked(command: list[str], *, env: dict[str, str], cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, env=env, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Confirm destructive reset of the local leafletpilot_test database.",
    )
    args = parser.parse_args()
    database_url = validate_target()
    if not args.confirm:
        raise SystemExit("Refusing reset without --confirm.")

    backend = Path(__file__).resolve().parents[1]
    child_env = os.environ.copy()
    child_env["ENVIRONMENT"] = "development"
    child_env["DATABASE_URL"] = database_url
    child_env.pop("TEST_DATABASE_URL", None)

    print(f"Resetting local manual-acceptance database {EXPECTED_MANUAL_ACCEPTANCE_DATABASE!r}.")
    asyncio.run(reset_schema(database_url))
    python = sys.executable
    run_checked([python, "-m", "alembic", "upgrade", "head"], env=child_env, cwd=backend)
    run_checked([python, "scripts/seed_dev_data.py"], env=child_env, cwd=backend)
    print("Manual acceptance database reset, migrated, and reseeded.")


if __name__ == "__main__":
    main()
