"""Platform Admin global catalog image review + bulk ZIP import acceptance.

Covers the review lifecycle (needs_review -> approved/rejected), resolver
eligibility, the tenant-override-over-global priority proof with the
Coca Cola 1L / Eti Burçak / Sütaş Yoğurt fixture, and the bulk ZIP/manifest
matching safety rules (exact/barcode/name match vs. ambiguous/unmatched/invalid).

Gated by TEST_DATABASE_URL, matching the rest of the platform-catalog suite.
"""

from __future__ import annotations

import io
import json
from decimal import Decimal
from uuid import UUID, uuid4
import zipfile

import httpx
import pytest
from PIL import Image
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.security import create_access_token, create_platform_access_token, hash_password
from app.main import app
from app.models import (
    Campaign,
    CampaignItem,
    Market,
    MarketProduct,
    MarketUser,
    PlatformAdmin,
    Product,
    ProductImage,
    User,
)
from app.services.product_image_resolution import resolve_campaign_product_images


def _png_bytes(color=(230, 40, 70)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), color).save(buffer, format="PNG")
    return buffer.getvalue()


def _zip_bytes(manifest_csv: str, images: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("manifest.csv", manifest_csv)
        for name, content in images.items():
            archive.writestr(f"images/{name}", content)
    return buffer.getvalue()


async def _seed_platform_and_market(prefix: str) -> dict:
    async with AsyncSessionLocal() as session:
        admin = PlatformAdmin(email=f"{prefix}@example.test", full_name="Review Admin", password_hash=hash_password("review-password"))
        market = Market(name=f"{prefix} Market", slug=f"{prefix}-market")
        user = User(email=f"{prefix}-owner@example.test", full_name="Market Owner", password_hash=hash_password("market-password"))
        session.add_all([admin, market, user])
        await session.flush()
        session.add(MarketUser(market_id=market.id, user_id=user.id, role="market_admin"))
        await session.commit()
        return {"admin": admin, "market": market, "user": user}


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")


@pytest.mark.asyncio
async def test_review_lifecycle_and_resolver_eligibility() -> None:
    if AsyncSessionLocal is None:
        pytest.skip("DATABASE_URL is not configured.")
    prefix = f"review-{uuid4().hex[:10]}"
    seeded = await _seed_platform_and_market(prefix)
    platform_headers = {"Authorization": f"Bearer {create_platform_access_token(str(seeded['admin'].id))}"}
    market_headers = {"Authorization": f"Bearer {create_access_token(str(seeded['user'].id))}", "X-Market-Id": str(seeded["market"].id)}

    async with AsyncSessionLocal() as session:
        product = Product(name=f"{prefix} Needs Review Product", is_global=True)
        session.add(product)
        await session.commit()
        product_id = str(product.id)
        product_name = product.name

    async with _client() as client:
        # (2) Only platform admin may upload/approve/reject global images.
        assert (await client.post(f"/api/platform/catalog/products/{product_id}/images", headers={**market_headers, "Content-Type": "image/png"}, content=_png_bytes())).status_code == 401

        # (1)/(3) A manual platform-admin upload is trusted immediately.
        uploaded = await client.post(f"/api/platform/catalog/products/{product_id}/images", headers={**platform_headers, "Content-Type": "image/png"}, content=_png_bytes(), params={"primary": True})
        assert uploaded.status_code == 201
        image_id = uploaded.json()["id"]
        uploaded_image = (await client.get("/api/platform/catalog/products", headers=platform_headers, params={"search": product_name})).json()["items"][0]["images"][0]
        assert uploaded_image["quality_status"] == "good"

        assert (await client.patch(f"/api/platform/catalog/products/{product_id}/images/{image_id}/approve", headers=market_headers)).status_code == 401
        assert (await client.patch(f"/api/platform/catalog/products/{product_id}/images/{image_id}/reject", headers=market_headers)).status_code == 401

        campaign = Campaign(id=uuid4(), market_id=seeded["market"].id, title="Review Campaign")
        campaign.items = [CampaignItem(id=uuid4(), market_id=seeded["market"].id, raw_line=product.name, incoming_name=product.name, price=Decimal("9.90"), sort_order=0)]
        async with AsyncSessionLocal() as session:
            session.add(campaign)
            await session.commit()

        # (6) The trusted manual upload is resolver-eligible immediately.
        async with AsyncSessionLocal() as session:
            summary = await resolve_campaign_product_images(session, seeded["market"].id, campaign.id)
        assert summary.resolved_count == 1

        # (4) Approval remains available for imported images and is idempotent for a trusted one.
        approved = await client.patch(f"/api/platform/catalog/products/{product_id}/images/{image_id}/approve", headers=platform_headers)
        assert approved.status_code == 200 and approved.json()["quality_status"] == "good"

        campaign2 = Campaign(id=uuid4(), market_id=seeded["market"].id, title="Review Campaign 2")
        campaign2.items = [CampaignItem(id=uuid4(), market_id=seeded["market"].id, raw_line=product.name, incoming_name=product.name, price=Decimal("9.90"), sort_order=0)]
        async with AsyncSessionLocal() as session:
            session.add(campaign2)
            await session.commit()
        async with AsyncSessionLocal() as session:
            summary2 = await resolve_campaign_product_images(session, seeded["market"].id, campaign2.id)
        assert summary2.resolved_count == 1

        # (5) Rejected image is not resolver-eligible.
        rejected = await client.patch(f"/api/platform/catalog/products/{product_id}/images/{image_id}/reject", headers=platform_headers)
        assert rejected.status_code == 200 and rejected.json()["quality_status"] == "rejected"

        campaign3 = Campaign(id=uuid4(), market_id=seeded["market"].id, title="Review Campaign 3")
        campaign3.items = [CampaignItem(id=uuid4(), market_id=seeded["market"].id, raw_line=product.name, incoming_name=product.name, price=Decimal("9.90"), sort_order=0)]
        async with AsyncSessionLocal() as session:
            session.add(campaign3)
            await session.commit()
        async with AsyncSessionLocal() as session:
            summary3 = await resolve_campaign_product_images(session, seeded["market"].id, campaign3.id)
        assert summary3.resolved_count == 0

        # (10) Replacement: upload a new primary image, delete the old one, storage stays consistent.
        replacement = await client.post(f"/api/platform/catalog/products/{product_id}/images", headers={**platform_headers, "Content-Type": "image/png"}, content=_png_bytes((10, 20, 30)), params={"primary": True})
        assert replacement.status_code == 201
        removed = await client.delete(f"/api/platform/catalog/products/{product_id}/images/{image_id}", headers=platform_headers)
        assert removed.status_code == 204
        after_replace = (await client.get("/api/platform/catalog/products", headers=platform_headers, params={"search": product_name})).json()["items"][0]
        assert sum(image["is_primary"] for image in after_replace["images"]) == 1

        # (11) Invalid images are rejected before persistence.
        invalid = await client.post(f"/api/platform/catalog/products/{product_id}/images", headers={**platform_headers, "Content-Type": "image/png"}, content=b"not-a-real-png")
        assert invalid.status_code == 422


@pytest.mark.asyncio
async def test_tenant_override_wins_over_approved_global_image() -> None:
    if AsyncSessionLocal is None:
        pytest.skip("DATABASE_URL is not configured.")
    prefix = f"priority-{uuid4().hex[:10]}"
    seeded = await _seed_platform_and_market(prefix)
    other_market = Market(name=f"{prefix} Other Market", slug=f"{prefix}-other-market")
    platform_headers = {"Authorization": f"Bearer {create_platform_access_token(str(seeded['admin'].id))}"}

    fixture_names = [f"{prefix} Coca Cola 1L", f"{prefix} Eti Burçak", f"{prefix} Sütaş Yoğurt"]
    async with AsyncSessionLocal() as session:
        session.add(other_market)
        products = [Product(name=name, is_global=True) for name in fixture_names]
        session.add_all(products)
        await session.commit()
        product_ids = {product.name: str(product.id) for product in products}

    async with _client() as client:
        # (Real acceptance fixture) upload + approve one image per product as Platform Admin.
        for name in fixture_names:
            uploaded = await client.post(
                f"/api/platform/catalog/products/{product_ids[name]}/images",
                headers={**platform_headers, "Content-Type": "image/png"},
                content=_png_bytes(),
                params={"primary": True},
            )
            assert uploaded.status_code == 201
            approved = await client.patch(f"/api/platform/catalog/products/{product_ids[name]}/images/{uploaded.json()['id']}/approve", headers=platform_headers)
            assert approved.status_code == 200

    async with AsyncSessionLocal() as session:
        rows = (
            await session.scalars(
                select(ProductImage).where(ProductImage.product_id.in_([UUID(pid) for pid in product_ids.values()]), ProductImage.is_primary.is_(True))
            )
        ).all()
        global_storage_keys = {str(row.product_id): row.storage_key for row in rows}
        assert all(global_storage_keys.values())

    # (8) No tenant override anywhere: every product resolves from the approved global image.
    async with AsyncSessionLocal() as session:
        campaign = Campaign(id=uuid4(), market_id=seeded["market"].id, title="No Override Campaign")
        campaign.items = [
            CampaignItem(id=uuid4(), market_id=seeded["market"].id, raw_line=name, incoming_name=name, price=Decimal("9.90"), sort_order=index)
            for index, name in enumerate(fixture_names)
        ]
        session.add(campaign)
        await session.commit()
        summary = await resolve_campaign_product_images(session, seeded["market"].id, campaign.id)
    assert summary.resolved_count == 3
    resolved_by_reason = {result.matched_product_id: result.image_storage_key for result in summary.results}
    for name in fixture_names:
        assert resolved_by_reason[UUID(product_ids[name])] == global_storage_keys[product_ids[name]]

    # (7) Add a tenant override for one product only; confirm only that product switches
    # while the remaining two continue resolving from the approved global images.
    overridden_name = fixture_names[0]
    async with AsyncSessionLocal() as session:
        session.add(
            MarketProduct(
                market_id=seeded["market"].id,
                product_id=UUID(product_ids[overridden_name]),
                image_storage_key=f"markets/{seeded['market'].id}/tenant-override.png",
                image_quality_status="good",
                is_active=True,
            )
        )
        campaign_override = Campaign(id=uuid4(), market_id=seeded["market"].id, title="Override Campaign")
        campaign_override.items = [
            CampaignItem(id=uuid4(), market_id=seeded["market"].id, raw_line=name, incoming_name=name, price=Decimal("9.90"), sort_order=index)
            for index, name in enumerate(fixture_names)
        ]
        session.add(campaign_override)
        await session.commit()
        summary_override = await resolve_campaign_product_images(session, seeded["market"].id, campaign_override.id)

    assert summary_override.resolved_count == 3
    for result in summary_override.results:
        product_id_str = str(result.matched_product_id)
        matched_name = next(name for name, pid in product_ids.items() if pid == product_id_str)
        if matched_name == overridden_name:
            assert result.image_storage_key == f"markets/{seeded['market'].id}/tenant-override.png"
        else:
            assert result.image_storage_key == global_storage_keys[product_id_str]

    # A second, unrelated market never sees the first market's tenant override.
    async with AsyncSessionLocal() as session:
        campaign_other = Campaign(id=uuid4(), market_id=other_market.id, title="Other Market Campaign")
        campaign_other.items = [CampaignItem(id=uuid4(), market_id=other_market.id, raw_line=overridden_name, incoming_name=overridden_name, price=Decimal("9.90"), sort_order=0)]
        session.add(campaign_other)
        await session.commit()
        summary_other = await resolve_campaign_product_images(session, other_market.id, campaign_other.id)
    assert summary_other.resolved_count == 1
    assert summary_other.results[0].image_storage_key == global_storage_keys[product_ids[overridden_name]]


@pytest.mark.asyncio
async def test_missing_image_produces_safe_fallback() -> None:
    if AsyncSessionLocal is None:
        pytest.skip("DATABASE_URL is not configured.")
    prefix = f"fallback-{uuid4().hex[:10]}"
    seeded = await _seed_platform_and_market(prefix)
    async with AsyncSessionLocal() as session:
        product = Product(name=f"{prefix} No Image Product", is_global=True)
        session.add(product)
        campaign = Campaign(id=uuid4(), market_id=seeded["market"].id, title="Fallback Campaign")
        campaign.items = [CampaignItem(id=uuid4(), market_id=seeded["market"].id, raw_line=product.name, incoming_name=product.name, price=Decimal("9.90"), sort_order=0)]
        session.add(campaign)
        await session.commit()
        summary = await resolve_campaign_product_images(session, seeded["market"].id, campaign.id)
    assert summary.resolved_count == 0
    assert summary.unresolved_count == 1
    assert summary.results[0].source == "fallback"
    assert summary.results[0].image_storage_key is None


@pytest.mark.asyncio
async def test_bulk_zip_import_matching_and_safety() -> None:
    if AsyncSessionLocal is None:
        pytest.skip("DATABASE_URL is not configured.")
    prefix = f"bulk-{uuid4().hex[:10]}"
    seeded = await _seed_platform_and_market(prefix)
    platform_headers = {"Authorization": f"Bearer {create_platform_access_token(str(seeded['admin'].id))}"}
    market_headers = {"Authorization": f"Bearer {create_access_token(str(seeded['user'].id))}", "X-Market-Id": str(seeded["market"].id)}

    async with AsyncSessionLocal() as session:
        exact_id_product = Product(name=f"{prefix} Exact Id Product", is_global=True)
        barcode_product = Product(name=f"{prefix} Barcode Product", is_global=True, barcode=f"{prefix}-barcode")
        name_product = Product(name=f"{prefix} Cikolatali Gofret 100g", is_global=True)
        ambiguous_a = Product(name=f"{prefix} Ambiguous Cola", is_global=True)
        ambiguous_b = Product(name=f"{prefix} Ambiguous Cola", is_global=True)
        session.add_all([exact_id_product, barcode_product, name_product, ambiguous_a, ambiguous_b])
        await session.commit()
        ids = {
            "exact": str(exact_id_product.id),
            "barcode": str(barcode_product.id),
            "name": str(name_product.id),
            "amb_a": str(ambiguous_a.id),
            "amb_b": str(ambiguous_b.id),
        }

    manifest = (
        "product_id,name,barcode,sku,image_filename\n"
        f"{ids['exact']},,,,exact.png\n"
        f",,{prefix}-barcode,,barcode.png\n"
        f",{prefix} Çikolatalı Gofret 100g,,,name.png\n"
        f",{prefix} Ambiguous Cola,,,ambiguous.png\n"
        ",Completely Unknown Product Xyz,,,unmatched.png\n"
        ",No Image Reference Row,,,missing-file.png\n"
    )
    images = {
        "exact.png": _png_bytes((1, 1, 1)),
        "barcode.png": _png_bytes((2, 2, 2)),
        "name.png": _png_bytes((3, 3, 3)),
        "ambiguous.png": _png_bytes((4, 4, 4)),
        "unmatched.png": _png_bytes((5, 5, 5)),
        # "missing-file.png" intentionally absent from the archive -> invalid row.
    }
    package = _zip_bytes(manifest, images)

    async with _client() as client:
        assert (await client.post("/api/platform/catalog/products/bulk-images/preview", headers={**market_headers, "Content-Type": "application/zip"}, content=package)).status_code == 401

        preview = await client.post("/api/platform/catalog/products/bulk-images/preview", headers={**platform_headers, "Content-Type": "application/zip"}, content=package)
        assert preview.status_code == 200
        preview_body = preview.json()
        statuses = [row["status"] for row in preview_body["rows"]]
        assert statuses == ["exact_match", "exact_match", "matched", "ambiguous", "unmatched", "invalid"]
        assert preview_body["counts"]["exact_match"] == 2
        assert preview_body["counts"]["matched"] == 1
        assert preview_body["counts"]["ambiguous"] == 1
        assert preview_body["counts"]["unmatched"] == 1
        assert preview_body["counts"]["invalid"] == 1

        ambiguous_row = next(row for row in preview_body["rows"] if row["status"] == "ambiguous")
        candidate_ids = {candidate["id"] for candidate in ambiguous_row["candidates"]}
        assert candidate_ids == {ids["amb_a"], ids["amb_b"]}

        # Import without resolving the ambiguous row: the 3 unambiguous rows (exact_match x2,
        # matched x1) are attached; ambiguous/unmatched/invalid must not be auto-attached.
        unresolved_import = await client.post("/api/platform/catalog/products/bulk-images/import", headers={**platform_headers, "Content-Type": "application/zip"}, content=package)
        assert unresolved_import.status_code == 200
        unresolved_body = unresolved_import.json()
        assert unresolved_body["uploaded"] == 3
        assert unresolved_body["needs_review"] == unresolved_body["uploaded"]
        assert unresolved_body["ambiguous"] == 1
        assert unresolved_body["unmatched"] == 1
        assert unresolved_body["invalid"] == 1
        skipped_ambiguous = next(row for row in unresolved_body["rows"] if row["row_index"] == ambiguous_row["row_index"])
        assert skipped_ambiguous.get("image_id") is None

        async with AsyncSessionLocal() as session:
            for product_id in (exact_id_product.id, barcode_product.id, name_product.id):
                images_row = (await session.scalars(select(ProductImage).where(ProductImage.product_id == product_id))).all()
                assert len(images_row) == 1
                assert images_row[0].quality_status == "needs_review"
            ambiguous_images_a = (await session.scalars(select(ProductImage).where(ProductImage.product_id == ambiguous_a.id))).all()
            ambiguous_images_b = (await session.scalars(select(ProductImage).where(ProductImage.product_id == ambiguous_b.id))).all()
        assert len(ambiguous_images_a) == 0
        assert len(ambiguous_images_b) == 0

        # Resolve the ambiguous row on its own (a focused package with just that row) so the
        # already-imported unambiguous rows above are not reprocessed a second time.
        ambiguous_only_manifest = "product_id,name,barcode,sku,image_filename\n" f",{prefix} Ambiguous Cola,,,ambiguous.png\n"
        ambiguous_only_package = _zip_bytes(ambiguous_only_manifest, {"ambiguous.png": images["ambiguous.png"]})
        ambiguous_only_row_index = 2  # single data row after the header
        resolutions = [{"row_index": ambiguous_only_row_index, "product_id": ids["amb_a"]}]
        resolved_import = await client.post(
            "/api/platform/catalog/products/bulk-images/import",
            headers={**platform_headers, "Content-Type": "application/zip"},
            params={"resolutions": json.dumps(resolutions)},
            content=ambiguous_only_package,
        )
        assert resolved_import.status_code == 200
        resolved_body = resolved_import.json()
        assert resolved_body["ambiguous"] == 1  # still classified ambiguous...
        resolved_row = resolved_body["rows"][0]
        assert resolved_row["image_id"] is not None  # ...but this time it was resolved and imported.

        async with AsyncSessionLocal() as session:
            for product_id in (exact_id_product.id, barcode_product.id, name_product.id, ambiguous_a.id):
                images_row = (await session.scalars(select(ProductImage).where(ProductImage.product_id == product_id))).all()
                assert len(images_row) == 1
                assert images_row[0].quality_status == "needs_review"
            no_images = (await session.scalars(select(ProductImage).where(ProductImage.product_id == ambiguous_b.id))).all()
            assert len(no_images) == 0


@pytest.mark.asyncio
async def test_bulk_market_auth_and_invalid_zip_rejected() -> None:
    if AsyncSessionLocal is None:
        pytest.skip("DATABASE_URL is not configured.")
    prefix = f"bulk-invalid-{uuid4().hex[:10]}"
    seeded = await _seed_platform_and_market(prefix)
    platform_headers = {"Authorization": f"Bearer {create_platform_access_token(str(seeded['admin'].id))}"}
    async with _client() as client:
        assert (await client.post("/api/platform/catalog/products/bulk-images/preview", headers=platform_headers)).status_code == 422
        assert (await client.post("/api/platform/catalog/products/bulk-images/preview", headers={**platform_headers, "Content-Type": "application/zip"}, content=b"not-a-zip")).status_code == 422
        assert (await client.post("/api/platform/catalog/products/bulk-images/preview")).status_code == 401
        assert (await client.post("/api/platform/catalog/products/images/bulk-approve", headers=platform_headers, json={"image_ids": []})).status_code == 422
