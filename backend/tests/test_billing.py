import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
import stripe
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.api.deps import get_catalog_session
from app.core.config import settings
from app.core.database import Base
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models import Market, MarketUser, User
from app.models.billing import MarketSubscription, StripeWebhookEvent
from app.services.billing import service as billing_service
from app.services.billing.errors import BillingError, PermanentSyncError
from app.services.billing.plans import plan_code_for_lookup_key, resolve_stripe_lookup_key
from app.services.billing.service import apply_invoice_event, sync_subscription_from_stripe_object
from app.services.billing.webhook import process_event


# ---------------------------------------------------------------------------
# Plan mapping — no DB required.
# ---------------------------------------------------------------------------


def test_resolve_stripe_lookup_key_covers_all_sellable_plans():
    assert resolve_stripe_lookup_key("starter") == settings.stripe_price_lookup_key_starter
    assert resolve_stripe_lookup_key("standard") == settings.stripe_price_lookup_key_standard
    assert resolve_stripe_lookup_key("pro") == settings.stripe_price_lookup_key_pro


def test_resolve_stripe_lookup_key_rejects_unassigned():
    with pytest.raises(ValueError):
        resolve_stripe_lookup_key("unassigned")


def test_plan_code_for_lookup_key_roundtrip_and_unknown():
    assert plan_code_for_lookup_key(settings.stripe_price_lookup_key_pro) == "pro"
    assert plan_code_for_lookup_key("not-a-real-lookup-key") is None
    assert plan_code_for_lookup_key(None) is None


# ---------------------------------------------------------------------------
# Shared DB helpers (mirrors the pattern in test_auth_api.py).
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


def _dt(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, tz=UTC)


_LOOKUP_KEYS = {
    "starter": settings.stripe_price_lookup_key_starter,
    "standard": settings.stripe_price_lookup_key_standard,
    "pro": settings.stripe_price_lookup_key_pro,
}
_UNIT_AMOUNTS = {"starter": 5900, "standard": 11900, "pro": 19900}


def _price(plan_code: str, price_id: str | None = None) -> dict:
    return {
        "id": price_id or f"price_{plan_code}",
        "lookup_key": _LOOKUP_KEYS[plan_code],
        "currency": "eur",
        "unit_amount": _UNIT_AMOUNTS[plan_code],
        "recurring": {"interval": "month"},
    }


def _subscription(
    *,
    market_id,
    plan_code: str,
    status: str = "active",
    sub_id: str | None = None,
    customer_id: str = "cus_1",
    created_ts: int = 1_700_000_000,
    period_end_ts: int = 1_702_592_000,
    pending_update: dict | None = None,
    schedule: str | None = None,
    cancel_at_period_end: bool = False,
) -> dict:
    return {
        "id": sub_id or f"sub_{uuid4()}",
        "status": status,
        "customer": customer_id,
        "schedule": schedule,
        "items": {"data": [{"id": "si_1", "price": _price(plan_code)}]},
        "metadata": {"market_id": str(market_id)},
        "current_period_start": created_ts,
        "current_period_end": period_end_ts,
        "start_date": created_ts,
        "cancel_at_period_end": cancel_at_period_end,
        "canceled_at": None,
        "ended_at": None,
        "trial_start": None,
        "trial_end": None,
        "latest_invoice": "in_1",
        "pending_update": pending_update,
    }


def _event(event_id: str, event_type: str, obj: dict, *, created_ts: int, livemode: bool = False) -> dict:
    return {"id": event_id, "type": event_type, "livemode": livemode, "created": created_ts, "data": {"object": obj}}


class _FakeStripeObject:
    """Minimal stand-in for the installed Stripe SDK's ``StripeObject``:
    supports recursive attribute/item access but — like the real SDK — has
    NO ``.get()`` method, so a lingering ``.get()`` call in production code
    fails here exactly as it does against a real Stripe response. Used to
    prove ``_field``/webhook processing are compatible with real Stripe
    objects, not just the plain-dict fixtures the rest of this file uses.
    """

    def __init__(self, data: dict) -> None:
        wrapped = {}
        for key, value in data.items():
            if isinstance(value, dict):
                value = _FakeStripeObject(value)
            elif isinstance(value, list):
                value = [_FakeStripeObject(item) if isinstance(item, dict) else item for item in value]
            wrapped[key] = value
        object.__setattr__(self, "_data", wrapped)

    def __getitem__(self, key):
        return self._data[key]

    def __getattr__(self, key):
        try:
            return self._data[key]
        except KeyError as exc:
            raise AttributeError(key) from exc


def _stub_subscription_retrieve(monkeypatch, resolver) -> None:
    """Stubs the authoritative pre-apply Stripe fetch that ``webhook._dispatch``
    now performs for subscription-state events (see
    ``SUBSCRIPTION_EVENT_TYPES_REQUIRING_REFETCH``). ``resolver`` is either a
    dict returned for any subscription id, or a callable
    ``(subscription_id) -> dict``. Call again before a later ``process_event``
    in the same test to change what the "current" Stripe state is.
    """

    async def fake_retrieve(subscription_id):
        return resolver(subscription_id) if callable(resolver) else resolver

    monkeypatch.setattr("stripe.Subscription.retrieve_async", fake_retrieve)


# ---------------------------------------------------------------------------
# Checkout route RBAC — HTTP-level, Stripe call stubbed.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_checkout_route_enforces_admin_role_and_tenant_scope_when_test_database_url_is_configured(monkeypatch) -> None:
    engine, session_factory = await _setup_engine()
    monkeypatch.setattr(settings, "stripe_enabled", True)

    async def fake_create_checkout_session(session, market, plan_code, **kwargs):
        return {"checkout_url": "https://stripe.test/checkout/cs_1", "checkout_session_id": "cs_1"}

    monkeypatch.setattr(billing_service, "create_checkout_session", fake_create_checkout_session)

    async def override_session():
        async with session_factory() as session:
            yield session

    market_id = uuid4()
    other_market_id = uuid4()
    app.dependency_overrides[get_catalog_session] = override_session
    try:
        async with session_factory() as session:
            admin_user = User(email=f"admin-{market_id}@example.com", password_hash=hash_password("pw"), is_active=True)
            staff_user = User(email=f"staff-{market_id}@example.com", password_hash=hash_password("pw"), is_active=True)
            market = await _create_market(session, id=market_id)
            other_market = await _create_market(session, id=other_market_id)
            session.add_all([admin_user, staff_user])
            await session.flush()
            session.add(MarketUser(market_id=market.id, user_id=admin_user.id, role="market_admin", is_active=True))
            session.add(MarketUser(market_id=market.id, user_id=staff_user.id, role="market_staff", is_active=True))
            await session.commit()
            admin_token = create_access_token(str(admin_user.id))
            staff_token = create_access_token(str(staff_user.id))

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            staff_response = await client.post(
                "/api/billing/checkout",
                json={"plan_code": "starter"},
                headers={"Authorization": f"Bearer {staff_token}", "X-Market-Id": str(market_id)},
            )
            assert staff_response.status_code == 403

            cross_tenant_response = await client.post(
                "/api/billing/checkout",
                json={"plan_code": "starter"},
                headers={"Authorization": f"Bearer {admin_token}", "X-Market-Id": str(other_market_id)},
            )
            assert cross_tenant_response.status_code == 403

            allowed_response = await client.post(
                "/api/billing/checkout",
                json={"plan_code": "starter"},
                headers={"Authorization": f"Bearer {admin_token}", "X-Market-Id": str(market_id)},
            )
            assert allowed_response.status_code == 200
            assert allowed_response.json()["checkout_url"] == "https://stripe.test/checkout/cs_1"
    finally:
        app.dependency_overrides.pop(get_catalog_session, None)
        await engine.dispose()


