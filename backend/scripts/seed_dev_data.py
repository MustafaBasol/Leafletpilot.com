from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.core.database import AsyncSessionLocal, engine  # noqa: E402
from app.models import (  # noqa: E402
    Brand,
    Campaign,
    Category,
    Market,
    MarketUser,
    Product,
    ProductAlias,
    ProductImage,
    Template,
    User,
)
from app.schemas.campaign import CampaignCreateFromTextRequest  # noqa: E402
from app.core.security import hash_password, verify_password  # noqa: E402
from app.services.campaign import create_campaign_from_text  # noqa: E402
from app.services.catalog import normalize_alias, slugify  # noqa: E402


DEMO_USER_EMAIL = "demo@leafletpilot.com"
DEMO_USER_PASSWORD = "demo1234"
DEMO_STAFF_EMAIL = "staff@leafletpilot.local"
DEMO_VIEWER_EMAIL = "viewer@leafletpilot.local"
DEMO_MARKET_SLUG = "anadolu-market"
DEMO_SECOND_MARKET_SLUG = "avrupa-market"
DEMO_CAMPAIGN_SLUG = "hafta-28-kampanyasi"
DEMO_CAMPAIGN_TITLE = "Hafta 28 Kampanyası"
DEMO_CAMPAIGN_RAW_TEXT = """Coca Cola 2L - 1.59€
Eti Burçak - 0.99€
Torku Sucuk 400g - 5.99EUR
Ülker Halley 10'lu - 1.49€
Pınar Süt 1L - 0.89€
Nutella 750g - 4.99€"""


@dataclass(frozen=True)
class ProductSeed:
    name: str
    barcode: str
    aliases: tuple[str, ...]
    category: str
    brand: str
    package_size: str


DEMO_BRANDS = ("Coca-Cola", "Eti", "Ülker", "Torku", "Pınar", "Nutella", "Sütaş", "Bizim")
DEMO_CATEGORIES = (
    "İçecekler",
    "Bisküvi & Çikolata",
    "Et & Şarküteri",
    "Süt Ürünleri",
    "Kahvaltılık",
    "Temel Gıda",
)
DEMO_PRODUCTS = (
    ProductSeed(
        name="Coca-Cola 2L",
        barcode="8690632032223",
        aliases=("Coca Cola 2 litre", "Kola 2L", "Coco Cola 2 lt"),
        category="İçecekler",
        brand="Coca-Cola",
        package_size="2L",
    ),
    ProductSeed(
        name="Eti Burçak",
        barcode="8690526066266",
        aliases=("Eti Burcak", "Burçak Bisküvi"),
        category="Bisküvi & Çikolata",
        brand="Eti",
        package_size="131g",
    ),
    ProductSeed(
        name="Ülker Halley 10'lu",
        barcode="8690504120126",
        aliases=("Halley 10lu", "Ulker Halley"),
        category="Bisküvi & Çikolata",
        brand="Ülker",
        package_size="10'lu",
    ),
    ProductSeed(
        name="Torku Sucuk 400g",
        barcode="8690123450400",
        aliases=("Torku Dana Sucuk 400g", "Torku Sucuk"),
        category="Et & Şarküteri",
        brand="Torku",
        package_size="400g",
    ),
    ProductSeed(
        name="Pınar Süt 1L",
        barcode="8690565010014",
        aliases=("Pinar Sut 1L", "Pınar 1 litre süt"),
        category="Süt Ürünleri",
        brand="Pınar",
        package_size="1L",
    ),
    ProductSeed(
        name="Nutella 750g",
        barcode="8000500310427",
        aliases=("Nutella 750 gr",),
        category="Kahvaltılık",
        brand="Nutella",
        package_size="750g",
    ),
    ProductSeed(
        name="Sütaş Ayran 1L",
        barcode="8690767001002",
        aliases=("Sutas Ayran 1L",),
        category="İçecekler",
        brand="Sütaş",
        package_size="1L",
    ),
    ProductSeed(
        name="Bizim Yağ 5L",
        barcode="8690515150505",
        aliases=("Bizim Ayçiçek Yağı 5L", "Bizim Yag 5 lt"),
        category="Temel Gıda",
        brand="Bizim",
        package_size="5L",
    ),
)

