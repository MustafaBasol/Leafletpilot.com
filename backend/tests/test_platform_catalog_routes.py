"""Focused contract and security coverage for the platform global catalog routes.

The DB-backed matrix is intentionally opt-in through TEST_DATABASE_URL; the route
surface and unauthenticated boundary are always exercised in every environment.
"""

from fastapi.testclient import TestClient
import pytest

from app.main import app

client = TestClient(app)


def test_platform_catalog_route_matrix_is_registered() -> None:
    paths = set(client.get("/openapi.json").json()["paths"])
    expected = {
        "/api/platform/catalog/categories",
        "/api/platform/catalog/categories/{category_id}",
        "/api/platform/catalog/brands",
        "/api/platform/catalog/brands/{brand_id}",
        "/api/platform/catalog/products",
        "/api/platform/catalog/products/{product_id}",
        "/api/platform/catalog/products/{product_id}/images",
        "/api/platform/catalog/products/{product_id}/images/{image_id}",
        "/api/platform/catalog/products/{product_id}/images/{image_id}/primary",
    }
    assert expected <= paths


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/platform/catalog/categories"),
        ("post", "/api/platform/catalog/categories"),
        ("patch", "/api/platform/catalog/categories/00000000-0000-0000-0000-000000000001"),
        ("delete", "/api/platform/catalog/categories/00000000-0000-0000-0000-000000000001"),
        ("get", "/api/platform/catalog/brands"),
        ("post", "/api/platform/catalog/brands"),
        ("patch", "/api/platform/catalog/brands/00000000-0000-0000-0000-000000000001"),
        ("delete", "/api/platform/catalog/brands/00000000-0000-0000-0000-000000000001"),
        ("get", "/api/platform/catalog/products"),
        ("post", "/api/platform/catalog/products"),
        ("patch", "/api/platform/catalog/products/00000000-0000-0000-0000-000000000001"),
        ("delete", "/api/platform/catalog/products/00000000-0000-0000-0000-000000000001"),
        ("post", "/api/platform/catalog/products/00000000-0000-0000-0000-000000000001/images"),
        ("patch", "/api/platform/catalog/products/00000000-0000-0000-0000-000000000001/images/00000000-0000-0000-0000-000000000002/primary"),
        ("delete", "/api/platform/catalog/products/00000000-0000-0000-0000-000000000001/images/00000000-0000-0000-0000-000000000002"),
    ],
)
def test_platform_catalog_requires_platform_auth(method: str, path: str) -> None:
    kwargs = {"json": {"name": "x"}} if method in {"post", "patch"} else {}
    response = client.request(method.upper(), path, **kwargs)
    assert response.status_code == 401


def test_platform_catalog_does_not_accept_market_auth_as_platform_auth() -> None:
    response = client.get("/api/platform/catalog/products", headers={"Authorization": "Bearer not-a-platform-token"})
    assert response.status_code == 401


def test_platform_catalog_image_contract_rejects_missing_auth_before_body_validation() -> None:
    response = client.post(
        "/api/platform/catalog/products/00000000-0000-0000-0000-000000000001/images",
        headers={"Content-Type": "image/png"},
        content=b"not-an-image",
    )
    assert response.status_code == 401