@pytest.mark.asyncio
async def test_create_checkout_session_rejects_unassigned_plan_when_test_database_url_is_configured(monkeypatch) -> None:
    engine, session_factory = await _setup_engine()
    monkeypatch.setattr(settings, "stripe_enabled", True)
    try:
        async with session_factory() as session:
            market = await _create_market(session)
            await session.commit()
            with pytest.raises(BillingError):
                await billing_service.create_checkout_session(session, market, "unassigned")
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Checkout guard — reject a second Checkout Session while one already exists
# locally in an active/in-progress state (overlapping-subscription guard).
# ---------------------------------------------------------------------------


class _FakePrice:
    def __init__(self, price_id: str) -> None:
        self.id = price_id


class _FakeCheckoutSession:
    def __init__(self, checkout_url: str, session_id: str) -> None:
        self.url = checkout_url
        self.id = session_id


@pytest.mark.asyncio
@pytest.mark.parametrize("blocking_status", ["active", "trialing", "past_due", "incomplete", "paused"])
async def test_checkout_rejected_when_market_has_in_progress_subscription_when_test_database_url_is_configured(
    blocking_status, monkeypatch
) -> None:
    engine, session_factory = await _setup_engine()
    monkeypatch.setattr(settings, "stripe_enabled", True)
    try:
        async with session_factory() as session:
            market = await _create_market(session)
            session.add(
                MarketSubscription(
                    market_id=market.id,
                    plan_code="starter",
                    status=blocking_status,
                    stripe_customer_id="cus_existing",
                    stripe_subscription_id=f"sub_existing_{blocking_status}",
                )
            )
            await session.commit()

            with pytest.raises(BillingError) as exc_info:
                await billing_service.create_checkout_session(session, market, "standard")
            assert exc_info.value.status_code == 409
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_checkout_allowed_when_market_has_no_local_subscription_when_test_database_url_is_configured(monkeypatch) -> None:
    engine, session_factory = await _setup_engine()
    monkeypatch.setattr(settings, "stripe_enabled", True)
    monkeypatch.setattr(billing_service, "_resolve_price", lambda plan_code: _resolved_price(plan_code))
    monkeypatch.setattr(
        "stripe.checkout.Session.create_async",
        lambda **kwargs: _fake_checkout_session("cs_no_prior_sub"),
    )
    try:
        async with session_factory() as session:
            market = await _create_market(session)
            await session.commit()

            result = await billing_service.create_checkout_session(session, market, "starter")
            assert result["checkout_url"].endswith("cs_no_prior_sub")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal_status", ["canceled", "unpaid", "incomplete_expired"])
async def test_checkout_allowed_after_terminal_subscription_confirmed_terminal_on_stripe_when_test_database_url_is_configured(
    terminal_status, monkeypatch
) -> None:
    # Local terminal status + a Stripe subscription id still on record: the
    # authoritative Stripe lookup must confirm the subscription is actually
    # terminal there too before allowing resubscribe.
    engine, session_factory = await _setup_engine()
    monkeypatch.setattr(settings, "stripe_enabled", True)
    monkeypatch.setattr(billing_service, "_resolve_price", lambda plan_code: _resolved_price(plan_code))
    monkeypatch.setattr(
        "stripe.checkout.Session.create_async",
        lambda **kwargs: _fake_checkout_session("cs_resubscribe"),
    )
    monkeypatch.setattr(
        "stripe.Subscription.retrieve_async",
        lambda subscription_id: _fake_stripe_subscription(terminal_status),
    )
    try:
        async with session_factory() as session:
            market = await _create_market(session)
            session.add(
                MarketSubscription(
                    market_id=market.id,
                    plan_code="unassigned",
                    status=terminal_status,
                    stripe_customer_id="cus_old",
                    stripe_subscription_id=f"sub_old_{terminal_status}",
                )
            )
            await session.commit()

            result = await billing_service.create_checkout_session(session, market, "starter")
            assert result["checkout_url"].endswith("cs_resubscribe")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_checkout_allowed_after_terminal_subscription_without_stripe_subscription_id_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    # No Stripe subscription id on the terminal local row — nothing to
    # authoritatively verify against, so resubscribe proceeds without a
    # Stripe lookup at all.
    engine, session_factory = await _setup_engine()
    monkeypatch.setattr(settings, "stripe_enabled", True)
    monkeypatch.setattr(billing_service, "_resolve_price", lambda plan_code: _resolved_price(plan_code))
    monkeypatch.setattr(
        "stripe.checkout.Session.create_async",
        lambda **kwargs: _fake_checkout_session("cs_resubscribe_no_sub_id"),
    )

    async def _unexpected_retrieve(subscription_id):
        raise AssertionError("Stripe lookup must not happen when there is no stripe_subscription_id")

    monkeypatch.setattr("stripe.Subscription.retrieve_async", _unexpected_retrieve)
    try:
        async with session_factory() as session:
            market = await _create_market(session)
            session.add(
                MarketSubscription(
                    market_id=market.id,
                    plan_code="unassigned",
                    status="canceled",
                    stripe_customer_id=None,
                    stripe_subscription_id=None,
                )
            )
            await session.commit()

            result = await billing_service.create_checkout_session(session, market, "starter")
            assert result["checkout_url"].endswith("cs_resubscribe_no_sub_id")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("local_status", ["canceled", "unpaid"])
@pytest.mark.parametrize("stripe_status", ["active", "past_due"])
async def test_checkout_rejected_when_stripe_shows_subscription_still_in_progress_when_test_database_url_is_configured(
    local_status, stripe_status, monkeypatch
) -> None:
    # Local mirror is stale — it thinks the subscription is terminal, but
    # Stripe says the prior subscription is still active/in-progress. Must
    # reject rather than create a second, overlapping subscription.
    engine, session_factory = await _setup_engine()
    monkeypatch.setattr(settings, "stripe_enabled", True)
    sub_id = f"sub_stale_{local_status}_{stripe_status}"
    monkeypatch.setattr(
        "stripe.Subscription.retrieve_async",
        lambda subscription_id: _fake_stripe_subscription(stripe_status, sub_id=sub_id),
    )
    try:
        async with session_factory() as session:
            market = await _create_market(session)
            session.add(
                MarketSubscription(
                    market_id=market.id,
                    plan_code="unassigned",
                    status=local_status,
                    stripe_customer_id="cus_stale",
                    stripe_subscription_id=sub_id,
                )
            )
            await session.commit()

            with pytest.raises(BillingError) as exc_info:
                await billing_service.create_checkout_session(session, market, "starter")
            assert exc_info.value.status_code == 409
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_checkout_not_created_when_authoritative_stripe_lookup_fails_transiently_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    engine, session_factory = await _setup_engine()
    monkeypatch.setattr(settings, "stripe_enabled", True)

    async def _flaky_retrieve(subscription_id):
        raise stripe.error.APIConnectionError("simulated network blip")

    monkeypatch.setattr("stripe.Subscription.retrieve_async", _flaky_retrieve)

    async def _unexpected_checkout_create(**kwargs):
        raise AssertionError("Checkout Session must not be created when the Stripe lookup fails")

    monkeypatch.setattr("stripe.checkout.Session.create_async", _unexpected_checkout_create)
    try:
        async with session_factory() as session:
            market = await _create_market(session)
            session.add(
                MarketSubscription(
                    market_id=market.id,
                    plan_code="unassigned",
                    status="canceled",
                    stripe_customer_id="cus_flaky",
                    stripe_subscription_id="sub_flaky",
                )
            )
            await session.commit()

            with pytest.raises(BillingError) as exc_info:
                await billing_service.create_checkout_session(session, market, "starter")
            assert exc_info.value.status_code == 503
    finally:
        await engine.dispose()


