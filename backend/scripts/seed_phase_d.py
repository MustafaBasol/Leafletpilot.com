"""Repeatable synthetic Phase D seed for an isolated PostgreSQL database."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.core.database import AsyncSessionLocal, engine  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import MarketProduct, PlatformAdmin, Product  # noqa: E402
from scripts.seed_dev_data import seed_dev_data  # noqa: E402


EMAIL = "phase-d-platform-admin@example.test"
PASSWORD = "PhaseD-Platform-Admin-123!"


async def main() -> None:
    if settings.is_production:
        raise RuntimeError("Phase D seed refuses production environment.")
    if AsyncSessionLocal is None:
        raise RuntimeError("DATABASE_URL is required for the Phase D seed.")
    async with AsyncSessionLocal() as session:
        await seed_dev_data(session)
        admin = await session.scalar(select(PlatformAdmin).where(PlatformAdmin.email == EMAIL))
        if admin is None:
            session.add(PlatformAdmin(email=EMAIL, full_name="Phase D Platform Admin", password_hash=hash_password(PASSWORD), is_active=True))
        else:
            admin.full_name = "Phase D Platform Admin"
            admin.password_hash = hash_password(PASSWORD)
            admin.is_active = True
        products = list((await session.scalars(select(Product).where(Product.is_global.is_(True)).order_by(Product.created_at).limit(2))).all())
        markets = list((await session.scalars(select(Product.market_id).where(Product.market_id.is_not(None)).distinct())).all())
        for market_id in markets:
            if products:
                existing = await session.scalar(select(MarketProduct).where(MarketProduct.market_id == market_id, MarketProduct.product_id == products[0].id))
                if existing is None:
                    session.add(MarketProduct(market_id=market_id, product_id=products[0].id, currency="EUR", regular_price=2.49, promo_price=1.99, is_active=True))
            private = await session.scalar(select(MarketProduct).where(MarketProduct.market_id == market_id, MarketProduct.product_id.is_(None)))
            if private is None:
                session.add(MarketProduct(market_id=market_id, private_name="Phase D Private Product", private_barcode=f"PHASE-D-{str(market_id)[:8]}", currency="EUR", regular_price=3.49, is_active=True))
        await session.commit()
    print(f"Seeded Phase D synthetic data in {settings.database_url}; platform admin={EMAIL}")
    if engine is not None:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
