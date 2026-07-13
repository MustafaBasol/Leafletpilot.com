"""Idempotent synthetic Phase E seed for disposable acceptance environments."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import AsyncSessionLocal, engine  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import Market, PlatformAdmin, Template  # noqa: E402
from scripts.seed_dev_data import seed_dev_data  # noqa: E402


PLATFORM_EMAIL = "phase-e-platform-admin@example.test"
PLATFORM_PASSWORD = "PhaseE-Platform-Admin-123!"


async def main() -> None:
    if AsyncSessionLocal is None:
        raise RuntimeError("DATABASE_URL is required for the Phase E seed.")
    async with AsyncSessionLocal() as session:
        await seed_dev_data(session)
        admin = await session.scalar(select(PlatformAdmin).where(PlatformAdmin.email == PLATFORM_EMAIL))
        if admin is None:
            session.add(PlatformAdmin(email=PLATFORM_EMAIL, full_name="Phase E Platform Admin", password_hash=hash_password(PLATFORM_PASSWORD), is_active=True))
        markets = list((await session.scalars(select(Market).order_by(Market.created_at))).all())
        for index, market in enumerate(markets[:3]):
            market.subscription_plan = ("starter", "growth", "pro")[index]
        demo_market = await session.scalar(select(Market).where(Market.slug == "anadolu-market"))
        if demo_market is not None:
            demo_market.subscription_plan = "growth"
        if markets:
            existing = list((await session.scalars(select(Template).where(Template.is_global.is_(True)).order_by(Template.created_at))).all())
            if not existing:
                session.add_all([
                    Template(name="Phase E Draft Global", slug="phase-e-draft-global", template_type="flyer", status="draft", is_global=True, config_json={"slot_count": 4}),
                    Template(name="Phase E Published Global v1", slug="phase-e-published-v1", template_type="flyer", status="published", is_global=True, version=1, config_json={"slot_count": 4}),
                    Template(name="Phase E Archived Global", slug="phase-e-archived-global", template_type="flyer", status="archived", is_global=True, is_active=False, config_json={"slot_count": 4}),
                ])
        await session.commit()
    if engine is not None:
        await engine.dispose()
    print(f"Seeded Phase E synthetic data; platform admin={PLATFORM_EMAIL} password={PLATFORM_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(main())
