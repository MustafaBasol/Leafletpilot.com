"""HTTP acceptance tests for the Phase 28D market catalog import.

Requires TEST_DATABASE_URL (a disposable PostgreSQL 16 instance); tests skip
themselves otherwise, matching the convention used by
test_platform_catalog_acceptance.py.
"""
from datetime import timedelta
from io import BytesIO
from uuid import uuid4

import httpx
import pytest
from openpyxl import Workbook
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.security import create_access_token, create_platform_access_token, hash_password
from app.main import app
from app.models import (
    Brand,
    Category,
    Market,
    MarketCatalogImport,
    MarketProduct,
    MarketUser,
    PlatformAdmin,
    Product,
    User,
)
from app.models.base import utc_now
from app.services.market_catalog_excel import COLUMNS


def _workbook_bytes(rows: list[tuple]) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.title = "Ürünler"
    sheet.append(COLUMNS)
    for row in rows:
        sheet.append(row)
    stream = BytesIO()
    book.save(stream)
    return stream.getvalue()


def _row(
    product_name="", brand="", barcode="", package_amount="", package_unit="",
    package_type="", package_size="", category="", price="", promo_price="",
    currency="", sku="", image_url="",
) -> tuple:
    return (
        product_name, brand, barcode, package_amount, package_unit, package_type,
        package_size, category, price, promo_price, currency, sku, image_url,
    )


async def _seed(prefix: str) -> dict:
    async with AsyncSessionLocal() as session:
        admin = PlatformAdmin(email=f"{prefix}@example.test", full_name="Import Admin", password_hash=hash_password("phase-28d-password"))
        market = Market(name=f"{prefix} Market", slug=f"{prefix}-market", subscription_plan="starter", currency="EUR")
        other_market = Market(name=f"{prefix} Other Market", slug=f"{prefix}-other-market", subscription_plan="starter", currency="EUR")
        user = User(email=f"{prefix}-owner@example.test", full_name="Market Owner", password_hash=hash_password("market-password"))
        session.add_all([admin, market, other_market, user])
        await session.flush()
        session.add(MarketUser(market_id=market.id, user_id=user.id, role="market_admin"))

        brand = Brand(name=f"{prefix} Ülker", slug=f"{prefix}-ulker", is_global=True)
        category = Category(name=f"{prefix} Atıştırmalık", slug=f"{prefix}-atistirmalik", is_global=True)
        session.add_all([brand, category])
        await session.flush()

        exact_match_product = Product(
            name=f"{prefix} Çokomel", barcode=f"{prefix}-8690504039025", brand_id=brand.id,
            category_id=category.id, package_amount="24", package_unit="g", is_global=True,
        )
        adopted_product = Product(
            name=f"{prefix} Ayran", barcode=f"{prefix}-ayran-barcode", package_amount="1000", package_unit="ml", is_global=True,
        )
        merge_winner = Product(
            name=f"{prefix} Merge Winner", barcode=f"{prefix}-winner-barcode", package_amount="500", package_unit="ml", is_global=True,
        )
        session.add_all([exact_match_product, adopted_product, merge_winner])
        await session.flush()
        merge_source = Product(
            name=f"{prefix} Merge Source", barcode=f"{prefix}-tombstone-barcode", package_amount="500", package_unit="ml",
            is_global=True, is_active=False, merged_into_product_id=merge_winner.id,
        )
        session.add(merge_source)
        await session.flush()

        adopted_market_product = MarketProduct(market_id=market.id, product_id=adopted_product.id, regular_price="1.50", currency="EUR")
        session.add(adopted_market_product)
        await session.commit()
        return {
            "admin": admin, "market": market, "other_market": other_market, "user": user,
            "brand": brand, "category": category,
            "exact_match_product": exact_match_product, "adopted_product": adopted_product,
            "adopted_market_product": adopted_market_product, "merge_winner": merge_winner,
        }