DEMO_MARKET_PRODUCTS = (
    (
        DEMO_MARKET_SLUG,
        ProductSeed(
            name="Anadolu Market Özel Zeytin 900g",
            barcode="LP-ANADOLU-0001",
            aliases=("Anadolu özel zeytin",),
            category="Kahvaltılık",
            brand="Bizim",
            package_size="900g",
        ),
    ),
    (
        DEMO_SECOND_MARKET_SLUG,
        ProductSeed(
            name="Avrupa Market Özel Kahve 500g",
            barcode="LP-AVRUPA-0001",
            aliases=("Avrupa özel kahve",),
            category="Temel Gıda",
            brand="Bizim",
            package_size="500g",
        ),
    ),
)

DEMO_TEMPLATES = (
    {
        "name": "Premium Market",
        "slug": "premium-market",
        "description": "Modern market kampanyaları için geniş görsel alanlı temel şablon.",
        "template_type": "premium",
        "config_json": {
            "layout": "premium-market",
            "formats": ["A4 PDF", "A4 PNG", "Instagram Post", "WhatsApp Görseli"],
            "max_products_per_page": 18,
            "preview_tone": "premium",
            "accent_color": "#b91c1c",
            "accent_soft_color": "#fff1f2",
            "columns": 3,
            "show_old_price": True,
            "show_badges": False,
        },
    },
    {
        "name": "Compact Weekly",
        "slug": "compact-weekly",
        "description": "Haftalık fiyat listeleri için yoğun ve sade kampanya şablonu.",
        "template_type": "compact",
        "config_json": {
            "layout": "compact-weekly",
            "formats": ["A4 PNG", "Instagram Story", "WhatsApp Görseli"],
            "max_products_per_page": 24,
            "preview_tone": "classic",
            "accent_color": "#0f766e",
            "accent_soft_color": "#ccfbf1",
            "columns": 2,
            "show_old_price": True,
            "show_badges": False,
        },
    },
)


def require_database_url() -> None:
    if not settings.database_url or AsyncSessionLocal is None:
        raise RuntimeError("DATABASE_URL is required to seed development data.")


async def seed_dev_data(session: AsyncSession) -> dict[str, Any]:
    counts = {"created": 0, "updated": 0, "unchanged": 0}

    user = await upsert_user(session, counts, DEMO_USER_EMAIL, "Demo Admin")
    staff_user = await upsert_user(session, counts, DEMO_STAFF_EMAIL, "Demo Staff")
    viewer_user = await upsert_user(session, counts, DEMO_VIEWER_EMAIL, "Demo Viewer")
    market = await upsert_market(session, counts)
    second_market = await upsert_second_market(session, counts)
    await upsert_market_user(session, market, user, "market_admin", counts)
    await upsert_market_user(session, second_market, user, "market_admin", counts)
    await upsert_market_user(session, market, staff_user, "market_staff", counts)
    await upsert_market_user(session, market, viewer_user, "viewer", counts)
    brands = await upsert_brands(session, counts)
    categories = await upsert_categories(session, counts)
    await upsert_products(session, brands, categories, {market.slug: market, second_market.slug: second_market}, counts)
    templates = await upsert_templates(session, counts)
    campaign = await upsert_demo_campaign(session, market, templates["premium-market"], counts)

    await session.commit()
    return {
        "market_id": market.id,
        "user_email": user.email,
        "campaign_id": campaign.id,
        **counts,
    }


async def upsert_user(session: AsyncSession, counts: dict[str, int], email: str, full_name: str) -> User:
    user = await session.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(
            email=email,
            full_name=full_name,
            password_hash=hash_password(DEMO_USER_PASSWORD),
            is_active=True,
        )
        session.add(user)
        counts["created"] += 1
        await session.flush()
        return user

    password_hash = user.password_hash
    if not verify_password(DEMO_USER_PASSWORD, password_hash):
        password_hash = hash_password(DEMO_USER_PASSWORD)
    changed = update_fields(user, full_name=full_name, password_hash=password_hash, is_active=True)
    counts["updated" if changed else "unchanged"] += 1
    return user


async def upsert_market(session: AsyncSession, counts: dict[str, int]) -> Market:
    market = await session.scalar(select(Market).where(Market.slug == DEMO_MARKET_SLUG))
    values = {
        "name": "Anadolu Market",
        "currency": "EUR",
        "language": "tr",
        "timezone": "Europe/Paris",
        "is_active": True,
    }
    if market is None:
        market = Market(slug=DEMO_MARKET_SLUG, **values)
        session.add(market)
        counts["created"] += 1
        await session.flush()
        return market

    changed = update_fields(market, **values)
    counts["updated" if changed else "unchanged"] += 1
    return market