async def _resolved_price(plan_code: str) -> _FakePrice:
    return _FakePrice(f"price_{plan_code}")


async def _fake_checkout_session(checkout_id: str) -> _FakeCheckoutSession:
    return _FakeCheckoutSession(f"https://stripe.test/checkout/{checkout_id}", checkout_id)


async def _fake_stripe_subscription(status: str, *, sub_id: str = "sub_stale") -> dict:
    return {"id": sub_id, "status": status}


# ---------------------------------------------------------------------------
# Checkout Session request shape: no `customer_creation` in subscription
# mode, `customer` only when known, Managed Payments always explicitly off,
# automatic tax always sent explicitly either way.
# ---------------------------------------------------------------------------


async def _capture_checkout_kwargs(monkeypatch, session_id: str) -> dict:
    captured: dict = {}

    async def fake_create(**kwargs):
        captured.update(kwargs)
        return await _fake_checkout_session(session_id)

    monkeypatch.setattr("stripe.checkout.Session.create_async", fake_create)
    return captured


@pytest.mark.asyncio
async def test_checkout_session_never_sends_customer_creation_in_subscription_mode_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    engine, session_factory = await _setup_engine()
    monkeypatch.setattr(settings, "stripe_enabled", True)
    monkeypatch.setattr(billing_service, "_resolve_price", lambda plan_code: _resolved_price(plan_code))
    captured = await _capture_checkout_kwargs(monkeypatch, "cs_shape")
    try:
        async with session_factory() as session:
            market = await _create_market(session)
            await session.commit()
            await billing_service.create_checkout_session(session, market, "starter")

        assert captured["mode"] == "subscription"
        assert "customer_creation" not in captured
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_checkout_session_uses_existing_customer_id_when_present_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    engine, session_factory = await _setup_engine()
    monkeypatch.setattr(settings, "stripe_enabled", True)
    monkeypatch.setattr(billing_service, "_resolve_price", lambda plan_code: _resolved_price(plan_code))
    captured = await _capture_checkout_kwargs(monkeypatch, "cs_existing_customer")
    try:
        async with session_factory() as session:
            market = await _create_market(session)
            session.add(
                MarketSubscription(
                    market_id=market.id,
                    plan_code="unassigned",
                    status="canceled",
                    stripe_customer_id="cus_known",
                    stripe_subscription_id=None,
                )
            )
            await session.commit()
            await billing_service.create_checkout_session(session, market, "starter")

        assert captured["customer"] == "cus_known"
        assert "customer_email" not in captured
        assert "customer_creation" not in captured
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_checkout_session_omits_customer_when_none_known_when_test_database_url_is_configured(monkeypatch) -> None:
    engine, session_factory = await _setup_engine()
    monkeypatch.setattr(settings, "stripe_enabled", True)
    monkeypatch.setattr(billing_service, "_resolve_price", lambda plan_code: _resolved_price(plan_code))
    captured = await _capture_checkout_kwargs(monkeypatch, "cs_no_customer")
    try:
        async with session_factory() as session:
            market = await _create_market(session)
            await session.commit()
            await billing_service.create_checkout_session(session, market, "starter")

        assert "customer" not in captured
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_checkout_session_always_sends_managed_payments_disabled_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    engine, session_factory = await _setup_engine()
    monkeypatch.setattr(settings, "stripe_enabled", True)
    monkeypatch.setattr(billing_service, "_resolve_price", lambda plan_code: _resolved_price(plan_code))
    captured = await _capture_checkout_kwargs(monkeypatch, "cs_managed_payments")
    try:
        async with session_factory() as session:
            market = await _create_market(session)
            await session.commit()
            await billing_service.create_checkout_session(session, market, "starter")

        assert captured["managed_payments"] == {"enabled": False}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("automatic_tax_enabled", [True, False])
