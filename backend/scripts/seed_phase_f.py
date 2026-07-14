"""Deterministic, secret-free Phase F data for disposable acceptance databases."""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import AsyncSessionLocal, engine  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import (  # noqa: E402
    Campaign,
    CampaignItem,
    ExportJob,
    Market,
    MarketProduct,
    MarketUser,
    PlatformAdmin,
    Product,
    ProductImage,
    Template,
    User,
)
from scripts.seed_dev_data import seed_dev_data  # noqa: E402


PASSWORD = "PhaseF-Local-Only-123!"
ADMIN_EMAIL = "phase-f-platform-admin@example.test"
USER_EMAILS = ("phase-f-user-a@example.test", "phase-f-user-b@example.test")


async def one(session, model, *, lookup=None, **values):
    row = await session.scalar(select(model).filter_by(**(lookup or values)))
    if row is None:
        row = model(**values)
        session.add(row)
        await session.flush()
    return row


async def main() -> None:
    if AsyncSessionLocal is None:
        raise RuntimeError("DATABASE_URL is required for the Phase F seed.")
    async with AsyncSessionLocal() as session:
        await seed_dev_data(session)

        admin = await one(session, PlatformAdmin, lookup={"email": ADMIN_EMAIL}, email=ADMIN_EMAIL, full_name="Phase F Platform Admin", password_hash=hash_password(PASSWORD))
        admin.full_name = "Phase F Platform Admin"
        admin.password_hash = hash_password(PASSWORD)
        admin.is_active = True

        markets = {}
        for slug, name, plan in (
            ("phase-f-starter", "Phase F Starter Market", "starter"),
            ("phase-f-growth", "Phase F Growth Market", "growth"),
            ("phase-f-pro", "Phase F Pro Market", "pro"),
        ):
            market = await one(session, Market, slug=slug, name=name)
            market.name = name
            market.subscription_plan = plan
            market.currency = "EUR"
            market.language = "tr"
            market.is_active = True
            markets[slug] = market

        users = []
        for index, email in enumerate(USER_EMAILS, start=1):
            user = await one(session, User, lookup={"email": email}, email=email, full_name=f"Phase F Market User {index}", password_hash=hash_password(PASSWORD))
            user.full_name = f"Phase F Market User {index}"
            user.password_hash = hash_password(PASSWORD)
            user.is_active = True
            users.append(user)
        for market in markets.values():
            await one(session, MarketUser, market_id=market.id, user_id=users[0].id, role="market_admin")
            membership = await session.scalar(select(MarketUser).where(MarketUser.market_id == market.id, MarketUser.user_id == users[0].id))
            membership.role = "market_admin"
            membership.is_active = True
        await one(session, MarketUser, market_id=markets["phase-f-growth"].id, user_id=users[1].id, role="market_staff")

        def template(slug, name, *, market_id=None, status="published", version=1, active=True, source_template_id=None, slot_count=4):
            return {"slug": slug, "name": name, "market_id": market_id, "is_global": market_id is None, "is_active": active, "status": status, "version": version, "source_template_id": source_template_id, "template_type": "flyer", "visibility": "shared", "minimum_plan": "starter", "published_at": datetime.now(UTC), "config_json": {"slot_count": slot_count, "layout": "phase-f", "accent_color": "#2563eb"}}

        v1 = await one(session, Template, slug="phase-f-global-v1", market_id=None, name="Phase F Global v1", template_type="flyer")
        for key, value in template("phase-f-global-v1", "Phase F Global v1").items(): setattr(v1, key, value)
        v2 = await one(session, Template, slug="phase-f-global-v2", market_id=None, name="Phase F Global v2", template_type="flyer")
        for key, value in template("phase-f-global-v2", "Phase F Global v2", version=2, source_template_id=v1.id).items(): setattr(v2, key, value)
        adopted = await one(session, Template, slug="phase-f-adopted", market_id=markets["phase-f-growth"].id, name="Phase F Adopted Template", template_type="flyer", is_global=False)
        for key, value in template("phase-f-adopted", "Phase F Adopted Template", market_id=markets["phase-f-growth"].id, source_template_id=v2.id).items(): setattr(adopted, key, value)
        custom = await one(session, Template, slug="phase-f-custom", market_id=markets["phase-f-growth"].id, name="Phase F Custom Template", template_type="flyer", is_global=False)
        for key, value in template("phase-f-custom", "Phase F Custom Template", market_id=markets["phase-f-growth"].id, slot_count=2).items(): setattr(custom, key, value)
        for slug, status, active in (("phase-f-draft", "draft", True), ("phase-f-archived", "archived", False)):
            row = await one(session, Template, slug=slug, market_id=None, name=f"Phase F {status.title()} Template", template_type="flyer")
            for key, value in template(slug, f"Phase F {status.title()} Template", status=status, active=active).items(): setattr(row, key, value)
        markets["phase-f-growth"].default_template_id = adopted.id

        products = []
        for index, (barcode, name, regular, promo) in enumerate((
            ("PHASE-F-001", "Phase F Adopted Product", "9.99", "7.99"),
            ("PHASE-F-002", "Phase F Second Product", "6.99", "5.99"),
            ("PHASE-F-003", "Phase F Third Product", "4.99", "3.99"),
        )):
            product = await session.scalar(select(Product).where(Product.barcode == barcode, Product.market_id.is_(None)))
            if product is None:
                product = Product(name=name, short_name=name, barcode=barcode, regular_price=Decimal(regular), promo_price=Decimal(promo), currency="EUR", is_global=True, is_active=True)
                session.add(product)
                await session.flush()
            product.name = name
            product.regular_price = Decimal(regular)
            product.promo_price = Decimal(promo)
            product.is_active = True
            image = await session.scalar(select(ProductImage).where(ProductImage.product_id == product.id))
            if image is None:
                session.add(ProductImage(product_id=product.id, url=f"https://example.com/phase-f-product-{index + 1}.png", mime_type="image/png", quality_status="good", is_primary=True))
            market_product = await one(session, MarketProduct, market_id=markets["phase-f-growth"].id, product_id=product.id)
            market_product.regular_price = Decimal(regular) + Decimal("1.00")
            market_product.promo_price = Decimal(promo) + Decimal("1.00")
            market_product.image_url = f"https://example.com/phase-f-override-{index + 1}.png"
            market_product.image_quality_status = "good"
            market_product.is_active = True
            products.append((product, market_product))
        product, market_product = products[0]
        private = await one(session, MarketProduct, market_id=markets["phase-f-growth"].id, private_name="Phase F Private Product")
        private.regular_price = Decimal("4.99")
        private.is_active = True
        third = await one(session, MarketProduct, market_id=markets["phase-f-growth"].id, private_name="Phase F Third Product")
        third.regular_price = Decimal("6.49")
        third.promo_price = Decimal("5.49")
        third.is_active = True

        async def campaign(slug, title, *, template_id, frozen=False, historical=False):
            row = await one(session, Campaign, market_id=markets["phase-f-growth"].id, slug=slug, title=title)
            row.title = title
            row.channel = "panel"
            row.source_type = "manual"
            row.template_id = template_id
            row.currency = "EUR"
            row.language = "tr"
            row.status = "approved" if frozen else "draft"
            row.campaign_start_date = date(2026, 7, 14)
            row.campaign_end_date = date(2026, 7, 21)
            row.created_by_user_id = users[0].id
            row.builder_config_json = {"headline": title, "subtitle": "Phase F acceptance", "promo_label": "%20 indirim", "footer": "Sentetik kabul verisi"}
            existing_items = {item.product_id: item for item in await session.scalars(select(CampaignItem).where(CampaignItem.campaign_id == row.id))}
            for index, (item_product, item_market_product) in enumerate(products):
                item = existing_items.get(item_product.id)
                if item is None:
                    item = CampaignItem(campaign_id=row.id, market_id=row.market_id, product_id=item_product.id, market_product_id=item_market_product.id, raw_line=item_product.name, incoming_name=item_product.name, display_name=item_product.name, price=item_market_product.promo_price, old_price=item_market_product.regular_price, currency="EUR", sort_order=index, is_hero=index == 0, match_status="matched", match_confidence=Decimal("99"))
                    session.add(item)
                else:
                    item.sort_order = index
                    item.display_name = item_product.name
                    item.price = item_market_product.promo_price
                    item.old_price = item_market_product.regular_price
            if frozen:
                row.frozen_at = row.frozen_at or datetime(2026, 7, 10, tzinfo=UTC)
                row.finalized_at = row.finalized_at or row.frozen_at
                snapshot_template = await session.get(Template, template_id)
                row.snapshot_json = {
                    "template_id": str(template_id),
                    "template_version": 1 if historical else 2,
                    "template_name": snapshot_template.name if snapshot_template else None,
                    "template_slug": snapshot_template.slug if snapshot_template else None,
                    "template_config": dict(snapshot_template.config_json or {}) if snapshot_template else {},
                    "title": title,
                    "language": row.language,
                    "currency": row.currency,
                    "market_name": markets["phase-f-growth"].name,
                    "items": [{"name": "Phase F Adopted Product", "resolved_name": "Phase F Adopted Product", "price": "8.99", "currency": "EUR", "sort_order": 0}],
                }
            return row

        draft = await campaign("phase-f-draft", "Phase F Draft Campaign", template_id=adopted.id)
        frozen = await campaign("phase-f-frozen", "Phase F Finalized Campaign", template_id=v2.id, frozen=True)
        historical = await campaign("phase-f-historical-v1", "Phase F Historical v1 Campaign", template_id=v1.id, frozen=True, historical=True)
        for job_type, formats in (("preview", ["png"]), ("final_export", ["pdf", "png"])):
            await one(session, ExportJob, campaign_id=frozen.id, market_id=frozen.market_id, job_type=job_type)

        await session.commit()
        phase_markets = select(Market.id).where(Market.slug.like("phase-f-%")).scalar_subquery()
        phase_campaigns = select(Campaign.id).where(Campaign.slug.like("phase-f-%")).scalar_subquery()
        counts = {
            "markets": await session.scalar(select(func.count()).select_from(Market).where(Market.slug.like("phase-f-%"))),
            "users": await session.scalar(select(func.count()).select_from(User).where(User.email.like("phase-f-%"))),
            "templates": await session.scalar(select(func.count()).select_from(Template).where(Template.slug.like("phase-f-%"))),
            "products": await session.scalar(select(func.count()).select_from(Product).where(Product.barcode.in_(["PHASE-F-001", "PHASE-F-002", "PHASE-F-003"]))),
            "market_products": await session.scalar(select(func.count()).select_from(MarketProduct).where(MarketProduct.market_id.in_(phase_markets))),
            "campaigns": await session.scalar(select(func.count()).select_from(Campaign).where(Campaign.slug.like("phase-f-%"))),
            "campaign_items": await session.scalar(select(func.count()).select_from(CampaignItem).where(CampaignItem.campaign_id.in_(phase_campaigns))),
            "export_jobs": await session.scalar(select(func.count()).select_from(ExportJob).where(ExportJob.campaign_id.in_(phase_campaigns))),
        }
        admin_ready = await session.scalar(select(func.count()).select_from(PlatformAdmin).where(PlatformAdmin.email == ADMIN_EMAIL, PlatformAdmin.is_active.is_(True))) == 1
        market_users_ready = await session.scalar(select(func.count()).select_from(User).where(User.email.in_(USER_EMAILS), User.is_active.is_(True))) == len(USER_EMAILS)
        summary = {
            "platform_admin_ready": admin_ready,
            "market_users_ready": market_users_ready,
            "templates_ready": counts["templates"] == 6,
            "products_ready": counts["products"] == 3 and counts["market_products"] == 5,
            "campaigns_ready": counts["campaigns"] == 3 and counts["campaign_items"] == 9,
            "exports_ready": counts["export_jobs"] == 2,
            "fixture_version": "phase-f-v1",
            "counts": counts,
        }
        if not all(summary[key] for key in ("platform_admin_ready", "market_users_ready", "templates_ready", "products_ready", "campaigns_ready", "exports_ready")):
            raise RuntimeError(f"Phase F seed self-check failed: {summary}")
        print(json.dumps(summary, sort_keys=True))
    if engine is not None:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
