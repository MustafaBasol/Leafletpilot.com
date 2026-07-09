from __future__ import annotations

import asyncio
import getpass
import os
import re
import sys

from sqlalchemy import select

from app.core.database import AsyncSessionLocal, engine
from app.core.security import hash_password
from app.models import PlatformAdmin

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


async def main() -> int:
    if AsyncSessionLocal is None:
        print("DATABASE_URL is not configured.", file=sys.stderr)
        return 2

    email = _read_value("PLATFORM_ADMIN_EMAIL", "E-posta").strip().lower()
    full_name = _read_value("PLATFORM_ADMIN_FULL_NAME", "Ad soyad").strip()
    password = os.getenv("PLATFORM_ADMIN_PASSWORD") or getpass.getpass("Şifre: ")

    if not EMAIL_RE.match(email):
        print("Valid email is required.", file=sys.stderr)
        return 2
    if not full_name:
        print("Full name is required.", file=sys.stderr)
        return 2
    if len(password) < 12:
        print("Password must be at least 12 characters.", file=sys.stderr)
        return 2

    try:
        async with AsyncSessionLocal() as session:
            existing = await session.scalar(select(PlatformAdmin).where(PlatformAdmin.email == email))
            if existing is not None:
                print("A PlatformAdmin with that email already exists.", file=sys.stderr)
                return 1
            session.add(
                PlatformAdmin(
                    email=email,
                    full_name=full_name,
                    password_hash=hash_password(password),
                    is_active=True,
                )
            )
            await session.commit()
    finally:
        if engine is not None:
            await engine.dispose()

    print(f"Platform admin created: {email}")
    return 0


def _read_value(env_name: str, prompt: str) -> str:
    value = os.getenv(env_name)
    if value is not None:
        return value
    return input(f"{prompt}: ")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