async def test_checkout_session_always_sends_automatic_tax_explicitly_when_test_database_url_is_configured(
    automatic_tax_enabled, monkeypatch
) -> None:
    engine, session_factory = await _setup_engine()
    monkeypatch.setattr(settings, "stripe_enabled", True)
    monkeypatch.setattr(settings, "stripe_automatic_tax_enabled", automatic_tax_enabled)
    monkeypatch.setattr(billing_service, "_resolve_price", lambda plan_code: _resolved_price(plan_code))
    captured = await _capture_checkout_kwargs(monkeypatch, "cs_automatic_tax")
    try:
        async with session_factory() as session:
            market = await _create_market(session)
            await session.commit()
            await billing_service.create_checkout_session(session, market, "starter")

        assert captured["automatic_tax"] == {"enabled": automatic_tax_enabled}
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Checkout email fallback: market.contact_email > fallback user email > omit.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_checkout_session_uses_market_contact_email_over_fallback_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    engine, session_factory = await _setup_engine()
    monkeypatch.setattr(settings, "stripe_enabled", True)
    monkeypatch.setattr(billing_service, "_resolve_price", lambda plan_code: _resolved_price(plan_code))
    captured = await _capture_checkout_kwargs(monkeypatch, "cs_email_contact")
    try:
        async with session_factory() as session:
            market = await _create_market(session, contact_email=" market@example.com ")
            await session.commit()
            await billing_service.create_checkout_session(
                session, market, "starter", fallback_customer_email="user@example.com"
            )

        assert captured["customer_email"] == "market@example.com"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_checkout_session_falls_back_to_user_email_when_contact_email_empty_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    engine, session_factory = await _setup_engine()
    monkeypatch.setattr(settings, "stripe_enabled", True)
    monkeypatch.setattr(billing_service, "_resolve_price", lambda plan_code: _resolved_price(plan_code))
    captured = await _capture_checkout_kwargs(monkeypatch, "cs_email_fallback")
    try:
        async with session_factory() as session:
            market = await _create_market(session, contact_email="   ")
            await session.commit()
            await billing_service.create_checkout_session(
                session, market, "starter", fallback_customer_email=" user@example.com "
            )

        assert captured["customer_email"] == "user@example.com"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_checkout_session_omits_customer_email_when_both_sources_empty_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    engine, session_factory = await _setup_engine()
    monkeypatch.setattr(settings, "stripe_enabled", True)
    monkeypatch.setattr(billing_service, "_resolve_price", lambda plan_code: _resolved_price(plan_code))
    captured = await _capture_checkout_kwargs(monkeypatch, "cs_email_none")
    try:
        async with session_factory() as session:
            market = await _create_market(session, contact_email=None)
            await session.commit()
            await billing_service.create_checkout_session(session, market, "starter", fallback_customer_email=None)

        assert "customer_email" not in captured
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Core sync: entitlement policy per status bucket.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_active_subscription_grants_full_entitlement_when_test_database_url_is_configured() -> None:
    engine, session_factory = await _setup_engine()
    try:
        async with session_factory() as session:
            market = await _create_market(session)
            await session.commit()

            sub = _subscription(market_id=market.id, plan_code="standard", status="active")
            row, applied = await sync_subscription_from_stripe_object(session, sub, event_created_at=_dt(1_700_000_100))
            await session.commit()

            assert applied is True
            assert row.plan_code == "standard"
            await session.refresh(market)
            assert market.subscription_plan == "standard"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_sync_past_due_keeps_current_entitlement_as_grace_when_test_database_url_is_configured() -> None:
    engine, session_factory = await _setup_engine()
    try:
        async with session_factory() as session:
            market = await _create_market(session)
            await session.commit()

            active_sub = _subscription(market_id=market.id, plan_code="standard", status="active")
            await sync_subscription_from_stripe_object(session, active_sub, event_created_at=_dt(1_700_000_100))
            await session.commit()

            past_due_sub = _subscription(market_id=market.id, plan_code="standard", status="past_due")
            row, applied = await sync_subscription_from_stripe_object(session, past_due_sub, event_created_at=_dt(1_700_000_200))
            await session.commit()

            assert applied is True
            assert row.status == "past_due"
            await session.refresh(market)
            assert market.subscription_plan == "standard"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_sync_canceled_subscription_downgrades_to_unassigned_when_test_database_url_is_configured() -> None:
    engine, session_factory = await _setup_engine()
    try:
        async with session_factory() as session:
            market = await _create_market(session)
            await session.commit()

            active_sub = _subscription(market_id=market.id, plan_code="pro", status="active")
            await sync_subscription_from_stripe_object(session, active_sub, event_created_at=_dt(1_700_000_100))
            await session.commit()

            deleted_sub = _subscription(market_id=market.id, plan_code="pro", status="canceled")
            row, applied = await sync_subscription_from_stripe_object(session, deleted_sub, event_created_at=_dt(1_700_000_200))
            await session.commit()

            assert applied is True
            assert row.plan_code == "unassigned"
            await session.refresh(market)
            assert market.subscription_plan == "unassigned"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_sync_cancellation_keeps_entitlement_through_paid_period_when_test_database_url_is_configured() -> None:
    engine, session_factory = await _setup_engine()
    try:
        async with session_factory() as session:
            market = await _create_market(session)
            await session.commit()

            active_sub = _subscription(market_id=market.id, plan_code="starter", status="active")
            await sync_subscription_from_stripe_object(session, active_sub, event_created_at=_dt(1_700_000_100))
            await session.commit()

            cancel_scheduled_sub = _subscription(
                market_id=market.id, plan_code="starter", status="active", cancel_at_period_end=True
            )
            row, applied = await sync_subscription_from_stripe_object(
                session, cancel_scheduled_sub, event_created_at=_dt(1_700_000_200)
            )
            await session.commit()

            assert applied is True
            assert row.cancel_at_period_end is True
            await session.refresh(market)
            assert market.subscription_plan == "starter"
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Unmapped price -> permanent sync error, surfaced on the subscription row.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unmapped_price_raises_permanent_sync_error_carrying_market_id_when_test_database_url_is_configured() -> None:
    # sync_subscription_from_stripe_object itself never persists sync_error —
    # its caller (process_event / resync_from_stripe) rolls back the failed
    # transaction first and records the error in a separate step (see
    # test_unmappable_webhook_event_marks_event_failed_and_subscription_sync_error
    # for that end-to-end behavior). This test only checks the exception's
    # own contract: it must carry the market_id so the caller can do that.
    engine, session_factory = await _setup_engine()
    try:
        async with session_factory() as session:
            market = await _create_market(session)
            await session.commit()

            sub = _subscription(market_id=market.id, plan_code="standard", status="active")
            sub["items"]["data"][0]["price"] = {
                "id": "price_unknown",
                "lookup_key": "some_other_products_price",
                "currency": "eur",
                "unit_amount": 999,
                "recurring": {"interval": "month"},
            }
            with pytest.raises(PermanentSyncError) as exc_info:
                await sync_subscription_from_stripe_object(session, sub, event_created_at=_dt(1_700_000_100))
            assert exc_info.value.market_id == market.id
            assert "Unmapped Stripe price" in str(exc_info.value)
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Out-of-order protection.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stale_event_does_not_regress_subscription_state_when_test_database_url_is_configured() -> None:
    engine, session_factory = await _setup_engine()
    try:
        async with session_factory() as session:
            market = await _create_market(session)
            await session.commit()

            newer_sub = _subscription(market_id=market.id, plan_code="pro", status="active")
            row, applied = await sync_subscription_from_stripe_object(session, newer_sub, event_created_at=_dt(2_000))
            await session.commit()
            assert applied is True
            assert row.plan_code == "pro"
            assert row.last_subscription_event_at == _dt(2_000)

            older_sub = _subscription(market_id=market.id, plan_code="starter", status="active")
            row_after, applied_after = await sync_subscription_from_stripe_object(
                session, older_sub, event_created_at=_dt(1_000)
            )
            await session.commit()

            assert applied_after is False
            assert row_after.plan_code == "pro"
            assert row_after.last_subscription_event_at == _dt(2_000)
            await session.refresh(market)
            assert market.subscription_plan == "pro"
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Upgrade payment safety.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upgrade_with_populated_pending_update_does_not_grant_entitlement_when_test_database_url_is_configured() -> None:
    engine, session_factory = await _setup_engine()
    try:
        async with session_factory() as session:
            market = await _create_market(session)
            await session.commit()

            active_sub = _subscription(market_id=market.id, plan_code="starter", status="active")
            await sync_subscription_from_stripe_object(session, active_sub, event_created_at=_dt(1_700_000_100))
            await session.commit()

            pending_sub = _subscription(
                market_id=market.id,
                plan_code="starter",
                status="active",
                pending_update={
                    "expires_at": 1_700_100_000,
                    "subscription_items": [{"price": _price("pro")}],
                },
            )
            row, applied = await sync_subscription_from_stripe_object(session, pending_sub, event_created_at=_dt(1_700_000_200))
            await session.commit()

            assert applied is True
            assert row.plan_code == "starter"
            assert row.pending_plan_code == "pro"
            assert row.pending_change_reason == "upgrade_pending_payment"
            await session.refresh(market)
            assert market.subscription_plan == "starter"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_invoice_payment_failed_leaves_current_entitlement_when_test_database_url_is_configured() -> None:
    engine, session_factory = await _setup_engine()
    try:
        async with session_factory() as session:
            market = await _create_market(session)
            await session.commit()
            active_sub = _subscription(market_id=market.id, plan_code="starter", status="active", sub_id="sub_pf")
            await sync_subscription_from_stripe_object(session, active_sub, event_created_at=_dt(1_700_000_100))
            await session.commit()

            invoice = {"id": "in_failed", "subscription": "sub_pf"}
            row, applied = await apply_invoice_event(
                session, invoice, event_created_at=_dt(1_700_000_200), kind="payment_failed"
            )
            await session.commit()

            assert applied is True
            assert row.last_payment_status == "payment_failed"
            assert row.plan_code == "starter"
            await session.refresh(market)
            assert market.subscription_plan == "starter"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_invoice_payment_action_required_leaves_current_entitlement_when_test_database_url_is_configured() -> None:
    engine, session_factory = await _setup_engine()
    try:
        async with session_factory() as session:
            market = await _create_market(session)
            await session.commit()
            active_sub = _subscription(market_id=market.id, plan_code="standard", status="active", sub_id="sub_ar")
            await sync_subscription_from_stripe_object(session, active_sub, event_created_at=_dt(1_700_000_100))
            await session.commit()

            invoice = {"id": "in_action", "subscription": "sub_ar"}
            row, applied = await apply_invoice_event(
                session, invoice, event_created_at=_dt(1_700_000_200), kind="payment_action_required"
            )
            await session.commit()

            assert applied is True
            assert row.last_payment_status == "requires_action"
            assert row.plan_code == "standard"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_pending_update_applied_activates_entitlement_exactly_once_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    engine, session_factory = await _setup_engine()
    try:
        async with session_factory() as session:
            market = await _create_market(session)
            await session.commit()

            active_sub = _subscription(market_id=market.id, plan_code="starter", status="active", sub_id="sub_applied")
            starter_event = _event("evt_created", "customer.subscription.created", active_sub, created_ts=1_700_000_100)
            _stub_subscription_retrieve(monkeypatch, active_sub)
            await process_event(session, starter_event)

            applied_sub = _subscription(market_id=market.id, plan_code="pro", status="active", sub_id="sub_applied")
            applied_event = _event(
                "evt_pending_applied", "customer.subscription.pending_update_applied", applied_sub, created_ts=1_700_000_200
            )
            _stub_subscription_retrieve(monkeypatch, applied_sub)
            await process_event(session, applied_event)

            row = await session.scalar(select(MarketSubscription).where(MarketSubscription.market_id == market.id))
            assert row.plan_code == "pro"
            assert row.pending_plan_code is None
            await session.refresh(market)
            assert market.subscription_plan == "pro"

            # Duplicate delivery of the same event id must be a safe no-op.
            await process_event(session, applied_event)
            events = (
                await session.scalars(
                    select(StripeWebhookEvent).where(StripeWebhookEvent.stripe_event_id == "evt_pending_applied")
                )
            ).all()
            assert len(events) == 1
            assert events[0].status == "processed"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_pending_update_expired_clears_pending_without_changing_plan_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    engine, session_factory = await _setup_engine()
    try:
        async with session_factory() as session:
            market = await _create_market(session)
            await session.commit()

            active_sub = _subscription(market_id=market.id, plan_code="starter", status="active", sub_id="sub_expire")
            _stub_subscription_retrieve(monkeypatch, active_sub)
            await process_event(
                session, _event("evt_created2", "customer.subscription.created", active_sub, created_ts=1_700_000_100)
            )

            pending_sub = _subscription(
                market_id=market.id,
                plan_code="starter",
                status="active",
                sub_id="sub_expire",
                pending_update={"expires_at": 1_700_100_000, "subscription_items": [{"price": _price("pro")}]},
            )
            _stub_subscription_retrieve(monkeypatch, pending_sub)
            await process_event(
                session, _event("evt_updated", "customer.subscription.updated", pending_sub, created_ts=1_700_000_200)
            )
            row = await session.scalar(select(MarketSubscription).where(MarketSubscription.market_id == market.id))
            assert row.pending_plan_code == "pro"

            expired_sub = _subscription(market_id=market.id, plan_code="starter", status="active", sub_id="sub_expire")
            _stub_subscription_retrieve(monkeypatch, expired_sub)
            await process_event(
                session,
                _event("evt_expired", "customer.subscription.pending_update_expired", expired_sub, created_ts=1_700_000_300),
            )
            await session.refresh(row)
            assert row.pending_plan_code is None
            assert row.pending_change_reason is None
            assert row.plan_code == "starter"
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Webhook idempotency (DB-level unique constraint race).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_duplicate_webhook_delivery_applies_state_exactly_once_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    engine, session_factory = await _setup_engine()
    try:
        async with session_factory() as session:
            market = await _create_market(session)
            await session.commit()
            market_id = market.id

            sub = _subscription(market_id=market_id, plan_code="standard", status="active", sub_id="sub_dup")
            event = _event("evt_dup", "customer.subscription.created", sub, created_ts=1_700_000_100)
            _stub_subscription_retrieve(monkeypatch, sub)

            await process_event(session, event)
            # The second delivery hits the DB unique constraint and rolls back —
            # SQLAlchemy expires every object in the session on rollback, so any
            # ORM object held from before this point (like `market`) must not be
            # touched again by plain attribute access; use `market_id` instead.
            await process_event(session, event)

            rows = (
                await session.scalars(select(StripeWebhookEvent).where(StripeWebhookEvent.stripe_event_id == "evt_dup"))
            ).all()
            assert len(rows) == 1
            assert rows[0].status == "processed"

            subscription_row = await session.scalar(
                select(MarketSubscription).where(MarketSubscription.market_id == market_id)
            )
            assert subscription_row.plan_code == "standard"
            assert subscription_row.last_subscription_event_at == _dt(1_700_000_100)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_transient_dispatch_failure_is_retryable_by_a_later_delivery_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    engine, session_factory = await _setup_engine()
    try:
        async with session_factory() as session:
            market = await _create_market(session)
            await session.commit()
            market_id = market.id

            sub = _subscription(market_id=market_id, plan_code="starter", status="active", sub_id="sub_transient")
            event = _event("evt_transient", "customer.subscription.created", sub, created_ts=1_700_000_100)
            _stub_subscription_retrieve(monkeypatch, sub)

            original_sync = billing_service.sync_subscription_from_stripe_object
            call_count = {"n": 0}

            async def flaky_sync(session, stripe_subscription, *, event_created_at, market_id_hint=None):
                call_count["n"] += 1
                if call_count["n"] == 1:
                    raise RuntimeError("simulated transient Stripe/network error")
                return await original_sync(
                    session, stripe_subscription, event_created_at=event_created_at, market_id_hint=market_id_hint
                )

            monkeypatch.setattr("app.services.billing.webhook.sync_subscription_from_stripe_object", flaky_sync)

            # First delivery: dispatch fails transiently. process_event must
            # propagate the failure (so the webhook route returns a failure
            # response and Stripe schedules a retry) and must leave the event
            # row retryable rather than permanently stuck.
            with pytest.raises(RuntimeError):
                await process_event(session, event)

            webhook_row = await session.scalar(
                select(StripeWebhookEvent).where(StripeWebhookEvent.stripe_event_id == "evt_transient")
            )
            assert webhook_row.status == "received"
            assert webhook_row.error is not None

            # Second delivery (Stripe retrying the same event id) must
            # actually reprocess — not be treated as an already-handled dup.
            await process_event(session, event)

            rows = (
                await session.scalars(
                    select(StripeWebhookEvent).where(StripeWebhookEvent.stripe_event_id == "evt_transient")
                )
            ).all()
            assert len(rows) == 1
            assert rows[0].status == "processed"
            assert rows[0].error is None
            assert call_count["n"] == 2

            subscription_row = await session.scalar(
                select(MarketSubscription).where(MarketSubscription.market_id == market_id)
            )
            assert subscription_row.plan_code == "starter"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_duplicate_deliveries_apply_business_transition_exactly_once_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    engine, session_factory = await _setup_engine()
    try:
        async with session_factory() as setup_session:
            market = await _create_market(setup_session)
            await setup_session.commit()
            market_id = market.id

        sub = _subscription(market_id=market_id, plan_code="pro", status="active", sub_id="sub_concurrent")
        event = _event("evt_concurrent", "customer.subscription.created", sub, created_ts=1_700_000_100)
        _stub_subscription_retrieve(monkeypatch, sub)

        original_sync = billing_service.sync_subscription_from_stripe_object
        call_count = {"n": 0}

        async def slow_sync(session, stripe_subscription, *, event_created_at, market_id_hint=None):
            call_count["n"] += 1
            # Widen the race window so a genuinely concurrent second delivery
            # reliably reaches the row lock while this one still holds it.
            await asyncio.sleep(0.3)
            return await original_sync(
                session, stripe_subscription, event_created_at=event_created_at, market_id_hint=market_id_hint
            )

        monkeypatch.setattr("app.services.billing.webhook.sync_subscription_from_stripe_object", slow_sync)

        async def deliver():
            async with session_factory() as session:
                await process_event(session, event)

        await asyncio.gather(deliver(), deliver())

        async with session_factory() as session:
            rows = (
                await session.scalars(
                    select(StripeWebhookEvent).where(StripeWebhookEvent.stripe_event_id == "evt_concurrent")
                )
            ).all()
            assert len(rows) == 1
            assert rows[0].status == "processed"

            subscription_row = await session.scalar(
                select(MarketSubscription).where(MarketSubscription.market_id == market_id)
            )
            assert subscription_row.plan_code == "pro"

        # Only the delivery that won the row lock ever reached dispatch — the
        # other blocked on `SELECT ... FOR UPDATE` until the winner
        # committed, then saw a terminal status and returned without
        # reprocessing.
        assert call_count["n"] == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_transient_rollback_does_not_overwrite_concurrently_committed_terminal_state_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    # 1. delivery A claims the event
    # 2. delivery B waits for the same event (blocked on the row lock)
    # 3. A fails transiently and rolls back, releasing the lock
    # 4. B acquires the claim and processes successfully -> terminal "processed"
    # 5. A must not overwrite B's terminal state back to "received"
    # 6. final event status is terminal and the business transition applied exactly once
    engine, session_factory = await _setup_engine()
    try:
        async with session_factory() as setup_session:
            market = await _create_market(setup_session)
            await setup_session.commit()
            market_id = market.id

        sub = _subscription(market_id=market_id, plan_code="pro", status="active", sub_id="sub_race")
        event = _event("evt_race", "customer.subscription.created", sub, created_ts=1_700_000_100)
        _stub_subscription_retrieve(monkeypatch, sub)

        original_sync = billing_service.sync_subscription_from_stripe_object
        call_count = {"n": 0}
        b_may_start = asyncio.Event()

        async def racy_sync(session, stripe_subscription, *, event_created_at, market_id_hint=None):
            call_count["n"] += 1
            if call_count["n"] == 1:
                # Delivery A: signal B to start racing for the row lock,
                # then keep holding the lock a while longer before failing
                # transiently, so B is queued on the lock well before A's
                # rollback releases it.
                b_may_start.set()
                await asyncio.sleep(0.3)
                raise RuntimeError("simulated transient Stripe/network error")
            return await original_sync(
                session, stripe_subscription, event_created_at=event_created_at, market_id_hint=market_id_hint
            )

        monkeypatch.setattr("app.services.billing.webhook.sync_subscription_from_stripe_object", racy_sync)

        async def deliver_a():
            async with session_factory() as session:
                with pytest.raises(RuntimeError):
                    await process_event(session, event)

        async def deliver_b():
            await b_may_start.wait()
            async with session_factory() as session:
                await process_event(session, event)

        await asyncio.gather(deliver_a(), deliver_b())

        async with session_factory() as session:
            rows = (
                await session.scalars(
                    select(StripeWebhookEvent).where(StripeWebhookEvent.stripe_event_id == "evt_race")
                )
            ).all()
            assert len(rows) == 1
            assert rows[0].status == "processed"

            subscription_row = await session.scalar(
                select(MarketSubscription).where(MarketSubscription.market_id == market_id)
            )
            assert subscription_row.plan_code == "pro"
            assert subscription_row.status == "active"

        assert call_count["n"] == 2
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Webhook ordering hardening — separate cursors per event kind, strict '<'.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_distinct_events_with_identical_created_timestamp_both_apply_when_test_database_url_is_configured() -> None:
    engine, session_factory = await _setup_engine()
    try:
        async with session_factory() as session:
            market = await _create_market(session)
            await session.commit()

            first_sub = _subscription(market_id=market.id, plan_code="starter", status="active", sub_id="sub_tie")
            row, applied = await sync_subscription_from_stripe_object(session, first_sub, event_created_at=_dt(5_000))
            await session.commit()
            assert applied is True
            assert row.plan_code == "starter"

            # A genuinely different event with the exact same `created` second
            # (Stripe timestamps are second-granularity) must not be
            # discarded just because the timestamp ties with the last one.
            second_sub = _subscription(market_id=market.id, plan_code="standard", status="active", sub_id="sub_tie")
            row_after, applied_after = await sync_subscription_from_stripe_object(
                session, second_sub, event_created_at=_dt(5_000)
            )
            await session.commit()

            assert applied_after is True
            assert row_after.plan_code == "standard"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_same_second_subscription_events_in_reverse_order_converge_to_authoritative_stripe_state_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    # Two distinct subscription-state events share a `created` second
    # (Stripe timestamps are second-granularity) and are delivered in the
    # reverse of their semantic order (updated before created). Both events'
    # embedded payloads are stale ("standard"); the authoritative Stripe
    # fetch webhook._dispatch now performs before applying state must make
    # the final result match Stripe's actual current state ("pro")
    # regardless of which event arrived last.
    engine, session_factory = await _setup_engine()
    try:
        async with session_factory() as session:
            market = await _create_market(session)
            await session.commit()

            current_sub = _subscription(market_id=market.id, plan_code="pro", status="active", sub_id="sub_reverse")

            def fake_retrieve(subscription_id):
                assert subscription_id == "sub_reverse"
                return current_sub

            _stub_subscription_retrieve(monkeypatch, fake_retrieve)

            stale_payload = _subscription(market_id=market.id, plan_code="standard", status="active", sub_id="sub_reverse")
            updated_event = _event("evt_rev_updated", "customer.subscription.updated", stale_payload, created_ts=9_000)
            created_event = _event("evt_rev_created", "customer.subscription.created", stale_payload, created_ts=9_000)

            await process_event(session, updated_event)
            await process_event(session, created_event)

            row = await session.scalar(select(MarketSubscription).where(MarketSubscription.market_id == market.id))
            assert row.plan_code == "pro"
            await session.refresh(market)
            assert market.subscription_plan == "pro"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_invoice_event_does_not_suppress_later_subscription_transition_when_test_database_url_is_configured() -> None:
    engine, session_factory = await _setup_engine()
    try:
        async with session_factory() as session:
            market = await _create_market(session)
            await session.commit()

            active_sub = _subscription(market_id=market.id, plan_code="starter", status="active", sub_id="sub_order")
            await sync_subscription_from_stripe_object(session, active_sub, event_created_at=_dt(1_000))
            await session.commit()

            # An invoice event with a much later timestamp must only advance
            # the invoice cursor, not the subscription cursor.
            invoice = {"id": "in_order", "subscription": "sub_order"}
            await apply_invoice_event(session, invoice, event_created_at=_dt(5_000), kind="paid")
            await session.commit()

            # A subscription-state event timestamped before the invoice
            # cursor (but after the subscription cursor) must still apply —
            # proving the invoice event did not suppress it.
            upgraded_sub = _subscription(market_id=market.id, plan_code="pro", status="active", sub_id="sub_order")
            row, applied = await sync_subscription_from_stripe_object(session, upgraded_sub, event_created_at=_dt(2_000))
            await session.commit()

            assert applied is True
            assert row.plan_code == "pro"
            await session.refresh(market)
            assert market.subscription_plan == "pro"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_subscription_event_does_not_suppress_later_invoice_event_when_test_database_url_is_configured() -> None:
    engine, session_factory = await _setup_engine()
    try:
        async with session_factory() as session:
            market = await _create_market(session)
            await session.commit()

            active_sub = _subscription(market_id=market.id, plan_code="starter", status="active", sub_id="sub_order2")
            await sync_subscription_from_stripe_object(session, active_sub, event_created_at=_dt(1_000))
            await session.commit()

            # A subscription-state event with a much later timestamp must
            # only advance the subscription cursor, not the invoice cursor.
            later_sub = _subscription(market_id=market.id, plan_code="starter", status="active", sub_id="sub_order2")
            await sync_subscription_from_stripe_object(session, later_sub, event_created_at=_dt(9_000))
            await session.commit()

            # An invoice event timestamped before the subscription cursor
            # (but after the unset invoice cursor) must still apply.
            invoice = {"id": "in_order2", "subscription": "sub_order2"}
            row, applied = await apply_invoice_event(session, invoice, event_created_at=_dt(2_000), kind="paid")
            await session.commit()

            assert applied is True
            assert row.last_payment_status == "paid"
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Sync error visibility + resync recovery.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unmappable_webhook_event_marks_event_failed_and_subscription_sync_error_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    engine, session_factory = await _setup_engine()
    try:
        async with session_factory() as session:
            market = await _create_market(session)
            await session.commit()
            market_id = market.id

            sub = _subscription(market_id=market_id, plan_code="standard", status="active", sub_id="sub_bad")
            sub["items"]["data"][0]["price"] = {
                "id": "price_unknown",
                "lookup_key": "unmapped",
                "currency": "eur",
                "unit_amount": 100,
                "recurring": {"interval": "month"},
            }
            event = _event("evt_bad", "customer.subscription.created", sub, created_ts=1_700_000_100)
            _stub_subscription_retrieve(monkeypatch, sub)
            # This path triggers a PermanentSyncError -> internal rollback, which
            # expires every object in the session; use market_id, not market.id.
            await process_event(session, event)

            webhook_row = await session.scalar(
                select(StripeWebhookEvent).where(StripeWebhookEvent.stripe_event_id == "evt_bad")
            )
            assert webhook_row.status == "failed"
            assert webhook_row.error is not None

            subscription_row = await session.scalar(
                select(MarketSubscription).where(MarketSubscription.market_id == market_id)
            )
            assert subscription_row is not None
            assert subscription_row.sync_error is not None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_resync_clears_sync_error_on_success_and_overwrites_on_failure_when_test_database_url_is_configured(monkeypatch) -> None:
    engine, session_factory = await _setup_engine()
    monkeypatch.setattr(settings, "stripe_enabled", True)
    try:
        async with session_factory() as session:
            market = await _create_market(session)
            await session.commit()

            active_sub = _subscription(market_id=market.id, plan_code="starter", status="active", sub_id="sub_resync")
            await sync_subscription_from_stripe_object(session, active_sub, event_created_at=_dt(1_700_000_100))
            row = await session.scalar(select(MarketSubscription).where(MarketSubscription.market_id == market.id))
            row.sync_error = "a previous failure"
            await session.commit()

            async def fake_retrieve_ok(subscription_id):
                return _subscription(market_id=market.id, plan_code="standard", status="active", sub_id="sub_resync")

            monkeypatch.setattr("stripe.Subscription.retrieve_async", fake_retrieve_ok)
            resynced = await billing_service.resync_from_stripe(session, market)
            assert resynced.sync_error is None
            assert resynced.plan_code == "standard"

            async def fake_retrieve_fail(subscription_id):
                raise Exception("stripe unavailable")

            monkeypatch.setattr("stripe.Subscription.retrieve_async", fake_retrieve_fail)
            with pytest.raises(Exception):
                await billing_service.resync_from_stripe(session, market)

            row_after = await session.scalar(select(MarketSubscription).where(MarketSubscription.market_id == market.id))
            assert row_after.plan_code == "standard"
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Pending plan visibility in customer + platform reads.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_billing_subscription_endpoint_reports_pending_plan_when_test_database_url_is_configured(monkeypatch) -> None:
    engine, session_factory = await _setup_engine()

    async def override_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_catalog_session] = override_session
    try:
        market_id = uuid4()
        async with session_factory() as session:
            user = User(email=f"user-{market_id}@example.com", password_hash=hash_password("pw"), is_active=True)
            market = await _create_market(session, id=market_id, subscription_plan="starter")
            session.add(user)
            await session.flush()
            session.add(MarketUser(market_id=market.id, user_id=user.id, role="market_admin", is_active=True))
            await session.commit()
            token = create_access_token(str(user.id))

            active_sub = _subscription(market_id=market.id, plan_code="starter", status="active")
            await sync_subscription_from_stripe_object(session, active_sub, event_created_at=_dt(1_700_000_100))
            pending_sub = _subscription(
                market_id=market.id,
                plan_code="starter",
                status="active",
                pending_update={"expires_at": 1_700_100_000, "subscription_items": [{"price": _price("pro")}]},
            )
            await sync_subscription_from_stripe_object(session, pending_sub, event_created_at=_dt(1_700_000_200))
            await session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.get(
                "/api/billing/subscription", headers={"Authorization": f"Bearer {token}", "X-Market-Id": str(market_id)}
            )
            assert response.status_code == 200
            body = response.json()
            assert body["plan_code"] == "starter"
            assert body["pending_plan_code"] == "pro"
            assert body["pending_change_reason"] == "upgrade_pending_payment"
    finally:
        app.dependency_overrides.pop(get_catalog_session, None)
        await engine.dispose()