async def upsert_second_market(session: AsyncSession, counts: dict[str, int]) -> Market:
    market = await session.scalar(select(Market).where(Market.slug == DEMO_SECOND_MARKET_SLUG))
    values = {
        "name": "Avrupa Market",
        "currency": "EUR",
        "language": "tr",
        "timezone": "Europe/Paris",
        "is_active": True,
    }
    if market is None:
        market = Market(slug=DEMO_SECOND_MARKET_SLUG, **values)
        session.add(market)
        counts["created"] += 1
        await session.flush()
        return market

    changed = update_fields(market, **values)
    counts["updated" if changed else "unchanged"] += 1
    return market


async def upsert_market_user(
    session: AsyncSession,
    market: Market,
    user: User,
    role: str,
    counts: dict[str, int],
) -> MarketUser:
    membership = await session.scalar(
        select(MarketUser).where(
            MarketUser.market_id == market.id,
            MarketUser.user_id == user.id,
        )
    )
    values = {"role": role, "is_active": True}
    if membership is None:
        membership = MarketUser(market_id=market.id, user_id=user.id, **values)
        session.add(membership)
        counts["created"] += 1
        await session.flush()
        return membership

    changed = update_fields(membership, **values)
    counts["updated" if changed else "unchanged"] += 1
    return membership


async def upsert_brands(session: AsyncSession, counts: dict[str, int]) -> dict[str, Brand]:
    brands: dict[str, Brand] = {}
    for name in DEMO_BRANDS:
        slug = slugify(name)
        brand = await session.scalar(
            select(Brand).where(Brand.slug == slug, Brand.market_id.is_(None))
        )
        values = {"name": name, "is_global": True, "is_active": True}
        if brand is None:
            brand = Brand(slug=slug, market_id=None, **values)
            session.add(brand)
            counts["created"] += 1
            await session.flush()
        else:
            changed = update_fields(brand, **values)
            counts["updated" if changed else "unchanged"] += 1
        brands[name] = brand
    return brands


async def upsert_categories(session: AsyncSession, counts: dict[str, int]) -> dict[str, Category]:
    categories: dict[str, Category] = {}
    for index, name in enumerate(DEMO_CATEGORIES, start=1):
        slug = slugify(name)
        category = await session.scalar(
            select(Category).where(Category.slug == slug, Category.market_id.is_(None))
        )
        values = {
            "name": name,
            "sort_order": index * 10,
            "is_global": True,
            "is_active": True,
        }
        if category is None:
            category = Category(slug=slug, market_id=None, **values)
            session.add(category)
            counts["created"] += 1
            await session.flush()
        else:
            changed = update_fields(category, **values)
            counts["updated" if changed else "unchanged"] += 1
        categories[name] = category
    return categories


async def upsert_products(
    session: AsyncSession,
    brands: dict[str, Brand],
    categories: dict[str, Category],
    markets_by_slug: dict[str, Market],
    counts: dict[str, int],
) -> None:
    for seed in DEMO_PRODUCTS:
        product = await session.scalar(
            select(Product)
            .where(Product.barcode == seed.barcode, Product.market_id.is_(None))
        )
        values = {
            "name": seed.name,
            "short_name": seed.name,
            "brand_id": brands[seed.brand].id,
            "category_id": categories[seed.category].id,
            "package_size": seed.package_size,
            "is_global": True,
            "is_active": True,
            "quality_score": 80,
        }
        if product is None:
            product = Product(barcode=seed.barcode, market_id=None, **values)
            session.add(product)
            counts["created"] += 1
            await session.flush()
        else:
            changed = update_fields(product, **values)
            counts["updated" if changed else "unchanged"] += 1

        await upsert_aliases(session, product, seed.aliases, counts)
        await upsert_product_image(session, product, seed, counts)

    for market_slug, seed in DEMO_MARKET_PRODUCTS:
        market = markets_by_slug[market_slug]
        product = await session.scalar(
            select(Product).where(Product.barcode == seed.barcode, Product.market_id == market.id)
        )
        values = {
            "name": seed.name,
            "short_name": seed.name,
            "brand_id": brands[seed.brand].id,
            "category_id": categories[seed.category].id,
            "package_size": seed.package_size,
            "is_global": False,
            "is_active": True,
            "quality_score": 80,
        }
        if product is None:
            product = Product(barcode=seed.barcode, market_id=market.id, **values)
            session.add(product)
            counts["created"] += 1
            await session.flush()
        else:
            changed = update_fields(product, **values)
            counts["updated" if changed else "unchanged"] += 1

        await upsert_aliases(session, product, seed.aliases, counts)
        await upsert_product_image(session, product, seed, counts)


