"""Guarded, deterministic demo tenant operations.

This module is intentionally CLI-only.  It never accepts a tenant selector from
the database or from a default/first row; the configured immutable market id is
always the primary safety boundary.
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid5

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import AsyncSessionLocal, engine
from app.core.security import hash_password
from app.models import (
    ActivityLog,
    Brand,
    Campaign,
    CampaignFile,
    CampaignItem,
    Category,
    Conversation,
    ExportJob,
    Market,
    MarketUser,
    MatchingSuggestion,
    Product,
    ProductAlias,
    ProductImage,
    Template,
    User,
)
from app.services.campaign import create_export_job
from app.services.catalog import normalize_alias
from app.services.rendering import storage_path_for_key, validate_rendered_file
from app.schemas.export import ExportJobCreate


DEMO_NAMESPACE = UUID("7b9d3d3a-1a6f-4f5c-a60c-20de7ed20d01")
DEMO_OWNER_PASSWORD = "demo-only-local-password"
DEMO_CAMPAIGN_SLUG = "haftanin-super-firsatlari"
DEMO_CAMPAIGN_TITLE = "Haftanın Süper Fırsatları"
DEMO_PRODUCTS = (
    ("apple", "Kırmızı Elma", "Meyve", "kg", "LP-DEMO-APPLE", "2.49", "3.29"),
    ("banana", "Muz", "Meyve", "kg", "LP-DEMO-BANANA", "1.99", "2.69"),
    ("tomato", "Salkım Domates", "Sebze", "kg", "LP-DEMO-TOMATO", "2.79", "3.59"),
    ("lettuce", "Kıtır Marul", "Sebze", "adet", "LP-DEMO-LETTUCE", "1.29", "1.79"),
    ("milk", "Günlük Süt", "Süt Ürünleri", "1 L", "LP-DEMO-MILK", "1.09", "1.39"),
    ("bread", "Taş Fırın Ekmeği", "Fırın", "500 g", "LP-DEMO-BREAD", "0.89", "1.19"),
    ("coffee", "Filtre Kahve", "Kahvaltılık", "250 g", "LP-DEMO-COFFEE", "4.99", "6.49"),
    ("pasta", "Penne Makarna", "Temel Gıda", "500 g", "LP-DEMO-PASTA", "1.19", "1.59"),
    ("rice", "Baldo Pirinç", "Temel Gıda", "1 kg", "LP-DEMO-RICE", "2.99", "3.79"),
    ("olive-oil", "Natürel Sızma Zeytinyağı", "Temel Gıda", "750 ml", "LP-DEMO-OIL", "8.99", "11.49"),
    ("cereal", "Gevrek Kahvaltılık", "Kahvaltılık", "375 g", "LP-DEMO-CEREAL", "3.49", "4.39"),
    ("yogurt", "Yoğun Kıvamlı Yoğurt", "Süt Ürünleri", "1 kg", "LP-DEMO-YOGURT", "2.39", "2.99"),
    ("dish-soap", "Limonlu Bulaşık Sıvısı", "Temizlik", "750 ml", "LP-DEMO-DISH", "2.19", "2.89"),
    ("detergent", "Renkli Çamaşır Deterjanı", "Temizlik", "2.5 L", "LP-DEMO-DETERGENT", "7.99", "9.99"),
    ("paper-towels", "Emici Havlu", "Ev İhtiyaçları", "6'lı", "LP-DEMO-TOWELS", "4.49", "5.49"),
    ("beans", "Kırmızı Fasulye", "Konserve", "400 g", "LP-DEMO-BEANS", "1.59", "2.09"),
)


class DemoOperationError(RuntimeError):
    pass


def stable_id(kind: str, key: str) -> UUID:
    return uuid5(DEMO_NAMESPACE, f"{kind}:{key}")


def require_demo_operations() -> None:
    if not settings.demo_operations_enabled:
        raise DemoOperationError("Demo operations are disabled; set DEMO_OPERATIONS_ENABLED=true explicitly.")
    if settings.demo_market_id is None or not settings.demo_market_slug or not settings.demo_owner_email:
        raise DemoOperationError("Demo allow-list is incomplete; market id, slug, and owner email are required.")


async def load_target(session: AsyncSession, *, allow_missing: bool = False) -> tuple[Market | None, User | None]:
    require_demo_operations()
    market = await session.get(Market, settings.demo_market_id)
    if market is None:
        by_slug = await session.scalar(select(Market).where(Market.slug == settings.demo_market_slug))
        if by_slug is not None:
            raise DemoOperationError("Configured demo slug belongs to a different market id.")
        if not allow_missing:
            raise DemoOperationError("Configured demo market does not exist.")
        owner = await session.scalar(select(User).where(User.email == settings.demo_owner_email.lower()))
        return None, owner
    if market.slug != settings.demo_market_slug:
        raise DemoOperationError("Configured demo market id and slug do not match.")
    owner = await session.scalar(select(User).where(User.email == settings.demo_owner_email.lower()))
    if owner is not None:
        membership = await session.scalar(
            select(MarketUser).where(MarketUser.market_id == market.id, MarketUser.user_id == owner.id)
        )
        if membership is None or membership.role != "market_admin" or not membership.is_active:
            raise DemoOperationError("Configured demo owner is not an active market_admin membership.")
    elif not allow_missing:
        raise DemoOperationError("Configured demo owner does not exist.")
    return market, owner


def asset_source(slug: str) -> Path:
    return Path(__file__).resolve().parents[1] / "assets" / "demo" / "products" / f"{slug}.png"


def asset_key(market_id: UUID, slug: str) -> str:
    return f"markets/{market_id}/demo-assets/{slug}.png"


def copy_asset(market_id: UUID, slug: str) -> tuple[str, int]:
    source = asset_source(slug)
    if not source.is_file() or source.stat().st_size == 0:
        raise DemoOperationError(f"Required local demo asset is missing: {slug}.png")
    key = asset_key(market_id, slug)
    target = storage_path_for_key(key)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return key, target.stat().st_size


async def reset_demo(session: AsyncSession, *, dry_run: bool = False) -> dict[str, int]:
    market, _ = await load_target(session)
    assert market is not None
    campaign_ids = list((await session.scalars(select(Campaign.id).where(Campaign.market_id == market.id, Campaign.slug == DEMO_CAMPAIGN_SLUG))).all())
    product_ids = list((await session.scalars(select(Product.id).where(Product.market_id == market.id, Product.barcode.like("LP-DEMO-%")))).all())
    counts = {"campaigns": len(campaign_ids), "products": len(product_ids)}
    if dry_run:
        return counts
    if campaign_ids:
        await session.execute(delete(MatchingSuggestion).where(MatchingSuggestion.campaign_id.in_(campaign_ids)))
        await session.execute(delete(CampaignItem).where(CampaignItem.campaign_id.in_(campaign_ids)))
        await session.execute(delete(CampaignFile).where(CampaignFile.campaign_id.in_(campaign_ids)))
        await session.execute(delete(ExportJob).where(ExportJob.campaign_id.in_(campaign_ids)))
        await session.execute(delete(Conversation).where(Conversation.campaign_id.in_(campaign_ids)))
        await session.execute(delete(Campaign).where(Campaign.id.in_(campaign_ids), Campaign.market_id == market.id))
    await session.execute(delete(ActivityLog).where(ActivityLog.market_id == market.id, ActivityLog.action.like("demo_%")))
    if product_ids:
        await session.execute(delete(ProductAlias).where(ProductAlias.product_id.in_(product_ids)))
        await session.execute(delete(ProductImage).where(ProductImage.product_id.in_(product_ids)))
        await session.execute(delete(Product).where(Product.id.in_(product_ids), Product.market_id == market.id))
    await session.execute(delete(Category).where(Category.market_id == market.id))
    await session.execute(delete(Brand).where(Brand.market_id == market.id))
    await session.execute(delete(Template).where(Template.market_id == market.id, Template.slug.like("demo-%")))
    await session.flush()
    root = storage_path_for_key(f"markets/{market.id}/demo-assets")
    if root.exists():
        shutil.rmtree(root)
    export_root = storage_path_for_key(f"markets/{market.id}/campaigns")
    if export_root.exists():
        shutil.rmtree(export_root)
    await session.commit()
    return counts


async def seed_demo(session: AsyncSession, *, dry_run: bool = False) -> dict[str, int | str]:
    market, owner = await load_target(session, allow_missing=True)
    if market is None:
        market = Market(id=settings.demo_market_id, name="LeafletPilot Demo Market", slug=settings.demo_market_slug, country_code="TR", city="İstanbul", currency="EUR", language="tr", timezone="Europe/Paris", is_active=True)
        session.add(market)
        await session.flush()
    if owner is None:
        owner = User(id=stable_id("user", settings.demo_owner_email), email=settings.demo_owner_email.lower(), full_name="LeafletPilot Demo Owner", password_hash=hash_password(DEMO_OWNER_PASSWORD), is_active=True)
        session.add(owner)
        await session.flush()
    membership = await session.scalar(select(MarketUser).where(MarketUser.market_id == market.id, MarketUser.user_id == owner.id))
    if membership is None:
        session.add(MarketUser(id=stable_id("membership", str(market.id)), market_id=market.id, user_id=owner.id, role="market_admin", is_active=True))
    else:
        membership.role, membership.is_active = "market_admin", True
    if dry_run:
        await session.rollback()
        return {"products": len(DEMO_PRODUCTS), "campaign_items": 10, "templates": 2}
    brands: dict[str, Brand] = {}
    categories: dict[str, Category] = {}
    for index, name in enumerate(sorted({row[2] for row in DEMO_PRODUCTS}), start=1):
        category = Category(id=stable_id("category", name), market_id=market.id, name=name, slug=f"demo-{index}-{name.lower().replace(' ', '-')}", sort_order=index * 10, is_global=False, is_active=True)
        session.add(category)
        categories[name] = category
    for name in ("LeafletPilot Demo"):
        brand = Brand(id=stable_id("brand", name), market_id=market.id, name=name, slug="demo-generic", is_global=False, is_active=True)
        session.add(brand)
        brands[name] = brand
    await session.flush()
    products: list[Product] = []
    for slug, name, category_name, unit, barcode, price, old_price in DEMO_PRODUCTS:
        key, size = copy_asset(market.id, slug)
        product = Product(id=stable_id("product", barcode), market_id=market.id, brand_id=brands["LeafletPilot Demo"].id, category_id=categories[category_name].id, name=name, short_name=name, barcode=barcode, package_size=unit, is_global=False, is_active=True, quality_score=100)
        product.images = [ProductImage(id=stable_id("image", barcode), storage_key=key, mime_type="image/png", size_bytes=size, width=420, height=420, quality_status="excellent", is_primary=True)]
        product.aliases = [ProductAlias(id=stable_id("alias", barcode), alias=name, normalized_alias=normalize_alias(name), source="demo_seed")]
        session.add(product)
        products.append(product)
    templates = []
    for slug, name, layout in (("demo-premium", "Demo Premium Market", "premium-market"), ("demo-compact", "Demo Compact Weekly", "compact-weekly")):
        template = Template(id=stable_id("template", slug), market_id=market.id, name=name, slug=slug, description="Deterministic LeafletPilot demo template.", template_type="demo", is_global=False, is_active=True, config_json={"layout": layout, "columns": 3 if layout == "premium-market" else 2, "show_old_price": True, "accent_color": "#0f766e", "accent_soft_color": "#ccfbf1"})
        session.add(template)
        templates.append(template)
    await session.flush()
    campaign = Campaign(id=stable_id("campaign", DEMO_CAMPAIGN_SLUG), market_id=market.id, created_by_user_id=owner.id, title=DEMO_CAMPAIGN_TITLE, slug=DEMO_CAMPAIGN_SLUG, status="approved", channel="panel", source_type="manual", raw_input_text="Deterministic demo campaign", template_id=templates[0].id, campaign_start_date=date(2026, 7, 13), campaign_end_date=date(2026, 7, 19), currency="EUR", language="tr")
    for index, product in enumerate(products[:10]):
        _, name, category_name, unit, _, price, old_price = DEMO_PRODUCTS[index]
        campaign.items.append(CampaignItem(id=stable_id("item", str(index)), market_id=market.id, product_id=product.id, raw_line=f"{name} - {price} EUR", incoming_name=name, display_name=name, price=Decimal(price), old_price=Decimal(old_price), currency="EUR", unit_label=unit, category_hint=category_name, sort_order=index, is_hero=index == 0, match_status="manual_selected", match_confidence=Decimal("100"), parsed_payload={"source": "demo_seed", "deterministic": True}))
    campaign.product_count = campaign.matched_count = 10
    campaign.missing_count = campaign.low_confidence_count = 0
    session.add(campaign)
    session.add(ActivityLog(id=stable_id("activity", DEMO_CAMPAIGN_SLUG), market_id=market.id, user_id=owner.id, entity_type="campaign", entity_id=campaign.id, action="demo_seeded", description="Deterministic demo campaign seeded", metadata_={"source": "demo_tenant"}))
    await session.commit()
    return {"market_id": str(market.id), "owner_email": owner.email, "products": len(products), "campaign_items": 10, "campaign_id": str(campaign.id)}


async def generate_exports(session: AsyncSession) -> dict[str, int | str]:
    market, _ = await load_target(session)
    campaign = await session.scalar(select(Campaign).where(Campaign.market_id == market.id, Campaign.slug == DEMO_CAMPAIGN_SLUG))
    if campaign is None:
        raise DemoOperationError("Golden demo campaign is missing; run seed first.")
    existing = await session.scalar(select(ExportJob).where(ExportJob.market_id == market.id, ExportJob.campaign_id == campaign.id, ExportJob.status == "completed"))
    if existing is not None:
        return {"export_job_id": str(existing.id), "status": "completed", "files": len(existing.result_file_ids or [])}
    job = await create_export_job(session, campaign.id, ExportJobCreate(job_type="final_export", requested_formats=["pdf", "png"]), market.id, commit=True)
    if job.status != "completed" or len(job.result_file_ids or []) != 2:
        raise DemoOperationError(f"Demo export failed with status {job.status}.")
    return {"export_job_id": str(job.id), "status": job.status, "files": len(job.result_file_ids or [])}


async def verify_demo(session: AsyncSession) -> dict[str, int | str]:
    market, owner = await load_target(session)
    product_count = await session.scalar(select(func.count(Product.id)).where(Product.market_id == market.id, Product.barcode.like("LP-DEMO-%")))
    campaign = await session.scalar(select(Campaign).options(selectinload(Campaign.items), selectinload(Campaign.template)).where(Campaign.market_id == market.id, Campaign.slug == DEMO_CAMPAIGN_SLUG))
    if product_count != 16 or campaign is None or len(campaign.items) != 10 or campaign.template is None:
        raise DemoOperationError("Demo verification failed: market, product, campaign, or template invariant is missing.")
    images = list((await session.scalars(select(ProductImage).join(Product).where(Product.market_id == market.id, Product.barcode.like("LP-DEMO-%")))).all())
    for image in images:
        if not image.storage_key or "example.com" in (image.url or ""):
            raise DemoOperationError("Demo verification failed: placeholder or remote image reference found.")
        path = storage_path_for_key(image.storage_key)
        if not path.is_file() or path.stat().st_size <= 0:
            raise DemoOperationError("Demo verification failed: local demo asset is missing.")
    jobs = list((await session.scalars(select(ExportJob).where(ExportJob.market_id == market.id, ExportJob.campaign_id == campaign.id, ExportJob.status == "completed"))).all())
    if not jobs:
        raise DemoOperationError("Demo verification failed: no completed export job.")
    files = list((await session.scalars(select(CampaignFile).where(CampaignFile.market_id == market.id, CampaignFile.campaign_id == campaign.id, CampaignFile.status == "ready"))).all())
    formats = {file.format for file in files}
    if not {"pdf", "png"}.issubset(formats):
        raise DemoOperationError("Demo verification failed: PDF and PNG files are required.")
    for file in files:
        path = storage_path_for_key(file.storage_key or "")
        validate_rendered_file(path, file.format or "")
    return {"market_id": str(market.id), "owner_email": owner.email, "products": product_count, "campaign_items": len(campaign.items), "exports": len(files), "status": "ready"}


async def run(command: str, *, confirm: bool = False, dry_run: bool = False) -> dict[str, int | str]:
    require_demo_operations()
    if AsyncSessionLocal is None:
        raise DemoOperationError("DATABASE_URL is required for demo operations.")
    if command == "reset" and not confirm and not dry_run:
        raise DemoOperationError("Reset requires --confirm.")
    async with AsyncSessionLocal() as session:
        if command == "inspect":
            market, owner = await load_target(session, allow_missing=True)
            return {"market_id": str(settings.demo_market_id), "market_exists": str(market is not None), "owner_exists": str(owner is not None), "status": "valid"}
        if command == "reset":
            return await reset_demo(session, dry_run=dry_run)
        if command == "seed":
            if dry_run:
                return await seed_demo(session, dry_run=True)
            market, _ = await load_target(session, allow_missing=True)
            if market is not None:
                await reset_demo(session)
            return await seed_demo(session)
        if command == "generate-exports":
            return await generate_exports(session)
        if command == "verify":
            return await verify_demo(session)
    raise DemoOperationError(f"Unknown demo command: {command}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Operator-only deterministic LeafletPilot demo tenant operations")
    parser.add_argument("command", choices=("inspect", "seed", "reset", "generate-exports", "verify"))
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        result = asyncio.run(run(args.command, confirm=args.confirm, dry_run=args.dry_run))
    except (DemoOperationError, ValueError) as exc:
        print(f"demo operation refused: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    print("demo operation ok")
    for key, value in result.items():
        print(f"{key}: {value}")
    if engine is not None:
        asyncio.run(engine.dispose())


if __name__ == "__main__":
    main()
