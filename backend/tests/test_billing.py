from datetime import UTC, datetime
from uuid import uuid4

import pytest
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


# ---------------------------------------------------------------------------
# Checkout route RBAC — HTTP-level, Stripe call stubbed.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_checkout_route_enforces_admin_role_and_tenant_scope_when_test_database_url_is_configured(monkeypatch) -> None:
    engine, session_factory = await _setup_engine()
    monkeypatch.setattr(settings, "stripe_enabled", True)

    async def fake_create_checkout_session(session, market, plan_code):
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
            assert row.last_stripe_event_at == _dt(2_000)

            older_sub = _subscription(market_id=market.id, plan_code="starter", status="active")
            row_after, applied_after = await sync_subscription_from_stripe_object(
                session, older_sub, event_created_at=_dt(1_000)
            )
            await session.commit()

            assert applied_after is False
            assert row_after.plan_code == "pro"
            assert row_after.last_stripe_event_at == _dt(2_000)
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
async def test_pending_update_applied_activates_entitlement_exactly_once_when_test_database_url_is_configured() -> None:
    engine, session_factory = await _setup_engine()
    try:
        async with session_factory() as session:
            market = await _create_market(session)
            await session.commit()

            active_sub = _subscription(market_id=market.id, plan_code="starter", status="active", sub_id="sub_applied")
            starter_event = _event("evt_created", "customer.subscription.created", active_sub, created_ts=1_700_000_100)
            await process_event(session, starter_event)

            applied_sub = _subscription(market_id=market.id, plan_code="pro", status="active", sub_id="sub_applied")
            applied_event = _event(
                "evt_pending_applied", "customer.subscription.pending_update_applied", applied_sub, created_ts=1_700_000_200
            )
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
async def test_pending_update_expired_clears_pending_without_changing_plan_when_test_database_url_is_configured() -> None:
    engine, session_factory = await _setup_engine()
    try:
        async with session_factory() as session:
            market = await _create_market(session)
            await session.commit()

            active_sub = _subscription(market_id=market.id, plan_code="starter", status="active", sub_id="sub_expire")
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
            await process_event(
                session, _event("evt_updated", "customer.subscription.updated", pending_sub, created_ts=1_700_000_200)
            )
            row = await session.scalar(select(MarketSubscription).where(MarketSubscription.market_id == market.id))
            assert row.pending_plan_code == "pro"

            expired_sub = _subscription(market_id=market.id, plan_code="starter", status="active", sub_id="sub_expire")
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
async def test_duplicate_webhook_delivery_applies_state_exactly_once_when_test_database_url_is_configured() -> None:
    engine, session_factory = await _setup_engine()
    try:
        async with session_factory() as session:
            market = await _create_market(session)
            await session.commit()
            market_id = market.id

            sub = _subscription(market_id=market_id, plan_code="standard", status="active", sub_id="sub_dup")
            event = _event("evt_dup", "customer.subscription.created", sub, created_ts=1_700_000_100)

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
            assert subscription_row.last_stripe_event_at == _dt(1_700_000_100)
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Sync error visibility + resync recovery.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unmappable_webhook_event_marks_event_failed_and_subscription_sync_error_when_test_database_url_is_configured() -> None:
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