@pytest.mark.asyncio
async def test_platform_market_detail_reports_pending_plan_and_sync_status_when_test_database_url_is_configured(monkeypatch) -> None:
    from app.api.deps import get_current_platform_admin
    from app.api.routes.platform import _market_detail

    engine, session_factory = await _setup_engine()
    try:
        async with session_factory() as session:
            market = await _create_market(session, subscription_plan="standard")
            await session.commit()

            active_sub = _subscription(market_id=market.id, plan_code="standard", status="active")
            await sync_subscription_from_stripe_object(session, active_sub, event_created_at=_dt(1_700_000_100))
            row = await session.scalar(select(MarketSubscription).where(MarketSubscription.market_id == market.id))
            row.pending_plan_code = "starter"
            row.pending_change_reason = "downgrade"
            await session.commit()
            await session.refresh(market)

            detail = await _market_detail(session, market)
            assert detail.billing.plan_code == "standard"
            assert detail.billing.pending_plan_code == "starter"
            assert detail.billing.pending_change_reason == "downgrade"
            assert detail.billing.billing_sync_status == "ok"
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Stripe SDK compatibility — the installed SDK's StripeObject has no
# `.get()`. These use `_FakeStripeObject` fixtures (no `.get()` at all)
# instead of the plain dicts the rest of this file uses, to prove the fix
# actually works against something shaped like a real Stripe response.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_webhook_claim_persists_livemode_from_stripe_object_like_event_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    engine, session_factory = await _setup_engine()
    try:
        async with session_factory() as session:
            market = await _create_market(session)
            await session.commit()

            sub = _subscription(market_id=market.id, plan_code="starter", status="active", sub_id="sub_sdk_1")
            event = _FakeStripeObject(
                _event(
                    "evt_sdk_livemode",
                    "customer.subscription.created",
                    sub,
                    created_ts=1_700_000_100,
                    livemode=True,
                )
            )
            _stub_subscription_retrieve(monkeypatch, _FakeStripeObject(sub))
            await process_event(session, event)

            webhook_row = await session.scalar(
                select(StripeWebhookEvent).where(StripeWebhookEvent.stripe_event_id == "evt_sdk_livemode")
            )
            assert webhook_row.status == "processed"
            assert webhook_row.livemode is True
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_sync_subscription_from_stripe_object_like_fixture_extracts_ids_and_plan_when_test_database_url_is_configured() -> (
    None
):
    engine, session_factory = await _setup_engine()
    try:
        async with session_factory() as session:
            market = await _create_market(session)
            await session.commit()

            sub = _FakeStripeObject(
                _subscription(
                    market_id=market.id,
                    plan_code="pro",
                    status="active",
                    sub_id="sub_sdk_2",
                    customer_id="cus_sdk_2",
                )
            )
            row, applied = await sync_subscription_from_stripe_object(session, sub, event_created_at=_dt(1_700_000_100))
            await session.commit()

            assert applied is True
            assert row.plan_code == "pro"
            assert row.stripe_subscription_id == "sub_sdk_2"
            assert row.stripe_customer_id == "cus_sdk_2"
            await session.refresh(market)
            assert market.subscription_plan == "pro"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_supported_events_process_without_attribute_error_for_stripe_object_like_fixtures_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    engine, session_factory = await _setup_engine()
    try:
        async with session_factory() as session:
            market = await _create_market(session)
            await session.commit()
            market_id = market.id

            sub = _subscription(market_id=market_id, plan_code="standard", status="active", sub_id="sub_sdk_3")
            event = _FakeStripeObject(
                _event("evt_sdk_full", "customer.subscription.created", sub, created_ts=1_700_000_100)
            )
            _stub_subscription_retrieve(monkeypatch, _FakeStripeObject(sub))
            await process_event(session, event)

            webhook_row = await session.scalar(
                select(StripeWebhookEvent).where(StripeWebhookEvent.stripe_event_id == "evt_sdk_full")
            )
            assert webhook_row.status == "processed"

            invoice = _FakeStripeObject(
                {"id": "in_sdk", "subscription": "sub_sdk_3", "status_transitions": {"paid_at": 1_700_000_150}}
            )
            row, applied = await apply_invoice_event(session, invoice, event_created_at=_dt(1_700_000_200), kind="paid")
            await session.commit()
            assert applied is True
            assert row.last_payment_status == "paid"

            subscription_row = await session.scalar(
                select(MarketSubscription).where(MarketSubscription.market_id == market_id)
            )
            assert subscription_row.plan_code == "standard"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_duplicate_delivery_of_stripe_object_like_event_remains_idempotent_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    engine, session_factory = await _setup_engine()
    try:
        async with session_factory() as session:
            market = await _create_market(session)
            await session.commit()

            sub = _subscription(market_id=market.id, plan_code="starter", status="active", sub_id="sub_sdk_4")
            event = _FakeStripeObject(
                _event("evt_sdk_dup", "customer.subscription.created", sub, created_ts=1_700_000_100)
            )
            _stub_subscription_retrieve(monkeypatch, _FakeStripeObject(sub))

            await process_event(session, event)
            await process_event(session, event)

            rows = (
                await session.scalars(
                    select(StripeWebhookEvent).where(StripeWebhookEvent.stripe_event_id == "evt_sdk_dup")
                )
            ).all()
            assert len(rows) == 1
            assert rows[0].status == "processed"
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Legacy plan code display (item: raw "growth" code must not leak to the UI).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_billing_subscription_endpoint_normalizes_legacy_plan_code_without_subscription_row_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    engine, session_factory = await _setup_engine()

    async def override_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_catalog_session] = override_session
    try:
        market_id = uuid4()
        async with session_factory() as session:
            user = User(email=f"user-{market_id}@example.com", password_hash=hash_password("pw"), is_active=True)
            market = await _create_market(session, id=market_id, subscription_plan="growth")
            session.add(user)
            await session.flush()
            session.add(MarketUser(market_id=market.id, user_id=user.id, role="market_admin", is_active=True))
            await session.commit()
            token = create_access_token(str(user.id))

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.get(
                "/api/billing/subscription", headers={"Authorization": f"Bearer {token}", "X-Market-Id": str(market_id)}
            )
            assert response.status_code == 200
            assert response.json()["plan_code"] == "standard"
    finally:
        app.dependency_overrides.pop(get_catalog_session, None)
        await engine.dispose()


