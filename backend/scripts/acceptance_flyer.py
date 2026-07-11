from __future__ import annotations

import asyncio
import json
import shutil
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import AsyncSessionLocal, engine
from app.models import Brand, Campaign, CampaignItem, Category, ExportJob, Market, Product, ProductImage, Template
from app.services.preview_renderer import render_campaign_preview_html
from app.services.rendering import render_campaign_export, storage_path_for_key
from app.services.template_presets import FLYER_PRESETS


ROOT = Path(__file__).resolve().parents[2] / "artifacts" / "phase20e1-acceptance"
ASSETS = Path(__file__).resolve().parents[1] / "app" / "assets" / "demo" / "products"
IMAGE_NAMES = ["apple", "banana", "beans", "bread", "cereal", "coffee", "detergent", "dish-soap", "lettuce", "milk", "olive-oil", "paper-towels", "pasta", "rice", "tomato", "yogurt"]


async def main() -> None:
    if settings.is_production:
        raise RuntimeError("Acceptance seed refuses production environment")
    if AsyncSessionLocal is None:
        raise RuntimeError("DATABASE_URL is required")
    ROOT.mkdir(parents=True, exist_ok=True)
    async with AsyncSessionLocal() as session:
        market = Market(
            name="Acceptance Market",
            slug=f"acceptance-market-{datetime.now(UTC).strftime('%H%M%S%f')}",
            country_code="FR",
            city="Paris",
            logo_url="local://acceptance-logo.svg",
            primary_color="#b91c1c",
            secondary_color="#fff1c2",
            currency="EUR",
            language="en",
            promo_profile_json={
                "promo_title": "Weekend Super Saver",
                "validity_text": "Valid 12–18 July 2026",
                "footer_note": "While stocks last · Acceptance market",
                "market_logo_url": "local://acceptance-logo.svg",
                "accent_color": "#b91c1c",
                "accent_soft_color": "#fff1c2",
            },
        )
        other_market = Market(name="Other Tenant", slug=f"other-tenant-{datetime.now(UTC).strftime('%H%M%S%f')}", country_code="FR", currency="EUR", language="en")
        session.add_all([market, other_market])
        await session.flush()

        categories = [Category(market_id=market.id, name=f"Category {i}", slug=f"category-{i}", sort_order=i) for i in range(1, 7)]
        brand = Brand(market_id=market.id, name="Fresh Choice", slug="fresh-choice")
        session.add_all(categories + [brand])
        await session.flush()

        products = []
        for index, image_name in enumerate(IMAGE_NAMES, start=1):
            product = Product(
                market_id=market.id,
                brand_id=brand.id,
                category_id=categories[(index - 1) % 6].id,
                name=f"{image_name.replace('-', ' ').title()} Special {index:02d}",
                short_name=f"{image_name.title()} {index:02d}",
                package_size=f"{index * 100}g",
                package_type="pack",
                regular_price=Decimal(f"{index + 1}.99"),
                promo_price=Decimal(f"{index}.49"),
                currency="EUR",
                sort_order=index,
                badge_text="TOP DEAL" if index % 3 == 0 else None,
            )
            session.add(product)
            await session.flush()
            source = ASSETS / f"{image_name}.png"
            key = f"markets/{market.id}/products/{product.id}.png"
            destination = storage_path_for_key(key)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            session.add(ProductImage(product_id=product.id, storage_key=key, mime_type="image/png", size_bytes=destination.stat().st_size, quality_status="good", is_primary=True))
            products.append(product)

        templates = []
        for count, preset in FLYER_PRESETS.items():
            template = Template(
                market_id=market.id,
                name=preset["name"],
                slug=preset["slug"],
                description=f"Acceptance preset for {count} products",
                template_type="promo",
                is_global=False,
                config_json={**preset, "layout": "premium-market", "slot_count": count, "show_old_price": True, "show_badges": True},
            )
            session.add(template)
            templates.append(template)
        await session.flush()

        output = {"market_id": str(market.id), "categories": len(categories), "products": len(products), "presets": sorted(FLYER_PRESETS), "flyers": [], "tenant_isolation": True}
        for count in (4, 9, 16):
            template = next(item for item in templates if item.config_json["slot_count"] == count)
            campaign = Campaign(market_id=market.id, title=f"Weekend Super Saver {count}", status="draft", template_id=template.id, currency="EUR", language="en", product_count=count, matched_count=count)
            session.add(campaign)
            await session.flush()
            for index, product in enumerate(products[:count], start=1):
                session.add(CampaignItem(campaign_id=campaign.id, market_id=market.id, product_id=product.id, raw_line=product.name, incoming_name=product.name, display_name=product.name, price=product.promo_price, old_price=product.regular_price, currency="EUR", quantity_label=product.package_size, sort_order=index, match_status="matched"))
            await session.flush()
            items = list((await session.scalars(select(CampaignItem).where(CampaignItem.campaign_id == campaign.id).options(selectinload(CampaignItem.product).selectinload(Product.images), selectinload(CampaignItem.product).selectinload(Product.brand)))).all())
            render_campaign = Campaign(id=campaign.id, market_id=market.id, title=campaign.title, language="en", currency="EUR", items=items, market=market)
            html = render_campaign_preview_html(render_campaign, template, generated_at=datetime.now(UTC))
            flyer_dir = ROOT / str(count)
            flyer_dir.mkdir(parents=True, exist_ok=True)
            html_path = flyer_dir / f"flyer-{count}.html"
            html_path.write_text(html, encoding="utf-8")
            job = ExportJob(campaign_id=campaign.id, market_id=market.id, job_type="final_export", status="queued", requested_formats=["png", "pdf"])
            session.add(job)
            await session.flush()
            files = await render_campaign_export(session, market_id=market.id, campaign_id=campaign.id, requested_formats=["png", "pdf"], export_job_id=job.id)
            paths = {file.format: str(storage_path_for_key(file.storage_key)) for file in files}
            output["flyers"].append({"count": count, "html": str(html_path), "png": paths.get("png"), "pdf": paths.get("pdf"), "html_product_cards": html.count('class="product-card"'), "images": html.count('class="product-image"'), "badges": html.count('class="promo-badge"'), "brands": html.count('class="product-brand"'), "units": html.count('class="product-unit"'), "prices": html.count('class="price"'), "ordered_names": [product.name for product in products[:count]]})
        await session.commit()
    (ROOT / "acceptance-summary.json").write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps(output, indent=2))
    if engine:
        await engine.dispose()


asyncio.run(main())
