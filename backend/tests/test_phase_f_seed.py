import pytest
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models import Market, Template


@pytest.mark.asyncio
async def test_phase_f_market_templates_are_market_scoped_when_seeded():
    if AsyncSessionLocal is None:
        pytest.skip("TEST_DATABASE_URL is not configured")

    async with AsyncSessionLocal() as session:
        templates = list(
            (
                await session.scalars(
                    select(Template)
                    .join(Market, Template.market_id == Market.id)
                    .where(Template.slug.in_(["phase-f-adopted", "phase-f-custom"]), Market.slug == "phase-f-growth")
                )
            ).all()
        )

    if not templates:
        pytest.skip("Phase F seed fixtures are not loaded in this database")

    assert {template.slug for template in templates} == {"phase-f-adopted", "phase-f-custom"}
    assert all(template.market_id is not None and template.is_global is False for template in templates)