# ---------------------------------------------------------------------------
# RBAC: market_staff must not be able to perform billing mutations.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path,body",
    [
        ("/api/billing/portal", None),
        ("/api/billing/change-plan", {"plan_code": "starter"}),
        ("/api/billing/cancel", None),
        ("/api/billing/resume", None),
    ],
)
async def test_billing_mutation_endpoints_reject_market_staff_when_test_database_url_is_configured(
    path, body, monkeypatch
) -> None:
    engine, session_factory = await _setup_engine()
    monkeypatch.setattr(settings, "stripe_enabled", True)

    async def override_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_catalog_session] = override_session
    try:
        market_id = uuid4()
        async with session_factory() as session:
            staff_user = User(email=f"staff-{market_id}@example.com", password_hash=hash_password("pw"), is_active=True)
            market = await _create_market(session, id=market_id)
            session.add(staff_user)
            await session.flush()
            session.add(MarketUser(market_id=market.id, user_id=staff_user.id, role="market_staff", is_active=True))
            await session.commit()
            staff_token = create_access_token(str(staff_user.id))

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.post(
                path,
                json=body,
                headers={"Authorization": f"Bearer {staff_token}", "X-Market-Id": str(market_id)},
            )
            assert response.status_code == 403
    finally:
        app.dependency_overrides.pop(get_catalog_session, None)
        await engine.dispose()


