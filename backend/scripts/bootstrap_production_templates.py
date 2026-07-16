"""Idempotently provision the canonical published global templates in production.

Run after migrations with: python -m scripts.bootstrap_production_templates
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.core.database import AsyncSessionLocal, engine  # noqa: E402
from app.models import Template  # noqa: E402
from scripts.seed_dev_data import DEMO_TEMPLATES  # noqa: E402


async def bootstrap() -> dict[str, int]:
    if not settings.is_production:
        raise RuntimeError("Production template bootstrap requires ENVIRONMENT=production.")
    if AsyncSessionLocal is None:
        raise RuntimeError("DATABASE_URL is required for production template bootstrap.")
    counts = {"created": 0, "updated": 0, "unchanged": 0}
    async with AsyncSessionLocal() as session:
        for seed in DEMO_TEMPLATES:
            template = await session.scalar(select(Template).where(Template.slug == seed["slug"], Template.market_id.is_(None)))
            values = {
                "name": seed["name"], "description": seed["description"], "template_type": seed["template_type"],
                "is_global": True, "is_active": True, "status": "published", "visibility": "shared",
                "config_json": seed["config_json"],
            }
            if template is None:
                session.add(Template(slug=seed["slug"], market_id=None, **values))
                counts["created"] += 1
            else:
                changed = False
                for key, value in values.items():
                    if getattr(template, key) != value:
                        setattr(template, key, value)
                        changed = True
                counts["updated" if changed else "unchanged"] += 1
        await session.commit()
    return counts


async def main() -> None:
    try:
        print(json.dumps(await bootstrap(), sort_keys=True))
    finally:
        if engine is not None:
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
