from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.api.deps import get_catalog_session, get_current_user
from app.api.routes.catalog import router as catalog_router
from app.core.config import settings
from app.core.database import Base
from app.main import app
from app.models import Market, MarketUser, User
from app.schemas.brand import BrandCreate
from app.schemas.category import CategoryCreate
from app.schemas.product import ProductCreate
from app.services.catalog import normalize_alias, slugify

client = TestClient(app)


def test_api_router_includes_catalog_routes() -> None:
    paths = {route.path for route in catalog_router.routes}

    assert "/catalog/brands" in paths
    assert "/catalog/categories" in paths
    assert "/catalog/products" in paths


def test_openapi_schema_contains_catalog_routes() -> None:
    schema = client.get("/openapi.json").json()

    assert "/api/catalog/brands" in schema["paths"]
    assert "/api/catalog/categories" in schema["paths"]
    assert "/api/catalog/products" in schema["paths"]


def test_catalog_schemas_validate_sample_payloads() -> None:
    brand = BrandCreate(name="Acme Foods", is_global=True)
    category = CategoryCreate(name="Dairy", color="#ffffff", sort_order=10, is_global=True)
    product = ProductCreate(
        name="Whole Milk 1L",
        barcode="123456789",
        package_size="1L",
        package_type="carton",
        is_global=True,
        aliases=["Milk 1 L", {"alias": "Whole-Milk", "source": "manual"}],
        images=[{"url": "https://example.com/milk.png", "is_primary": True}],
    )

    assert brand.slug is None
    assert category.name == "Dairy"
    assert product.aliases[0] == "Milk 1 L"


def test_slug_generation_works() -> None:
    assert slugify("  Whole Milk 1L!  ") == "whole-milk-1l"


def test_alias_normalization_works() -> None:
    assert normalize_alias("  SÜT, 1L!!  ") == "süt 1l"


@pytest.mark.asyncio
async def test_global_brand_api_crud_runs_when_test_database_url_is_configured() -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed catalog CRUD tests skipped.")

    engine = create_async_engine(settings.test_database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def override_session():
        async with session_factory() as session:
            yield session

    market_id = uuid4()
    user_id = uuid4()

    async def override_user():
        return User(id=user_id, email=f"catalog-{user_id}@example.com", is_active=True)

    app.dependency_overrides[get_catalog_session] = override_session
    app.dependency_overrides[get_current_user] = override_user
    try:
        async with session_factory() as session:
            market = Market(id=market_id, name=f"Catalog Test Market {market_id}", slug=f"c-{market_id}")
            user = User(id=user_id, email=f"catalog-{user_id}@example.com", is_active=True)
            membership = MarketUser(market_id=market_id, user_id=user_id, role="market_admin", is_active=True)
            session.add_all([market, user, membership])
            await session.commit()

        unique_name = f"Catalog Test Brand {uuid4()}"
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as async_client:
            headers = {"X-Market-Id": str(market_id)}
            create_response = await async_client.post(
                "/api/catalog/brands",
                headers=headers,
                json={"name": unique_name, "is_global": True},
            )
            assert create_response.status_code == 201
            brand = create_response.json()
            assert brand["name"] == unique_name
            assert brand["is_global"] is True

            list_response = await async_client.get(
                "/api/catalog/brands",
                headers=headers,
                params={"search": unique_name},
            )
            assert list_response.status_code == 200
            assert list_response.json()["total"] >= 1

            delete_response = await async_client.delete(f"/api/catalog/brands/{brand['id']}", headers=headers)
            assert delete_response.status_code == 200
            assert delete_response.json()["is_active"] is False
    finally:
        app.dependency_overrides.pop(get_catalog_session, None)
        app.dependency_overrides.pop(get_current_user, None)
        await engine.dispose()