@pytest.mark.asyncio
async def test_market_user_forbidden_platform_admin_allowed_when_test_database_url_is_configured() -> None:
    if AsyncSessionLocal is None:
        pytest.skip("DATABASE_URL is not configured.")
    prefix = f"import-auth-{uuid4().hex[:8]}"
    seeded = await _seed(prefix)
    market_token = create_access_token(str(seeded["user"].id))
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")
    try:
        content = _workbook_bytes([_row(product_name="Test Ürün", price="1.00")])
        files = {"workbook": ("import.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        market_id = seeded["market"].id
        assert (await client.post(f"/api/platform/markets/{market_id}/catalog-import/preview", headers={"Authorization": f"Bearer {market_token}"}, files=files)).status_code == 401
        assert (await client.get(f"/api/platform/markets/{market_id}/catalog-import/template")).status_code == 401
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_preview_classifies_every_row_state_and_projects_quota_when_test_database_url_is_configured() -> None:
    if AsyncSessionLocal is None:
        pytest.skip("DATABASE_URL is not configured.")
    prefix = f"import-preview-{uuid4().hex[:8]}"
    seeded = await _seed(prefix)
    market = seeded["market"]
    admin_headers = {"Authorization": f"Bearer {create_platform_access_token(str(seeded['admin'].id))}"}

    rows = [
        _row(product_name=seeded["exact_match_product"].name, barcode=seeded["exact_match_product"].barcode, price="12.90"),
        _row(product_name=f"{prefix} Brand New Local Item", price="3.50"),
        _row(product_name="Ayran Refill", barcode=seeded["adopted_product"].barcode, price="1.80"),
        _row(product_name="Tombstone Buyer", barcode=seeded["merge_winner"].barcode.replace("winner", "tombstone"), price="2.00"),
        _row(product_name="Duplicate A", barcode="4001234567890", price="5.00"),
        _row(product_name="Duplicate A again", barcode="4001234567890", price="5.00"),
        _row(product_name="Conflict A", barcode="4009876543210", price="5.00"),
        _row(product_name="Conflict A again", barcode="4009876543210", price="6.00"),
        _row(product_name="", price="1.00"),
        _row(product_name="Bad Currency Item", price="1.00", currency="ZZZ"),
    ]
    content = _workbook_bytes(rows)
    files = {"workbook": ("import.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")
    try:
        response = await client.post(f"/api/platform/markets/{market.id}/catalog-import/preview", headers=admin_headers, files=files)
        assert response.status_code == 200, response.text
        body = response.json()
        by_row = {row["row"]: row for row in body["rows"]}

        assert by_row[2]["state"] == "global_exact_match"
        assert by_row[2]["proposed_action"] == "adopt_global"

        assert by_row[3]["state"] == "new_market_local"
        assert by_row[3]["proposed_action"] == "create_local"

        assert by_row[4]["state"] == "existing_market_product"
        assert by_row[4]["existing_market_product_id"] == str(seeded["adopted_market_product"].id)

        assert by_row[5]["state"] == "global_strong_match", by_row[5]
        assert by_row[5]["global_match"]["candidates"][0]["name"] == seeded["merge_winner"].name

        # First occurrence in a matching pair proceeds under its own natural
        # classification; only the later duplicate(s) are marked blocked.
        assert by_row[6]["state"] == "new_market_local"
        assert by_row[7]["state"] == "duplicate_in_file"
        assert by_row[7]["duplicate_of_row"] == 6

        assert by_row[8]["state"] == "conflict"
        assert by_row[9]["state"] == "conflict"

        assert by_row[10]["state"] == "invalid"
        assert by_row[11]["state"] == "invalid"

        counts = body["counts"]
        assert counts["total"] == 10
        assert counts["invalid"] == 2
        assert counts["duplicate_in_file"] == 1
        assert counts["conflict"] == 2

        quota = body["quota"]
        assert quota["limit"] == 25
        assert quota["projected_new_local"] == 2
        assert quota["would_exceed"] is False

        async with AsyncSessionLocal() as session:
            job = await session.get(MarketCatalogImport, body["import_id"])
            assert job is not None
            assert job.status == "previewed"
            assert job.preview_payload is not None
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_commit_creates_adopts_updates_and_enforces_entitlements_when_test_database_url_is_configured() -> None:
    if AsyncSessionLocal is None:
        pytest.skip("DATABASE_URL is not configured.")
    prefix = f"import-commit-{uuid4().hex[:8]}"
    seeded = await _seed(prefix)
    market = seeded["market"]
    admin_headers = {"Authorization": f"Bearer {create_platform_access_token(str(seeded['admin'].id))}"}

    async with AsyncSessionLocal() as session:
        for index in range(24):
            session.add(MarketProduct(market_id=market.id, private_name=f"{prefix} Filler {index}", regular_price="1.00", currency="EUR"))
        await session.commit()

    rows = [
        _row(product_name=seeded["exact_match_product"].name, barcode=seeded["exact_match_product"].barcode, price="12.90"),
        _row(product_name="Ayran Refill", barcode=seeded["adopted_product"].barcode, price="2.20"),
        _row(product_name=f"{prefix} Only Room For One", price="3.50"),
        _row(product_name=f"{prefix} Over Quota Item", price="4.50"),
    ]
    content = _workbook_bytes(rows)
    files = {"workbook": ("import.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")
    try:
        preview = (await client.post(f"/api/platform/markets/{market.id}/catalog-import/preview", headers=admin_headers, files=files)).json()
        import_id = preview["import_id"]
        assert preview["quota"]["would_exceed"] is True

        commit = await client.post(f"/api/platform/markets/{market.id}/catalog-import/{import_id}/commit", headers=admin_headers, json={"decisions": {}})
        assert commit.status_code == 200, commit.text
        result = commit.json()
        by_row = {row["row"]: row for row in result["rows"]}
        assert by_row[2]["outcome"] == "success"
        assert by_row[3]["outcome"] == "success"
        assert by_row[4]["outcome"] == "success"
        assert by_row[5]["outcome"] == "failed"
        assert "limit" in by_row[5]["error"].lower()
        assert result["imported_rows"] == 2
        assert result["updated_rows"] == 1
        assert result["failed_rows"] == 1

        async with AsyncSessionLocal() as session:
            job = await session.get(MarketCatalogImport, import_id)
            assert job.status == "committed"
            assert job.preview_payload is None
            assert job.imported_rows == 2
            assert job.updated_rows == 1
            assert job.failed_rows == 1

            adopted = await session.scalar(
                select(MarketProduct).where(MarketProduct.market_id == market.id, MarketProduct.product_id == seeded["exact_match_product"].id)
            )
            assert adopted is not None
            assert str(adopted.regular_price) == "12.90"

            updated_existing = await session.get(MarketProduct, seeded["adopted_market_product"].id)
            assert str(updated_existing.regular_price) == "2.20"

            new_local = await session.scalar(
                select(MarketProduct).where(MarketProduct.market_id == market.id, MarketProduct.private_name == f"{prefix} Only Room For One")
            )
            assert new_local is not None

            over_quota = await session.scalar(
                select(MarketProduct).where(MarketProduct.market_id == market.id, MarketProduct.private_name == f"{prefix} Over Quota Item")
            )
            assert over_quota is None

        # Committing again is rejected; the job is terminal.
        recommit = await client.post(f"/api/platform/markets/{market.id}/catalog-import/{import_id}/commit", headers=admin_headers, json={"decisions": {}})
        assert recommit.status_code == 409
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_ambiguous_row_requires_explicit_decision_when_test_database_url_is_configured() -> None:
    if AsyncSessionLocal is None:
        pytest.skip("DATABASE_URL is not configured.")
    prefix = f"import-ambiguous-{uuid4().hex[:8]}"
    seeded = await _seed(prefix)
    market = seeded["market"]
    admin_headers = {"Authorization": f"Bearer {create_platform_access_token(str(seeded['admin'].id))}"}

    async with AsyncSessionLocal() as session:
        twin_brand = Brand(name=f"{prefix} Twin Brand", slug=f"{prefix}-twin-brand", is_global=True)
        session.add(twin_brand)
        await session.flush()
        twin_a = Product(name=f"{prefix} Twin Product", brand_id=twin_brand.id, package_amount="100", package_unit="g", is_global=True)
        twin_b = Product(name=f"{prefix} Twin Product", brand_id=twin_brand.id, package_amount="100", package_unit="g", is_global=True)
        session.add_all([twin_a, twin_b])
        await session.commit()
        twin_a_id, twin_b_id = str(twin_a.id), str(twin_b.id)

    rows = [_row(product_name=f"{prefix} Twin Product", brand=f"{prefix} Twin Brand", package_size="100g", price="9.00")]
    content = _workbook_bytes(rows)
    files = {"workbook": ("import.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")
    try:
        preview = (await client.post(f"/api/platform/markets/{market.id}/catalog-import/preview", headers=admin_headers, files=files)).json()
        import_id = preview["import_id"]
        assert preview["rows"][0]["state"] == "global_ambiguous"
        candidate_ids = {candidate["product_id"] for candidate in preview["rows"][0]["global_match"]["candidates"]}
        assert candidate_ids == {twin_a_id, twin_b_id}

        # No decision: the row is skipped, not silently auto-picked.
        skipped_commit = await client.post(f"/api/platform/markets/{market.id}/catalog-import/{import_id}/commit", headers=admin_headers, json={"decisions": {}})
        assert skipped_commit.json()["rows"][0]["outcome"] == "skipped"

        second_preview = (await client.post(f"/api/platform/markets/{market.id}/catalog-import/preview", headers=admin_headers, files={"workbook": ("import.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})).json()
        second_import_id = second_preview["import_id"]
        resolved_commit = await client.post(
            f"/api/platform/markets/{market.id}/catalog-import/{second_import_id}/commit",
            headers=admin_headers,
            json={"decisions": {"2": {"action": "adopt_global", "target_id": twin_a_id}}},
        )
        assert resolved_commit.status_code == 200, resolved_commit.text
        assert resolved_commit.json()["rows"][0]["outcome"] == "success"

        async with AsyncSessionLocal() as session:
            adopted = await session.scalar(select(MarketProduct).where(MarketProduct.market_id == market.id, MarketProduct.product_id == twin_a_id))
            assert adopted is not None
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_tenant_isolation_and_stale_preview_when_test_database_url_is_configured() -> None:
    if AsyncSessionLocal is None:
        pytest.skip("DATABASE_URL is not configured.")
    prefix = f"import-isolation-{uuid4().hex[:8]}"
    seeded = await _seed(prefix)
    market = seeded["market"]
    other_market = seeded["other_market"]
    admin_headers = {"Authorization": f"Bearer {create_platform_access_token(str(seeded['admin'].id))}"}

    content = _workbook_bytes([_row(product_name=f"{prefix} Isolated Item", price="1.00")])
    files = {"workbook": ("import.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")
    try:
        preview = (await client.post(f"/api/platform/markets/{market.id}/catalog-import/preview", headers=admin_headers, files=files)).json()
        import_id = preview["import_id"]

        # Committing a market A preview against market B's URL must 404, not
        # silently import into the wrong tenant.
        cross_tenant = await client.post(f"/api/platform/markets/{other_market.id}/catalog-import/{import_id}/commit", headers=admin_headers, json={"decisions": {}})
        assert cross_tenant.status_code == 404

        async with AsyncSessionLocal() as session:
            job = await session.get(MarketCatalogImport, import_id)
            job.expires_at = utc_now() - timedelta(minutes=1)
            await session.commit()

        expired_commit = await client.post(f"/api/platform/markets/{market.id}/catalog-import/{import_id}/commit", headers=admin_headers, json={"decisions": {}})
        assert expired_commit.status_code == 410

        async with AsyncSessionLocal() as session:
            job = await session.get(MarketCatalogImport, import_id)
            assert job.status == "expired"
            no_leak = await session.scalar(
                select(MarketProduct).where(MarketProduct.market_id == other_market.id, MarketProduct.private_name == f"{prefix} Isolated Item")
            )
            assert no_leak is None
    finally:
        await client.aclose()
