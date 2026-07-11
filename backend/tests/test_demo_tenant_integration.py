from uuid import uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.core.config import settings
from app.core.database import Base
from app.models import Brand, Campaign, CampaignFile, Category, ExportJob, Market, MarketUser, User
from app.scripts import demo_tenant


@pytest.mark.asyncio
async def test_demo_tenant_postgres_idempotency_isolation_and_chromium_export_when_test_database_url_is_configured(
    tmp_path, monkeypatch
) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; PostgreSQL demo integration skipped.")

    market_id = uuid4()
    owner_email = f"demo-owner-{market_id}@example.test"
    monkeypatch.setattr(settings, "demo_operations_enabled", True)
    monkeypatch.setattr(settings, "demo_market_id", market_id)
    monkeypatch.setattr(settings, "demo_market_slug", f"demo-{market_id}")
    monkeypatch.setattr(settings, "demo_owner_email", owner_email)
    monkeypatch.setattr(settings, "demo_owner_initial_password", SecretStr("synthetic-only-bootstrap"))
    monkeypatch.setattr(settings, "local_storage_dir", str(tmp_path))

    engine = create_async_engine(settings.test_database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    try:
        async with session_factory() as session:
            owner = User(id=uuid4(), email=owner_email, full_name="Synthetic Demo Owner", is_active=True)
            market = Market(id=market_id, name="Synthetic Demo", slug=f"demo-{market_id}")
            unrelated_category = Category(id=uuid4(), market_id=market_id, name="Unrelated", slug=f"unrelated-{market_id}")
            unrelated_brand = Brand(id=uuid4(), market_id=market_id, name="Unrelated Brand", slug=f"unrelated-{market_id}")
            unrelated_campaign = Campaign(
                id=uuid4(), market_id=market_id, created_by_user_id=owner.id,
                title="Unrelated campaign", slug=f"unrelated-{market_id}", status="draft",
            )
            unrelated_key = f"markets/{market_id}/campaigns/{unrelated_campaign.id}/exports/unrelated.pdf"
            unrelated_path = tmp_path / "markets" / str(market_id) / "campaigns" / str(unrelated_campaign.id) / "exports" / "unrelated.pdf"
            unrelated_path.parent.mkdir(parents=True)
            unrelated_path.write_bytes(b"%PDF-unrelated")
            unrelated_file = CampaignFile(
                id=uuid4(), campaign_id=unrelated_campaign.id, market_id=market_id,
                file_type="brochure_pdf", format="pdf", status="ready", storage_key=unrelated_key,
                size_bytes=unrelated_path.stat().st_size,
            )
            unrelated_export = ExportJob(
                id=uuid4(), campaign_id=unrelated_campaign.id, market_id=market_id,
                job_type="final_export", status="completed", requested_formats=["pdf"],
                result_file_ids=[str(unrelated_file.id)],
            )
            session.add_all([owner, market, unrelated_category, unrelated_brand, unrelated_campaign, unrelated_file, unrelated_export])
            session.add(MarketUser(id=uuid4(), market_id=market_id, user_id=owner.id, role="market_admin", is_active=True))
            await session.commit()

            first = await demo_tenant.seed_demo(session)
            assert first["products"] == 16
            assert first["campaign_items"] == 10
            brands = list((await session.scalars(select(Brand).where(Brand.market_id == market_id))).all())
            assert len([brand for brand in brands if brand.id in {demo_tenant.stable_id("brand", fixture["key"]) for fixture in demo_tenant.DEMO_BRANDS}]) == len(demo_tenant.DEMO_BRANDS)
            demo_brands = [brand for brand in brands if brand.id in {demo_tenant.stable_id("brand", fixture["key"]) for fixture in demo_tenant.DEMO_BRANDS}]
            assert [(brand.name, brand.slug) for brand in demo_brands] == [("LeafletPilot Demo", "demo-generic")]
            assert all(len(brand.name) > 1 for brand in demo_brands)
            assert len({brand.slug for brand in brands}) == len(brands)
            second = await demo_tenant.seed_demo(session)
            assert second["products"] == 16
            assert await session.scalar(select(Brand.id).where(Brand.id == demo_tenant.stable_id("brand", "generic"))) == demo_tenant.stable_id("brand", "generic")
            assert await session.scalar(select(Brand.name).where(Brand.id == demo_tenant.stable_id("brand", "generic"))) == "LeafletPilot Demo"
            assert await session.scalar(select(Brand.slug).where(Brand.id == demo_tenant.stable_id("brand", "generic"))) == "demo-generic"
            assert await session.scalar(select(Brand.id).where(Brand.market_id == market_id, Brand.slug == "demo-generic")) == demo_tenant.stable_id("brand", "generic")
            assert await session.scalar(select(Category.id).where(Category.id == unrelated_category.id)) == unrelated_category.id
            assert await session.scalar(select(Brand.id).where(Brand.id == unrelated_brand.id)) == unrelated_brand.id
            assert await session.scalar(select(Campaign.id).where(Campaign.id == unrelated_campaign.id)) == unrelated_campaign.id
            assert await session.scalar(select(CampaignFile.id).where(CampaignFile.id == unrelated_file.id)) == unrelated_file.id
            assert await session.scalar(select(ExportJob.id).where(ExportJob.id == unrelated_export.id)) == unrelated_export.id

            exported = await demo_tenant.generate_exports(session)
            assert exported["status"] == "completed"
            counts = await demo_tenant.verify_demo(session)
            assert counts["products"] == 16
            campaign = await session.scalar(select(Campaign).where(Campaign.id == demo_tenant.stable_id("campaign", demo_tenant.DEMO_CAMPAIGN_SLUG)))
            assert campaign is not None
            files = list((await session.scalars(select(CampaignFile).where(CampaignFile.campaign_id == campaign.id))).all())
            assert {file.format for file in files} == {"pdf", "png"}
            for file in files:
                path = demo_tenant.storage_path_for_key(file.storage_key)
                assert path.stat().st_size > 0
                signature = path.read_bytes()[:8]
                assert signature.startswith(b"%PDF-") if file.format == "pdf" else signature == b"\x89PNG\r\n\x1a\n"

            await demo_tenant.reset_demo(session)
            assert await session.scalar(select(Brand.id).where(Brand.id == demo_tenant.stable_id("brand", "generic"))) is None
            assert await session.scalar(select(Brand.id).where(Brand.id == unrelated_brand.id)) == unrelated_brand.id
            await demo_tenant.reset_demo(session)
            reseeded = await demo_tenant.seed_demo(session)
            assert reseeded["products"] == 16
            recreated_brands = list((await session.scalars(select(Brand).where(Brand.market_id == market_id, Brand.slug == "demo-generic"))).all())
            assert [(brand.name, brand.slug) for brand in recreated_brands] == [("LeafletPilot Demo", "demo-generic")]
            reseeded_export = await demo_tenant.generate_exports(session)
            assert reseeded_export["status"] == "completed"
            assert (await demo_tenant.verify_demo(session))["status"] == "ready"
            assert await session.scalar(select(Campaign.id).where(Campaign.id == unrelated_campaign.id)) == unrelated_campaign.id
            assert await session.scalar(select(CampaignFile.id).where(CampaignFile.id == unrelated_file.id)) == unrelated_file.id
            assert unrelated_path.read_bytes() == b"%PDF-unrelated"
    finally:
        await engine.dispose()
