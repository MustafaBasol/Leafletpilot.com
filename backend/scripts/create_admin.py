from __future__ import annotations

import asyncio
from getpass import getpass
import os
from pathlib import Path
import sys

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import AsyncSessionLocal, engine  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import Market, MarketUser, User  # noqa: E402
from app.services.catalog import slugify  # noqa: E402


def _read_value(env_name: str, prompt: str, *, secret: bool = False) -> str:
    value = os.environ.get(env_name, "").strip()
    if value:
        return value
    if secret:
        return getpass(prompt).strip()
    return input(prompt).strip()


def _read_password() -> str:
    password = os.environ.get("ADMIN_PASSWORD", "")
    if password:
        return password

    password = getpass("Admin password: ")
    confirmation = getpass("Confirm admin password: ")
    if password != confirmation:
        raise RuntimeError("Password confirmation does not match.")
    return password


async def create_admin() -> None:
    if AsyncSessionLocal is None:
        raise RuntimeError("DATABASE_URL is required to create the first administrator.")

    email = _read_value("ADMIN_EMAIL", "Admin email: ").lower()
    full_name = _read_value("ADMIN_FULL_NAME", "Admin full name: ")
    market_name = _read_value("ADMIN_MARKET_NAME", "Market name: ")
    password = _read_password()

    if not email or "@" not in email:
        raise RuntimeError("ADMIN_EMAIL must be a valid email address.")
    if not full_name:
        raise RuntimeError("ADMIN_FULL_NAME is required.")
    if not market_name:
        raise RuntimeError("ADMIN_MARKET_NAME is required.")
    if len(password) < 12:
        raise RuntimeError("ADMIN_PASSWORD must be at least 12 characters.")

    market_slug = slugify(market_name)
    async with AsyncSessionLocal() as session:
        async with session.begin():
            existing_user = await session.scalar(select(User).where(User.email == email))
            if existing_user is not None:
                raise RuntimeError(f"User already exists: {email}")

            existing_market = await session.scalar(select(Market).where(Market.slug == market_slug))
            if existing_market is not None:
                raise RuntimeError(f"Market already exists: {market_slug}")

            user = User(
                email=email,
                full_name=full_name,
                password_hash=hash_password(password),
                is_active=True,
            )
            market = Market(
                name=market_name,
                slug=market_slug,
                currency="EUR",
                language="tr",
                timezone="Europe/Paris",
                is_active=True,
            )
            session.add_all([user, market])
            await session.flush()
            session.add(
                MarketUser(
                    market_id=market.id,
                    user_id=user.id,
                    role="market_admin",
                    is_active=True,
                )
            )

    print(f"Created market_admin user {email} for market {market_slug}.")


async def main() -> None:
    try:
        await create_admin()
    finally:
        if engine is not None:
            await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
