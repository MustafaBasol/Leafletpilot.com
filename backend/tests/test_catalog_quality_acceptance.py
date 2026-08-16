"""Disposable-PostgreSQL HTTP acceptance for global catalog dedup and merge.

Mirrors test_platform_catalog_acceptance.py: real HTTP surface, disposable
PostgreSQL 16, skips when DATABASE_URL/TEST_DATABASE_URL are not configured.
"""

import io
from uuid import uuid4

import httpx
import pytest
from openpyxl import Workbook
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.security import create_access_token, create_platform_access_token, hash_password
from app.main import app
from app.services.catalog import normalize_alias
from app.services.global_catalog_excel import COLUMNS
from app.models import (
    Brand,
    CampaignItem,
    Category,
    CatalogQualityDecision,
    Campaign,
    Market,
    MarketProduct,
    MarketUser,
    PlatformAdmin,
    Product,
    ProductAlias,
    ProductImage,
    User,
)


async def _seed(prefix: str) -> dict:
    async with AsyncSessionLocal() as session:
        admin = PlatformAdmin(email=f"{prefix}@example.test", full_name="Quality Admin", password_hash=hash_password("phase-c-password"))
        market_user = User(email=f"{prefix}-user@example.test", full_name="Market User", password_hash=hash_password("market-password"))
        markets = [Market(name=f"{prefix} Market {i}", slug=f"{prefix}-mk-{i}", subscription_plan="growth") for i in ("a", "b", "c")]
        brand = Brand(name=f"{prefix} Brand", slug=f"{prefix}-brand", is_global=True)
        category = Category(name=f"{prefix} Category", slug=f"{prefix}-category", is_global=True)
        session.add_all([admin, market_user, *markets, brand, category])
        await session.flush()
        session.add(MarketUser(market_id=markets[0].id, user_id=market_user.id, role="market_admin"))
        await session.commit()
        return {"admin": admin, "market_user": market_user, "markets": markets, "brand": brand, "category": category}


def _product(prefix: str, name: str, *, brand_id, package_size="1 L", barcode=None, is_active=True) -> Product:
    return Product(
        name=f"{prefix} {name}",
        barcode=barcode,
        brand_id=brand_id,
        package_size=package_size,
        is_global=True,
        is_active=is_active,
    )


@pytest.mark.asyncio
async def test_global_product_merge_relinks_market_adoption_moves_alias_and_flattens_redirect_chain() -> None:
    if AsyncSessionLocal is None:
        pytest.skip("DATABASE_URL is not configured.")

    prefix = f"merge-{uuid4().hex[:8]}"
    seeded = await _seed(prefix)
    async with AsyncSessionLocal() as session:
        winner = _product(prefix, "Cola 1L", brand_id=seeded["brand"].id)
        loser = _product(prefix, "Cola 1L", brand_id=seeded["brand"].id)
        session.add_all([winner, loser])
        await session.flush()
        session.add(ProductAlias(product_id=loser.id, alias="Fresh Cola", normalized_alias=normalize_alias("Fresh Cola")))
        # This alias duplicates the winner's own canonical name and must be
        # deduplicated (deleted), never copied onto the winner a second time.
        session.add(ProductAlias(product_id=loser.id, alias=winner.name, normalized_alias=normalize_alias(winner.name)))
        session.add(ProductImage(product_id=loser.id, url="https://example.test/loser.png", mime_type="image/png", quality_status="good", is_primary=True))
        session.add(MarketProduct(market_id=seeded["markets"][0].id, product_id=loser.id, regular_price="3.10", badge_text="Kampanya"))
        await session.commit()
        winner_id, loser_id, market_id = winner.id, loser.id, seeded["markets"][0].id

    headers = {"Authorization": f"Bearer {create_platform_access_token(str(seeded['admin'].id))}"}
    market_headers = {"Authorization": f"Bearer {create_access_token(str(seeded['market_user'].id))}", "X-Market-Id": str(market_id)}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        assert (await client.get("/api/platform/catalog/quality/candidates", headers=market_headers)).status_code == 401
        assert (await client.get("/api/platform/catalog/quality/candidates")).status_code == 401

        preview = await client.post("/api/platform/catalog/quality/merge-preview", headers=headers, json={"source_product_id": str(loser_id), "target_product_id": str(winner_id)})
        assert preview.status_code == 200
        body = preview.json()
        assert body["can_merge"] is True
        assert body["aliases"]["move_count"] == 1
        assert body["aliases"]["deduplicated_count"] == 1
        assert body["images"]["move_count"] == 1
        assert body["market_adoptions"]["source_count"] == 1

        merged = await client.post("/api/platform/catalog/quality/merge", headers=headers, json={"source_product_id": str(loser_id), "target_product_id": str(winner_id)})
        assert merged.status_code == 200
        counts = merged.json()["migration_counts"]
        assert counts["aliases_moved"] == 1
        assert counts["aliases_deduplicated"] == 1
        assert counts["images_moved"] == 1
        assert counts["market_adoptions_relinked"] == 1

        # Self merge, already-merged source, and merging into a redirect all reject.
        assert (await client.post("/api/platform/catalog/quality/merge", headers=headers, json={"source_product_id": str(winner_id), "target_product_id": str(winner_id)})).status_code == 409
        assert (await client.post("/api/platform/catalog/quality/merge", headers=headers, json={"source_product_id": str(loser_id), "target_product_id": str(winner_id)})).status_code == 409

    async with AsyncSessionLocal() as session:
        loser_row = await session.get(Product, loser_id)
        assert loser_row.is_active is False
        assert loser_row.merged_into_product_id == winner_id
        moved_alias = await session.scalar(select(ProductAlias).where(ProductAlias.normalized_alias == "fresh cola"))
        assert moved_alias.product_id == winner_id
        dedup_count = await session.scalar(select(ProductAlias).where(ProductAlias.product_id == loser_id, ProductAlias.normalized_alias == normalize_alias(winner.name)))
        assert dedup_count is None
        winner_images = list((await session.scalars(select(ProductImage).where(ProductImage.product_id == winner_id))).all())
        assert len(winner_images) == 1 and winner_images[0].is_primary is False
        adoption = await session.scalar(select(MarketProduct).where(MarketProduct.market_id == market_id))
        assert adoption.product_id == winner_id
        assert str(adoption.regular_price) == "3.10"
        assert adoption.badge_text == "Kampanya"

        # Chained merge: winner now becomes the loser of a later merge. The
        # earlier redirect (loser -> winner) must flatten to the new target
        # instead of going stale on an inactive intermediate tombstone.
        final_target = _product(prefix, "Cola 1L", brand_id=seeded["brand"].id)
        session.add(final_target)
        await session.commit()
        final_target_id = final_target.id

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        chained = await client.post("/api/platform/catalog/quality/merge", headers=headers, json={"source_product_id": str(winner_id), "target_product_id": str(final_target_id)})
        assert chained.status_code == 200
        assert chained.json()["migration_counts"]["redirects_flattened"] == 1

    async with AsyncSessionLocal() as session:
        loser_row = await session.get(Product, loser_id)
        winner_row = await session.get(Product, winner_id)
        assert winner_row.merged_into_product_id == final_target_id
        assert loser_row.merged_into_product_id == final_target_id  # flattened, not stale on winner_id


