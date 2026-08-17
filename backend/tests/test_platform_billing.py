"""Platform Admin billing plan-mapping health endpoint.

Regression coverage for the StripeObject `.get()` incompatibility that broke
GET /api/platform/billing/plans in production: the installed Stripe SDK's
StripeObject supports attribute/item access but not `.get()`. `_FakeStripePrice`
below (mirroring `_FakeStripeObject` in test_billing.py) has no `.get()` at
all, so a lingering `.get()` call in platform_billing.py fails here exactly
as it would against a real Stripe response.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.api.routes.platform import list_platform_markets
from app.api.routes.platform_billing import billing_health, plan_mapping_health
from app.core.database import Base
from app.core.config import settings
from app.models import Market, PlatformAdmin
from app.models.billing import MarketSubscription, StripeWebhookEvent
from app.services.billing import service as billing_service


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


def test_billing_health_route_registered() -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    paths = set(client.get("/openapi.json").json()["paths"])
    assert "/api/platform/billing/health" in paths


@pytest.mark.asyncio
async def test_billing_health_route_requires_platform_admin_auth() -> None:
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/api/platform/billing/health")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /platform/billing/health — DB-backed aggregation + Platform Admin
# billing-operations dashboard (PART F/G/I).
# ---------------------------------------------------------------------------


async def _setup_engine():
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed billing tests skipped.")
    engine = create_async_engine(settings.test_database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return engine, session_factory


async def _create_market(session, **overrides) -> Market:
    market_id = overrides.pop("id", uuid4())
    market = Market(
        id=market_id,
        name=overrides.pop("name", f"Market {market_id}"),
        slug=overrides.pop("slug", f"market-{market_id}"),
        subscription_plan=overrides.pop("subscription_plan", "unassigned"),
        **overrides,
    )
    session.add(market)
    await session.flush()
    return market


def _admin_row() -> PlatformAdmin:
    return PlatformAdmin(email="admin-health@example.com", full_name="Admin", password_hash="hashed")


@pytest.mark.asyncio
async def test_billing_health_aggregates_counts_and_sanitizes_errors_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_abcdef123456")
    monkeypatch.setattr(billing_service, "_PORTAL_CONFIGURATION_CACHE", None)
    engine, session_factory = await _setup_engine()
    try:
        async with session_factory() as session:
            healthy_market = await _create_market(session, subscription_plan="pro")
            attention_market = await _create_market(session, subscription_plan="pro")
            unassigned_market = await _create_market(session, subscription_plan="unassigned")
            await session.commit()

            session.add(
                MarketSubscription(
                    market_id=healthy_market.id,
                    plan_code="pro",
                    status="active",
                    stripe_customer_id="cus_health_1",
                    stripe_subscription_id="sub_health_1",
                )
            )
            session.add(
                MarketSubscription(
                    market_id=attention_market.id,
                    plan_code="pro",
                    status="active",
                    stripe_customer_id="cus_health_2",
                    stripe_subscription_id="sub_health_2",
                    sync_error="Unmapped Stripe price id=price_x sk_test_shouldnotleak123456",
                )
            )
            session.add(
                StripeWebhookEvent(
                    stripe_event_id="evt_health_failed_1",
                    event_type="invoice.paid",
                    livemode=False,
                    status="failed",
                    error="Invoice event has no associated subscription. whsec_shouldnotleak789012",
                )
            )
            session.add(
                StripeWebhookEvent(
                    stripe_event_id="evt_health_processed_1",
                    event_type="customer.subscription.updated",
                    livemode=False,
                    status="processed",
                    processed_at=datetime.now(UTC),
                )
            )
            await session.commit()

            result = await billing_health(_admin_row(), session)

            assert result["stripe_enabled"] is True
            assert result["environment"] == "sandbox"
            assert result["managed_payments_disabled"] is True
            assert result["portal_status"] == "not_checked"

            assert result["webhook_counts"]["by_status"]["failed"] == 1
            assert result["webhook_counts"]["by_status"]["processed"] == 1
            assert result["webhook_counts"]["failed_invoice_count"] == 1

            assert result["subscription_counts"]["by_status"]["active"] == 2

            assert result["plan_distribution"]["pro"] == 2
            assert result["plan_distribution"]["unassigned"] == 1
            assert unassigned_market.id  # sanity: created, contributes to the "unassigned" bucket above

            attention_ids = {item["market_id"] for item in result["attention_markets"]}
            assert str(attention_market.id) in attention_ids
            assert str(healthy_market.id) not in attention_ids
            attention_entry = next(item for item in result["attention_markets"] if item["market_id"] == str(attention_market.id))
            # The redaction keeps the harmless "sk_test_" prefix (for
            # identifying which kind of secret leaked) but must strip the
            # actual key material that followed it.
            assert "shouldnotleak123456" not in attention_entry["issue"]
            assert "[redacted]" in attention_entry["issue"]

            failure_by_market = {item["market_id"]: item for item in result["recent_failures"] if item["market_id"]}
            assert failure_by_market == {}  # this test's own failed event carries no market_id
            assert any(item["event_type"] == "invoice.paid" for item in result["recent_failures"])
            invoice_failure = next(item for item in result["recent_failures"] if item["event_type"] == "invoice.paid")
            assert "shouldnotleak789012" not in invoice_failure["error"]
            assert "[redacted]" in invoice_failure["error"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_billing_health_excludes_market_with_no_sync_issues_from_attention_list_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "stripe_secret_key", "not-a-real-stripe-key")
    monkeypatch.setattr(billing_service, "_PORTAL_CONFIGURATION_CACHE", None)
    engine, session_factory = await _setup_engine()
    try:
        async with session_factory() as session:
            market = await _create_market(session, subscription_plan="starter")
            await session.commit()
            session.add(
                MarketSubscription(
                    market_id=market.id,
                    plan_code="starter",
                    status="active",
                    stripe_customer_id="cus_health_3",
                    stripe_subscription_id="sub_health_3",
                )
            )
            await session.commit()

            result = await billing_health(_admin_row(), session)

            attention_ids = {item["market_id"] for item in result["attention_markets"]}
            assert str(market.id) not in attention_ids
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_billing_health_reports_not_configured_environment_when_stripe_disabled_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "stripe_enabled", False)
    engine, session_factory = await _setup_engine()
    try:
        async with session_factory() as session:
            result = await billing_health(_admin_row(), session)
            assert result["stripe_enabled"] is False
            assert result["environment"] == "not_configured"
            assert result["portal_status"] == "unavailable"
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# PR #69 final closure round — PART C: GET /platform/markets exposes a
# canonical `plan`/`Plan` display label and supports `plan=` filtering,
# entirely from local DB state (Market.subscription_plan / MarketSubscription)
# — no per-market Stripe call, ever (see PART C3 in the task brief).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_platform_market_list_exposes_canonical_plan_and_public_display_label_when_test_database_url_is_configured() -> None:
    engine, session_factory = await _setup_engine()
    try:
        async with session_factory() as session:
            starter_market = await _create_market(session, subscription_plan="starter")
            growth_market = await _create_market(session, subscription_plan="growth")
            unassigned_market = await _create_market(session, subscription_plan="unassigned")
            await session.commit()

            response = await list_platform_markets(plan=None, limit=25, offset=0, session=session)
            by_id = {item.id: item for item in response.items}

            assert by_id[starter_market.id].subscription_plan == "starter"
            assert by_id[starter_market.id].subscription_plan_display == "Başlangıç"
            # The raw code preserves the legacy "growth" alias (see
            # entitlements.resolve_plan_code) but the *display* name is
            # always the canonical public "Plus" — never "growth"/"standard"
            # raw. The UI (PlatformMarketList.jsx) renders subscription_plan_display,
            # never subscription_plan, for exactly this reason.
            assert by_id[growth_market.id].subscription_plan == "growth"
            assert by_id[growth_market.id].subscription_plan_display == "Plus"
            assert by_id[unassigned_market.id].subscription_plan == "unassigned"
            assert by_id[unassigned_market.id].subscription_plan_display == "Atanmamış"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_platform_market_list_plan_filter_matches_each_canonical_code_when_test_database_url_is_configured() -> None:
    engine, session_factory = await _setup_engine()
    try:
        async with session_factory() as session:
            starter_market = await _create_market(session, subscription_plan="starter")
            pro_market = await _create_market(session, subscription_plan="pro")
            unassigned_market = await _create_market(session, subscription_plan="unassigned")
            await session.commit()

            # Assertions tolerate other markets left over from earlier test
            # runs against the shared TEST_DATABASE_URL (no per-test
            # truncation) — every item in a filtered page must itself carry
            # the requested plan, and this test's own market must be among them.
            starter_response = await list_platform_markets(plan="starter", limit=25, offset=0, session=session)
            assert all(item.subscription_plan == "starter" for item in starter_response.items)
            assert starter_market.id in {item.id for item in starter_response.items}

            pro_response = await list_platform_markets(plan="pro", limit=25, offset=0, session=session)
            assert all(item.subscription_plan == "pro" for item in pro_response.items)
            assert pro_market.id in {item.id for item in pro_response.items}

            unassigned_response = await list_platform_markets(plan="unassigned", limit=25, offset=0, session=session)
            assert all(item.subscription_plan == "unassigned" for item in unassigned_response.items)
            assert unassigned_market.id in {item.id for item in unassigned_response.items}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_platform_market_list_plan_filter_standard_includes_legacy_growth_when_test_database_url_is_configured() -> None:
    engine, session_factory = await _setup_engine()
    try:
        async with session_factory() as session:
            standard_market = await _create_market(session, subscription_plan="standard")
            growth_market = await _create_market(session, subscription_plan="growth")
            starter_market = await _create_market(session, subscription_plan="starter")
            await session.commit()

            response = await list_platform_markets(plan="standard", limit=25, offset=0, session=session)
            returned_ids = {item.id for item in response.items}

            # Raw subscription_plan preserves the legacy "growth" alias, but
            # every returned row's *display* name (what the admin UI shows)
            # is the canonical "Plus" regardless.
            assert all(item.subscription_plan_display == "Plus" for item in response.items)
            assert {standard_market.id, growth_market.id} <= returned_ids
            assert starter_market.id not in returned_ids
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_platform_market_list_plan_filter_rejects_unknown_value_when_test_database_url_is_configured() -> None:
    from fastapi import HTTPException

    engine, session_factory = await _setup_engine()
    try:
        async with session_factory() as session:
            with pytest.raises(HTTPException) as exc_info:
                await list_platform_markets(plan="not-a-real-plan", session=session)
            assert exc_info.value.status_code == 422
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_platform_market_list_plan_filter_composes_with_lifecycle_status_when_test_database_url_is_configured() -> None:
    engine, session_factory = await _setup_engine()
    try:
        async with session_factory() as session:
            active_pro = await _create_market(session, subscription_plan="pro", lifecycle_status="active")
            trial_pro = await _create_market(session, subscription_plan="pro", lifecycle_status="trial")
            active_starter = await _create_market(session, subscription_plan="starter", lifecycle_status="active")
            await session.commit()

            response = await list_platform_markets(plan="pro", lifecycle_status="active", limit=25, offset=0, session=session)
            returned_ids = {item.id for item in response.items}

            assert all(item.subscription_plan == "pro" and item.lifecycle_status == "active" for item in response.items)
            assert active_pro.id in returned_ids
            assert trial_pro.id not in returned_ids
            assert active_starter.id not in returned_ids
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_platform_market_list_plan_filter_composes_with_billing_sync_status_when_test_database_url_is_configured() -> None:
    engine, session_factory = await _setup_engine()
    try:
        async with session_factory() as session:
            healthy_pro = await _create_market(session, subscription_plan="pro")
            erroring_pro = await _create_market(session, subscription_plan="pro")
            await session.commit()
            session.add(
                MarketSubscription(
                    market_id=healthy_pro.id,
                    plan_code="pro",
                    status="active",
                    stripe_customer_id="cus_plan_filter_ok",
                    stripe_subscription_id="sub_plan_filter_ok",
                )
            )
            session.add(
                MarketSubscription(
                    market_id=erroring_pro.id,
                    plan_code="pro",
                    status="active",
                    stripe_customer_id="cus_plan_filter_err",
                    stripe_subscription_id="sub_plan_filter_err",
                    sync_error="Unmapped Stripe price id=price_x",
                )
            )
            await session.commit()

            response = await list_platform_markets(plan="pro", billing_sync_status="error", limit=25, offset=0, session=session)
            returned_ids = {item.id for item in response.items}

            assert all(item.subscription_plan == "pro" and item.billing.billing_sync_status == "error" for item in response.items)
            assert erroring_pro.id in returned_ids
            assert healthy_pro.id not in returned_ids
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_platform_market_list_and_plan_filter_never_call_stripe_when_test_database_url_is_configured(monkeypatch) -> None:
    import stripe

    def _unexpected(*args, **kwargs):
        raise AssertionError("the platform market list must never call the Stripe API per row")

    monkeypatch.setattr(stripe.Subscription, "retrieve_async", _unexpected)
    monkeypatch.setattr(stripe.Price, "list_async", _unexpected)
    monkeypatch.setattr(stripe.SubscriptionSchedule, "retrieve_async", _unexpected)

    engine, session_factory = await _setup_engine()
    try:
        async with session_factory() as session:
            growth_market = await _create_market(session, subscription_plan="growth")
            standard_market = await _create_market(session, subscription_plan="standard")
            await session.commit()

            # Getting this far without the monkeypatched Stripe stubs raising
            # is itself the assertion — a per-row Stripe call would have
            # thrown AssertionError above. Also sanity-check the filter still
            # returned exactly this market pair's normalized plan.
            response = await list_platform_markets(plan="standard", limit=25, offset=0, session=session)
            returned_ids = {item.id for item in response.items}
            assert {growth_market.id, standard_market.id} <= returned_ids
            assert all(item.subscription_plan_display == "Plus" for item in response.items)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_platform_markets_route_requires_platform_admin_auth_with_plan_param() -> None:
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/api/platform/markets", params={"plan": "starter"})
    assert response.status_code == 401