# ---------------------------------------------------------------------------
# Stripe API errors must translate to a controlled response, not an
# unhandled 500 that reaches the browser looking like a CORS failure.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stripe_invalid_request_error_becomes_controlled_response_without_leaking_details_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    engine, session_factory = await _setup_engine()
    monkeypatch.setattr(settings, "stripe_enabled", True)

    async def override_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_catalog_session] = override_session
    try:
        market_id = uuid4()
        async with session_factory() as session:
            admin_user = User(email=f"admin-{market_id}@example.com", password_hash=hash_password("pw"), is_active=True)
            market = await _create_market(session, id=market_id)
            session.add(admin_user)
            await session.flush()
            session.add(MarketUser(market_id=market.id, user_id=admin_user.id, role="market_admin", is_active=True))
            await session.commit()
            admin_token = create_access_token(str(admin_user.id))

        async def failing_create_checkout_session(session, market, plan_code, **kwargs):
            raise stripe.error.InvalidRequestError(
                "customer_creation can only be used in `payment` mode.", param="customer_creation"
            )

        monkeypatch.setattr(billing_service, "create_checkout_session", failing_create_checkout_session)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.post(
                "/api/billing/checkout",
                json={"plan_code": "starter"},
                headers={"Authorization": f"Bearer {admin_token}", "X-Market-Id": str(market_id)},
            )
            assert response.status_code == 502
            detail = response.json()["detail"]
            assert "customer_creation" not in detail
            assert "sk_" not in detail
    finally:
        app.dependency_overrides.pop(get_catalog_session, None)
        await engine.dispose()