@pytest.mark.asyncio
async def test_dual_market_adoption_blocks_merge_without_losing_either_overrides() -> None:
    if AsyncSessionLocal is None:
        pytest.skip("DATABASE_URL is not configured.")

    prefix = f"dual-{uuid4().hex[:8]}"
    seeded = await _seed(prefix)
    async with AsyncSessionLocal() as session:
        winner = _product(prefix, "Bread 500g", brand_id=seeded["brand"].id, package_size="500 g")
        loser = _product(prefix, "Bread 500g", brand_id=seeded["brand"].id, package_size="500 g")
        session.add_all([winner, loser])
        await session.flush()
        market_id = seeded["markets"][1].id
        session.add(MarketProduct(market_id=market_id, product_id=winner.id, regular_price="1.00"))
        session.add(MarketProduct(market_id=market_id, product_id=loser.id, regular_price="1.50", badge_text="Son Gün"))
        await session.commit()
        winner_id, loser_id = winner.id, loser.id

    headers = {"Authorization": f"Bearer {create_platform_access_token(str(seeded['admin'].id))}"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        preview = await client.post("/api/platform/catalog/quality/merge-preview", headers=headers, json={"source_product_id": str(loser_id), "target_product_id": str(winner_id)})
        assert preview.status_code == 200
        assert preview.json()["can_merge"] is False
        assert preview.json()["market_adoptions"]["conflict_markets"]

        blocked = await client.post("/api/platform/catalog/quality/merge", headers=headers, json={"source_product_id": str(loser_id), "target_product_id": str(winner_id)})
        assert blocked.status_code == 409

    async with AsyncSessionLocal() as session:
        rows = list((await session.scalars(select(MarketProduct).where(MarketProduct.product_id.in_((winner_id, loser_id))))).all())
        assert len(rows) == 2
        by_price = {str(row.regular_price) for row in rows}
        assert by_price == {"1.00", "1.50"}
        loser_row = await session.get(Product, loser_id)
        assert loser_row.is_active is True and loser_row.merged_into_product_id is None


@pytest.mark.asyncio
async def test_historical_campaign_reference_keeps_loser_images_on_the_redirect() -> None:
    if AsyncSessionLocal is None:
        pytest.skip("DATABASE_URL is not configured.")

    prefix = f"hist-{uuid4().hex[:8]}"
    seeded = await _seed(prefix)
    async with AsyncSessionLocal() as session:
        winner = _product(prefix, "Milk 1L", brand_id=seeded["brand"].id)
        loser = _product(prefix, "Milk 1L", brand_id=seeded["brand"].id)
        session.add_all([winner, loser])
        await session.flush()
        session.add(ProductImage(product_id=loser.id, url="https://example.test/milk-loser.png", mime_type="image/png", quality_status="good", is_primary=True))
        campaign = Campaign(market_id=seeded["markets"][0].id, title=f"{prefix} campaign")
        session.add(campaign)
        await session.flush()
        session.add(CampaignItem(campaign_id=campaign.id, market_id=seeded["markets"][0].id, product_id=loser.id, raw_line="Milk 1L", incoming_name="Milk 1L"))
        await session.commit()
        winner_id, loser_id, campaign_id = winner.id, loser.id, campaign.id

    headers = {"Authorization": f"Bearer {create_platform_access_token(str(seeded['admin'].id))}"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        preview = (await client.post("/api/platform/catalog/quality/merge-preview", headers=headers, json={"source_product_id": str(loser_id), "target_product_id": str(winner_id)})).json()
        assert preview["historical_references"]["campaign_items"] == 1
        assert preview["images"]["move_count"] == 0
        assert preview["images"]["historical_retention"] is True

        merged = await client.post("/api/platform/catalog/quality/merge", headers=headers, json={"source_product_id": str(loser_id), "target_product_id": str(winner_id)})
        assert merged.status_code == 200
        assert merged.json()["migration_counts"]["images_moved"] == 0
        assert merged.json()["migration_counts"]["campaign_items_retained"] == 1

    async with AsyncSessionLocal() as session:
        item = (await session.scalars(select(CampaignItem).where(CampaignItem.campaign_id == campaign_id))).one()
        assert item.product_id == loser_id  # historical evidence is never rewritten
        loser_image = await session.scalar(select(ProductImage).where(ProductImage.product_id == loser_id))
        assert loser_image is not None  # image stayed on the redirect, not silently dropped


@pytest.mark.asyncio
async def test_ignore_decision_hides_candidate_until_state_filter_requests_it() -> None:
    if AsyncSessionLocal is None:
        pytest.skip("DATABASE_URL is not configured.")

    prefix = f"ignore-{uuid4().hex[:8]}"
    seeded = await _seed(prefix)
    async with AsyncSessionLocal() as session:
        shared_barcode = f"{prefix}-shared-barcode-9001"
        first = _product(prefix, "Ignore Candidate", brand_id=seeded["brand"].id, barcode=shared_barcode)
        second = _product(prefix, "Ignore Candidate", brand_id=seeded["brand"].id, barcode=shared_barcode)
        session.add_all([first, second])
        await session.commit()
        first_id, second_id = first.id, second.id

    headers = {"Authorization": f"Bearer {create_platform_access_token(str(seeded['admin'].id))}"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        candidates = (await client.get("/api/platform/catalog/quality/candidates", headers=headers, params={"limit": 100})).json()
        pair_ids = {(item["product_a"]["id"], item["product_b"]["id"]) for item in candidates["items"]}
        assert (str(min(first_id, second_id, key=str)), str(max(first_id, second_id, key=str))) in pair_ids

        ignore = await client.post("/api/platform/catalog/quality/ignore", headers=headers, json={"product_a_id": str(first_id), "product_b_id": str(second_id), "note": "Different SKUs"})
        assert ignore.status_code == 200

        after = (await client.get("/api/platform/catalog/quality/candidates", headers=headers, params={"limit": 100})).json()
        after_pairs = {(item["product_a"]["id"], item["product_b"]["id"]) for item in after["items"]}
        assert (str(min(first_id, second_id, key=str)), str(max(first_id, second_id, key=str))) not in after_pairs

        ignored_view = (await client.get("/api/platform/catalog/quality/candidates", headers=headers, params={"state": "ignored", "limit": 100})).json()
        assert any(item["state"] == "ignored" for item in ignored_view["items"])

        # Idempotent: reaffirming the same decision must not create a duplicate row.
        assert (await client.post("/api/platform/catalog/quality/ignore", headers=headers, json={"product_a_id": str(second_id), "product_b_id": str(first_id)})).status_code == 200

    async with AsyncSessionLocal() as session:
        decisions = list((await session.scalars(select(CatalogQualityDecision).where(CatalogQualityDecision.product_a_id.in_((first_id, second_id))))).all())
        assert len(decisions) == 1


@pytest.mark.asyncio
async def test_global_product_create_and_update_reject_normalized_collisions_but_allow_reuse_after_merge() -> None:
    if AsyncSessionLocal is None:
        pytest.skip("DATABASE_URL is not configured.")

    prefix = f"collide-{uuid4().hex[:8]}"
    seeded = await _seed(prefix)
    headers = {"Authorization": f"Bearer {create_platform_access_token(str(seeded['admin'].id))}"}
    # Purely numeric so normalize_barcode() collapses punctuation differences
    # (an alphanumeric SKU-style barcode is deliberately kept in its own
    # namespace and would not collide here).
    digits = str(uuid4().int % 10**12).zfill(12)
    base_barcode = f"{digits[:4]}-{digits[4:8]} {digits[8:]}"
    variant_barcode = digits
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        created = await client.post("/api/platform/catalog/products", headers=headers, json={"name": f"{prefix} Base Product", "barcode": base_barcode})
        assert created.status_code == 201
        base_id = created.json()["id"]

        # Same digits, different formatting: must resolve to the same normalized barcode.
        collided = await client.post("/api/platform/catalog/products", headers=headers, json={"name": f"{prefix} Other Product", "barcode": variant_barcode})
        assert collided.status_code == 409

        other = await client.post("/api/platform/catalog/products", headers=headers, json={"name": f"{prefix} Second Product"})
        assert other.status_code == 201
        other_id = other.json()["id"]
        collided_update = await client.patch(f"/api/platform/catalog/products/{other_id}", headers=headers, json={"barcode": variant_barcode})
        assert collided_update.status_code == 409

        # Updating a product with its own unchanged barcode must not self-collide.
        unchanged = await client.patch(f"/api/platform/catalog/products/{base_id}", headers=headers, json={"short_name": "Base"})
        assert unchanged.status_code == 200

        # Once the base product is merged away it becomes a tombstone; its
        # normalized barcode must be free for reuse, not permanently reserved.
        # The target shares the base product's canonical name so the merge's
        # identity-overlap check passes; it is seeded directly (not through the
        # create endpoint) since two active products can never share an identity.
        async with AsyncSessionLocal() as session:
            merge_target = Product(name=f"{prefix} Base Product", is_global=True, is_active=True)
            session.add(merge_target)
            await session.commit()
            target_id = merge_target.id
        merged = await client.post("/api/platform/catalog/quality/merge", headers=headers, json={"source_product_id": base_id, "target_product_id": str(target_id)})
        assert merged.status_code == 200

        reused = await client.post("/api/platform/catalog/products", headers=headers, json={"name": f"{prefix} Reused Barcode Product", "barcode": variant_barcode})
        assert reused.status_code == 201


@pytest.mark.asyncio
async def test_excel_import_does_not_resurrect_a_merged_tombstone() -> None:
    if AsyncSessionLocal is None:
        pytest.skip("DATABASE_URL is not configured.")

    prefix = f"import-tombstone-{uuid4().hex[:8]}"
    seeded = await _seed(prefix)
    digits = str(uuid4().int % 10**12).zfill(12)
    async with AsyncSessionLocal() as session:
        winner = _product(prefix, "Yogurt 1L", brand_id=seeded["brand"].id)
        loser = _product(prefix, "Yogurt 1L", brand_id=seeded["brand"].id, barcode=digits)
        session.add_all([winner, loser])
        await session.commit()
        winner_id, loser_id = winner.id, loser.id

    headers = {"Authorization": f"Bearer {create_platform_access_token(str(seeded['admin'].id))}"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        merged = await client.post("/api/platform/catalog/quality/merge", headers=headers, json={"source_product_id": str(loser_id), "target_product_id": str(winner_id)})
        assert merged.status_code == 200

        book = Workbook()
        sheet = book.active
        sheet.title = "Ürünler"
        sheet.append(COLUMNS)
        sheet.append((f"{prefix} Yogurt 1L Reimport", seeded["brand"].name, seeded["category"].name, digits, "1", "L", "", "true", ""))
        workbook = io.BytesIO()
        book.save(workbook)
        content = workbook.getvalue()

        import_headers = {**headers, "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
        preview = await client.post("/api/platform/catalog/products/import/preview", headers=import_headers, content=content)
        assert preview.status_code == 200
        assert preview.json()["counts"]["new"] == 1
        assert preview.json()["rows"][0]["product_id"] is None  # never matched to the tombstoned loser

        imported = await client.post("/api/platform/catalog/products/import", headers=import_headers, content=content)
        assert imported.status_code == 200
        assert imported.json()["created"] == 1

    async with AsyncSessionLocal() as session:
        rows = list((await session.scalars(select(Product).where(Product.barcode == digits))).all())
        assert len(rows) == 2  # the tombstoned loser plus the freshly created product
        created_row = next(row for row in rows if row.id != loser_id)
        assert created_row.is_active is True
        assert created_row.merged_into_product_id is None
        loser_row = next(row for row in rows if row.id == loser_id)
        assert loser_row.is_active is False
        assert loser_row.merged_into_product_id == winner_id
