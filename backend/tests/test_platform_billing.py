"""Platform Admin billing plan-mapping health endpoint.

Regression coverage for the StripeObject `.get()` incompatibility that broke
GET /api/platform/billing/plans in production: the installed Stripe SDK's
StripeObject supports attribute/item access but not `.get()`. `_FakeStripePrice`
below (mirroring `_FakeStripeObject` in test_billing.py) has no `.get()` at
all, so a lingering `.get()` call in platform_billing.py fails here exactly
as it would against a real Stripe response.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.api.routes.platform_billing import plan_mapping_health
from app.core.config import settings
from app.models import PlatformAdmin


class _FakeStripePrice:
    def __init__(self, data: dict) -> None:
        object.__setattr__(self, "_data", data)

    def __getitem__(self, key):
        return self._data[key]

    def __getattr__(self, key):
        try:
            return self._data[key]
        except KeyError as exc:
            raise AttributeError(key) from exc


def _admin() -> PlatformAdmin:
    return PlatformAdmin(email="admin@example.com", full_name="Admin", password_hash="hashed")


def _list_result(prices: list[dict]):
    return SimpleNamespace(data=[_FakeStripePrice(p) for p in prices])


@pytest.fixture(autouse=True)
def _enable_stripe(monkeypatch):
    monkeypatch.setattr(settings, "stripe_enabled", True)
    monkeypatch.setattr(settings, "stripe_secret_key", "not-a-real-stripe-key")
    monkeypatch.setattr(settings, "stripe_price_lookup_key_starter", "leafletpilot_starter_monthly")
    monkeypatch.setattr(settings, "stripe_price_lookup_key_standard", "leafletpilot_standard_monthly")
    monkeypatch.setattr(settings, "stripe_price_lookup_key_pro", "leafletpilot_pro_monthly")


@pytest.mark.asyncio
async def test_plan_mapping_health_succeeds_with_stripeobject_lacking_get(monkeypatch):
    async def fake_list_async(*, lookup_keys, limit=10):
        by_key = {
            "leafletpilot_starter_monthly": [
                {"id": "price_starter", "active": True, "currency": "eur", "unit_amount": 5900}
            ],
            "leafletpilot_standard_monthly": [
                {"id": "price_standard", "active": True, "currency": "eur", "unit_amount": 11900}
            ],
            "leafletpilot_pro_monthly": [
                {"id": "price_pro", "active": True, "currency": "eur", "unit_amount": 19900}
            ],
        }
        return _list_result(by_key[lookup_keys[0]])

    monkeypatch.setattr("stripe.Price.list_async", fake_list_async)

    result = await plan_mapping_health(_admin())

    assert result["stripe_enabled"] is True
    plans_by_code = {p["plan_code"]: p for p in result["plans"]}
    assert plans_by_code["starter"]["health"] == "ok"
    assert plans_by_code["starter"]["stripe_price_id"] == "price_starter"
    assert plans_by_code["starter"]["unit_amount"] == 5900
    assert plans_by_code["starter"]["currency"] == "eur"
    assert plans_by_code["pro"]["health"] == "ok"
    assert plans_by_code["pro"]["stripe_price_id"] == "price_pro"
    assert plans_by_code["pro"]["unit_amount"] == 19900


@pytest.mark.asyncio
async def test_plan_mapping_health_detects_inactive_price(monkeypatch):
    async def fake_list_async(*, lookup_keys, limit=10):
        return _list_result([{"id": "price_x", "active": False, "currency": "eur", "unit_amount": 5900}])

    monkeypatch.setattr("stripe.Price.list_async", fake_list_async)

    result = await plan_mapping_health(_admin())

    plans_by_code = {p["plan_code"]: p for p in result["plans"]}
    assert plans_by_code["starter"]["health"] == "inactive"
    assert plans_by_code["starter"]["stripe_price_id"] is None


@pytest.mark.asyncio
async def test_plan_mapping_health_detects_currency_mismatch(monkeypatch):
    async def fake_list_async(*, lookup_keys, limit=10):
        return _list_result([{"id": "price_x", "active": True, "currency": "usd", "unit_amount": 5900}])

    monkeypatch.setattr("stripe.Price.list_async", fake_list_async)

    result = await plan_mapping_health(_admin())

    plans_by_code = {p["plan_code"]: p for p in result["plans"]}
    assert plans_by_code["starter"]["health"] == "currency_mismatch"


@pytest.mark.asyncio
async def test_plan_mapping_health_detects_amount_mismatch(monkeypatch):
    async def fake_list_async(*, lookup_keys, limit=10):
        return _list_result([{"id": "price_x", "active": True, "currency": "eur", "unit_amount": 100}])

    monkeypatch.setattr("stripe.Price.list_async", fake_list_async)

    result = await plan_mapping_health(_admin())

    plans_by_code = {p["plan_code"]: p for p in result["plans"]}
    assert plans_by_code["starter"]["health"] == "amount_mismatch"


@pytest.mark.asyncio
async def test_plan_mapping_health_missing_price_does_not_crash(monkeypatch):
    async def fake_list_async(*, lookup_keys, limit=10):
        return _list_result([])

    monkeypatch.setattr("stripe.Price.list_async", fake_list_async)

    result = await plan_mapping_health(_admin())

    plans_by_code = {p["plan_code"]: p for p in result["plans"]}
    assert plans_by_code["starter"]["health"] == "missing"
    assert plans_by_code["starter"]["stripe_price_id"] is None
    assert plans_by_code["starter"]["unit_amount"] is None
    assert plans_by_code["starter"]["currency"] is None


@pytest.mark.asyncio
async def test_plan_mapping_health_missing_optional_price_fields_does_not_crash(monkeypatch):
    """A Stripe Price missing `active`/`unit_amount` (optional in the API
    response for some price types) must not crash `_field`'s attribute lookup."""

    async def fake_list_async(*, lookup_keys, limit=10):
        return _list_result([{"id": "price_x", "active": True, "currency": "eur"}])

    monkeypatch.setattr("stripe.Price.list_async", fake_list_async)

    result = await plan_mapping_health(_admin())

    plans_by_code = {p["plan_code"]: p for p in result["plans"]}
    assert plans_by_code["starter"]["health"] == "amount_mismatch"
    assert plans_by_code["starter"]["unit_amount"] is None


def test_plan_mapping_route_registered() -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    paths = set(client.get("/openapi.json").json()["paths"])
    assert "/api/platform/billing/plans" in paths