async def upsert_aliases(
    session: AsyncSession,
    product: Product,
    aliases: tuple[str, ...],
    counts: dict[str, int],
) -> None:
    result = await session.execute(
        select(ProductAlias.normalized_alias).where(ProductAlias.product_id == product.id)
    )
    existing = set(result.scalars().all())
    for alias in aliases:
        normalized = normalize_alias(alias)
        if normalized in existing:
            counts["unchanged"] += 1
            continue
        session.add(ProductAlias(product_id=product.id, alias=alias, normalized_alias=normalized, source="seed"))
        counts["created"] += 1
        existing.add(normalized)
    await session.flush()


async def upsert_product_image(
    session: AsyncSession,
    product: Product,
    seed: ProductSeed,
    counts: dict[str, int],
) -> None:
    existing_image_id = await session.scalar(
        select(ProductImage.id).where(ProductImage.product_id == product.id).limit(1)
    )
    if existing_image_id is not None:
        counts["unchanged"] += 1
        return

    image_slug = slugify(seed.name)
    session.add(
        ProductImage(
            product_id=product.id,
            url=f"https://example.com/leafletpilot/demo/{image_slug}.png",
            image_type="main",
            mime_type="image/png",
            width=1200,
            height=1200,
            has_transparent_background=True,
            quality_status="needs_review",
            is_primary=True,
        )
    )
    counts["created"] += 1
    await session.flush()


async def upsert_templates(session: AsyncSession, counts: dict[str, int]) -> dict[str, Template]:
    templates: dict[str, Template] = {}
    for seed in DEMO_TEMPLATES:
        template = await session.scalar(
            select(Template).where(Template.slug == seed["slug"], Template.market_id.is_(None))
        )
        values = {
            "name": seed["name"],
            "description": seed["description"],
            "template_type": seed["template_type"],
            "is_global": True,
            "is_active": True,
            "config_json": seed["config_json"],
        }
        if template is None:
            template = Template(slug=seed["slug"], market_id=None, **values)
            session.add(template)
            counts["created"] += 1
            await session.flush()
        else:
            changed = update_fields(template, **values)
            counts["updated" if changed else "unchanged"] += 1
        templates[seed["slug"]] = template
    return templates


async def upsert_demo_campaign(
    session: AsyncSession,
    market: Market,
    template: Template,
    counts: dict[str, int],
) -> Campaign:
    campaign = await session.scalar(
        select(Campaign)
        .options(selectinload(Campaign.items))
        .where(
            and_(
                Campaign.market_id == market.id,
                Campaign.slug == DEMO_CAMPAIGN_SLUG,
            )
        )
    )
    if campaign is not None:
        changed = update_fields(
            campaign,
            title=DEMO_CAMPAIGN_TITLE,
            source_type="text",
            channel="panel",
            raw_input_text=DEMO_CAMPAIGN_RAW_TEXT,
            template_id=template.id,
            currency="EUR",
            language="tr",
        )
        counts["updated" if changed else "unchanged"] += 1
        return campaign

    response = await create_campaign_from_text(
        session,
        CampaignCreateFromTextRequest(
            title=DEMO_CAMPAIGN_TITLE,
            raw_text=DEMO_CAMPAIGN_RAW_TEXT,
            template_id=template.id,
            currency="EUR",
            language="tr",
            generate_suggestions=True,
        ),
        market.id,
    )
    campaign = await session.scalar(
        select(Campaign)
        .options(selectinload(Campaign.items))
        .where(Campaign.id == response.campaign_id)
    )
    if campaign is None:
        raise RuntimeError("Demo campaign was created but could not be reloaded.")
    campaign.slug = DEMO_CAMPAIGN_SLUG
    counts["created"] += 1
    await session.flush()
    return campaign


def update_fields(instance: Any, **values: Any) -> bool:
    changed = False
    for key, value in values.items():
        if getattr(instance, key) != value:
            setattr(instance, key, value)
            changed = True
    return changed


async def main() -> None:
    require_database_url()
    try:
        async with AsyncSessionLocal() as session:
            result = await seed_dev_data(session)

        print("Seeded LeafletPilot development data.")
        print(f"Demo market id: {result['market_id']}")
        print(f"Demo user email: {result['user_email']}")
        print(f"Demo staff email: {DEMO_STAFF_EMAIL}")
        print(f"Demo viewer email: {DEMO_VIEWER_EMAIL}")
        print(f"Demo campaign id: {result['campaign_id']}")
        print(
            "Rows created/updated/unchanged: "
            f"{result['created']}/{result['updated']}/{result['unchanged']}"
        )
        print("Use the demo market id as X-Market-Id for market-scoped API calls.")
    finally:
        if engine is not None:
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
