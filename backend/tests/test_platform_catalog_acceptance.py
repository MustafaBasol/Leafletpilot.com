"""Disposable PostgreSQL HTTP acceptance for the global catalog boundary.

Run with DATABASE_URL and TEST_DATABASE_URL pointed at a disposable PostgreSQL
16 instance and an isolated LOCAL_STORAGE_DIR.  The test deliberately uses FastAPI's
real HTTP surface instead of calling route functions or catalog services.
"""

from pathlib import Path
from uuid import uuid4

import pytest
import httpx
from app.core.database import AsyncSessionLocal
from app.core.config import settings
from app.core.security import create_access_token, create_platform_access_token, hash_password
from app.main import app
from app.models import Brand, Category, Market, MarketProduct, MarketUser, PlatformAdmin, Product, User


async def _seed(prefix: str) -> dict:
    async with AsyncSessionLocal() as session:
        admin = PlatformAdmin(email=f"{prefix}@example.test", full_name="Phase C Admin", password_hash=hash_password("phase-c-password"))
        markets = [Market(name=f"{prefix} Market {index}", slug=f"{prefix}-{index}") for index in ("a", "b")]
        users = [User(email=f"{prefix}-{index}@example.test", full_name=f"Market User {index}", password_hash=hash_password("market-password")) for index in ("a", "b")]
        session.add_all([admin, *markets, *users])
        await session.flush()
        session.add_all([MarketUser(market_id=market.id, user_id=user.id, role="market_admin") for market, user in zip(markets, users)])
        categories = [Category(name=f"{prefix} Category {index}", slug=f"{prefix}-category-{index}", is_global=True) for index in range(6)]
        brands = [Brand(name=f"{prefix} Brand {index}", slug=f"{prefix}-brand-{index}", is_global=True) for index in range(8)]
        session.add_all([*categories, *brands])
        await session.flush()
        products = [
            Product(name=f"{prefix} Product {index}", barcode=f"{prefix}-barcode-{index}", brand_id=brands[index % 8].id, category_id=categories[index % 6].id, is_global=True)
            for index in range(20)
        ]
        session.add_all(products)
        await session.flush()
        for index, product in enumerate(products):
            session.add(MarketProduct(market_id=markets[index % 2].id, product_id=product.id, regular_price="2.50", currency="EUR"))
        await session.commit()
        return {"admin": admin, "markets": markets, "users": users, "categories": categories, "brands": brands, "products": products}