@pytest.mark.asyncio
async def test_unexpected_non_stripe_exception_still_surfaces_as_server_error_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    # A genuine programmer bug must not be silently swallowed by the Stripe
    # error translation — only `stripe.error.StripeError` is caught.
    engine, session_factory = await _setup_engine()
    monkeypatch.setattr(settings, "stripe_enabled", True)

    async def override_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_catalog_session] = override_session
    try:
        market_id = uuid4()
        async with session_factory() as session:
            admin_user = User(email=f"admin-{market_id}@example.com", password_hash=hash_password("pw"), is_active=True)
            market = await _create_market(session, id=market_id)
            session.add(admin_user)
            await session.flush()
            session.add(MarketUser(market_id=market.id, user_id=admin_user.id, role="market_admin", is_active=True))
            await session.commit()
            admin_token = create_access_token(str(admin_user.id))

        async def buggy_create_checkout_session(session, market, plan_code, **kwargs):
            raise RuntimeError("simulated programmer bug")

        monkeypatch.setattr(billing_service, "create_checkout_session", buggy_create_checkout_session)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            with pytest.raises(RuntimeError):
                await client.post(
                    "/api/billing/checkout",
                    json={"plan_code": "starter"},
                    headers={"Authorization": f"Bearer {admin_token}", "X-Market-Id": str(market_id)},
                )
    finally:
        app.dependency_overrides.pop(get_catalog_session, None)
        await engine.dispose()