@pytest.mark.asyncio
async def test_when_test_database_url_is_configured_global_catalog_http_acceptance() -> None:
    if AsyncSessionLocal is None:
        pytest.skip("DATABASE_URL is not configured.")

    prefix = f"phasec-{uuid4().hex[:10]}"
    seeded = await _seed(prefix)
    admin_token = create_platform_access_token(str(seeded["admin"].id))
    market_token = create_access_token(str(seeded["users"][0].id))
    platform_headers = {"Authorization": f"Bearer {admin_token}"}
    market_headers = {"Authorization": f"Bearer {market_token}"}
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")

    category = seeded["categories"][0]
    brand = seeded["brands"][0]
    product = seeded["products"][0]
    created_image_ids: list[str] = []

    assert (await client.get("/api/platform/catalog/categories")).status_code == 401
    assert (await client.get("/api/platform/catalog/categories", headers=market_headers)).status_code == 401
    assert (await client.get("/api/platform/catalog/products", headers=market_headers)).status_code == 401

    created_category = await client.post("/api/platform/catalog/categories", headers=platform_headers, json={"name": f"{prefix} Created Category"})
    assert created_category.status_code == 201
    created_category_id = created_category.json()["id"]
    assert (await client.patch(f"/api/platform/catalog/categories/{created_category_id}", headers=platform_headers, json={"name": f"{prefix} Edited Category"})).status_code == 200
    assert (await client.delete(f"/api/platform/catalog/categories/{created_category_id}", headers=platform_headers)).status_code == 200
    assert (await client.patch(f"/api/platform/catalog/categories/{created_category_id}", headers=platform_headers, json={"is_active": True})).status_code == 200
    assert (await client.post("/api/platform/catalog/categories", headers=platform_headers, json={"name": f"{prefix} Edited Category"})).status_code == 409
    referenced_category = await client.delete(f"/api/platform/catalog/categories/{category.id}", headers=platform_headers)
    assert referenced_category.status_code == 200
    assert referenced_category.json()["is_active"] is False

    created_brand = await client.post("/api/platform/catalog/brands", headers=platform_headers, json={"name": f"{prefix} Created Brand"})
    assert created_brand.status_code == 201
    created_brand_id = created_brand.json()["id"]
    assert (await client.patch(f"/api/platform/catalog/brands/{created_brand_id}", headers=platform_headers, json={"name": f"{prefix} Edited Brand"})).status_code == 200
    assert (await client.delete(f"/api/platform/catalog/brands/{created_brand_id}", headers=platform_headers)).status_code == 200
    assert (await client.patch(f"/api/platform/catalog/brands/{created_brand_id}", headers=platform_headers, json={"is_active": True})).status_code == 200
    assert (await client.post("/api/platform/catalog/brands", headers=platform_headers, json={"name": f"{prefix} Edited Brand"})).status_code == 409

    duplicate_name = await client.post("/api/platform/catalog/products", headers=platform_headers, json={"name": product.name, "barcode": f"{prefix}-other"})
    assert duplicate_name.status_code == 409
    duplicate_barcode = await client.post("/api/platform/catalog/products", headers=platform_headers, json={"name": f"{prefix} Other Product", "barcode": product.barcode})
    assert duplicate_barcode.status_code == 409

    created_product = await client.post(
        "/api/platform/catalog/products",
        headers=platform_headers,
        json={"name": f"{prefix} Created Product", "barcode": f"{prefix}-created", "brand_id": str(brand.id), "category_id": str(category.id), "aliases": [{"alias": f"{prefix} Alias"}]},
    )
    assert created_product.status_code == 201
    created_product_id = created_product.json()["id"]
    edited = await client.patch(
        f"/api/platform/catalog/products/{created_product_id}",
        headers=platform_headers,
        json={"name": f"{prefix} Edited Product", "package_size": "500", "package_type": "g", "aliases": [{"alias": f"{prefix} Updated Alias"}]},
    )
    assert edited.status_code == 200
    assert edited.json()["aliases"][0]["alias"] == f"{prefix} Updated Alias"
    assert (await client.get("/api/platform/catalog/products", headers=platform_headers, params={"barcode": product.barcode})).json()["total"] == 1
    assert (await client.get("/api/platform/catalog/products", headers=platform_headers, params={"brand_id": str(brand.id)})).json()["total"] >= 1
    assert (await client.get("/api/platform/catalog/products", headers=platform_headers, params={"category_id": str(category.id)})).json()["total"] >= 1
    usage = (await client.get("/api/platform/catalog/products", headers=platform_headers, params={"search": product.name})).json()["items"][0]["usage_count"]
    assert usage == 1
    category_items = (await client.get("/api/platform/catalog/categories", headers=platform_headers)).json()["items"]
    assert any(item["id"] == str(category.id) and item["usage_count"] >= 1 for item in category_items)
    assert (await client.delete(f"/api/platform/catalog/products/{created_product_id}", headers=platform_headers)).status_code == 200
    assert (await client.patch(f"/api/platform/catalog/products/{created_product_id}", headers=platform_headers, json={"is_active": True})).status_code == 200

    product_id = str(product.id)
    storage_root = Path(settings.local_storage_path)
    files_before_upload = {path for path in storage_root.rglob("*") if path.is_file()} if storage_root.exists() else set()
    valid_images = [("image/png", b"\x89PNG\r\n\x1a\nphase-c"), ("image/jpeg", b"\xff\xd8\xffphase-c"), ("image/webp", b"RIFFxxxxWEBPphase-c")]
    for mime, body in valid_images:
        response = await client.post(f"/api/platform/catalog/products/{product_id}/images", headers={**platform_headers, "Content-Type": mime}, content=body, params={"primary": mime == "image/png"})
        assert response.status_code == 201
        payload = response.json()
        created_image_ids.append(payload["id"])
        assert "storage_key" not in payload
        assert payload["is_primary"] is (mime == "image/png")
    files_after_upload = {path for path in storage_root.rglob("*") if path.is_file()}
    assert len(files_after_upload - files_before_upload) == 3

    before_failed = (await client.get(f"/api/platform/catalog/products", headers=platform_headers, params={"search": product.name})).json()["items"][0]["images"]
    assert (await client.post(f"/api/platform/catalog/products/{product_id}/images", headers={**platform_headers, "Content-Type": "image/gif"}, content=b"GIF89a")).status_code == 415
    assert (await client.post(f"/api/platform/catalog/products/{product_id}/images", headers={**platform_headers, "Content-Type": "image/png"}, content=b"not-png")).status_code == 422
    assert (await client.post(f"/api/platform/catalog/products/{product_id}/images", headers={**platform_headers, "Content-Type": "image/png"}, content=b"\x89PNG\r\n\x1a\n" + b"x" * (10 * 1024 * 1024 + 1))).status_code == 413
    after_failed = (await client.get(f"/api/platform/catalog/products", headers=platform_headers, params={"search": product.name})).json()["items"][0]["images"]
    assert len(after_failed) == len(before_failed)
    files_after_failed = {path for path in storage_root.rglob("*") if path.is_file()}
    assert files_after_failed == files_after_upload

    primary_id = created_image_ids[1]
    primary = await client.patch(f"/api/platform/catalog/products/{product_id}/images/{primary_id}/primary", headers=platform_headers)
    assert primary.status_code == 200 and primary.json()["is_primary"] is True
    fresh = (await client.get("/api/platform/catalog/products", headers=platform_headers, params={"search": product.name})).json()["items"][0]
    assert next(image for image in fresh["images"] if str(image["id"]) == primary_id)["is_primary"] is True
    assert all("storage_key" not in image and "url" not in image for image in fresh["images"])
    assert (await client.get(f"/api/platform/catalog/products/{product_id}/images/{created_image_ids[2]}/content", headers=platform_headers)).status_code == 200
    assert (await client.delete(f"/api/platform/catalog/products/{product_id}/images/{created_image_ids[2]}", headers=platform_headers)).status_code == 204
    files_after_remove = {path for path in storage_root.rglob("*") if path.is_file()}
    assert len(files_after_upload - files_after_remove) == 1
    assert (await client.get(f"/api/platform/catalog/products/{product_id}/images/{created_image_ids[2]}/content", headers=platform_headers)).status_code == 404
    assert (await client.delete(f"/api/platform/catalog/products/{product_id}/images/{primary_id}", headers=platform_headers)).status_code == 204
    remaining = (await client.get("/api/platform/catalog/products", headers=platform_headers, params={"search": product.name})).json()["items"][0]["images"]
    assert sum(image["is_primary"] for image in remaining) <= 1

    assert (await client.patch(f"/api/platform/catalog/products/{product_id}", headers=market_headers, json={"name": f"{prefix} Market Mutation"})).status_code == 401
    assert (await client.post("/api/platform/catalog/brands", headers=market_headers, json={"name": f"{prefix} Market Brand"})).status_code == 401
    await client.aclose()
