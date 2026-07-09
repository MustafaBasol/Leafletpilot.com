from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.api.deps import get_catalog_session
from app.core.config import settings
from app.core.database import Base
from app.core.lifecycle import can_transition_lifecycle
from app.main import app
from app.models import SignupRequest, SignupThrottle


def test_lifecycle_transition_matrix() -> None:
    allowed = {
        ("trial", "active"),
        ("trial", "suspended"),
        ("active", "suspended"),
        ("suspended", "active"),
        ("trial", "archived"),
        ("active", "archived"),
        ("suspended", "archived"),
    }
    rejected = {
        ("active", "trial"),
        ("suspended", "trial"),
        ("archived", "active"),
        ("archived", "suspended"),
        ("archived", "trial"),
    }
    for current, target in allowed:
        assert can_transition_lifecycle(current, target)
    for current, target in rejected:
        assert not can_transition_lifecycle(current, target)
    assert can_transition_lifecycle("active", "active")


@pytest.mark.asyncio
async def test_public_signup_throttle_dimensions_are_atomic_and_hashed_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed throttle tests skipped.")

    monkeypatch.setattr(settings, "public_signup_throttle_limit", 2)
    monkeypatch.setattr(settings, "public_signup_throttle_window_minutes", 60)
    engine = create_async_engine(settings.test_database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    async def override_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_catalog_session] = override_session
    try:
        payload = _signup_payload("first@example.com")
        async with AsyncClient(
            transport=ASGITransport(app=app, client=("203.0.113.10", 1234)),
            base_url="http://testserver",
        ) as client:
            first = await client.post("/api/public/signup-requests", json=payload)
            second = await client.post("/api/public/signup-requests", json=_signup_payload("second@example.com"))
            third = await client.post("/api/public/signup-requests", json=_signup_payload("third@example.com"))
        assert [first.status_code, second.status_code, third.status_code] == [202, 202, 202]
        assert first.json() == third.json()

        async with AsyncClient(
            transport=ASGITransport(app=app, client=("203.0.113.11", 1234)),
            base_url="http://testserver",
        ) as client:
            same_email = await client.post("/api/public/signup-requests", json=payload)
        assert same_email.status_code == 202
        async with AsyncClient(
            transport=ASGITransport(app=app, client=("203.0.113.12", 1234)),
            base_url="http://testserver",
        ) as client:
            blocked_email = await client.post("/api/public/signup-requests", json=payload)
        assert blocked_email.status_code == 202

        async with session_factory() as session:
            request_count = await session.scalar(select(func.count()).select_from(SignupRequest))
            throttles = (await session.scalars(select(SignupThrottle))).all()
        assert request_count == 3
        assert {row.key_type for row in throttles} == {"ip", "email"}
        assert all("203.0.113" not in row.key_hash for row in throttles)
        assert all("example.com" not in row.key_hash for row in throttles)
    finally:
        app.dependency_overrides.pop(get_catalog_session, None)
        await engine.dispose()


@pytest.mark.asyncio
async def test_public_signup_throttle_concurrent_first_requests_create_unique_rows_when_test_database_url_is_configured(
    monkeypatch,
) -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed throttle tests skipped.")

    monkeypatch.setattr(settings, "public_signup_throttle_limit", 2)
    engine = create_async_engine(settings.test_database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    async def override_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_catalog_session] = override_session
    try:
        async def submit(index: int):
            async with AsyncClient(
                transport=ASGITransport(app=app, client=("203.0.113.20", 1000 + index)),
                base_url="http://testserver",
            ) as client:
                return await client.post("/api/public/signup-requests", json=_signup_payload(f"race-{index}@example.com"))

        responses = await asyncio.gather(*(submit(index) for index in range(6)))
        assert all(response.status_code == 202 for response in responses)
        async with session_factory() as session:
            request_count = await session.scalar(select(func.count()).select_from(SignupRequest))
            key_count = await session.scalar(
                select(func.count())
                .select_from(SignupThrottle)
                .where(SignupThrottle.key_type == "ip")
            )
        assert request_count == 2
        assert key_count == 1
    finally:
        app.dependency_overrides.pop(get_catalog_session, None)
        await engine.dispose()


def _signup_payload(email: str) -> dict:
    suffix = uuid4().hex[:8]
    return {
        "market_name": f"Market {suffix}",
        "contact_name": "Signup Owner",
        "email": email,
        "phone": "+33123456789",
        "country_code": "FR",
        "city": "Paris",
        "preferred_language": "tr",
        "expected_campaigns_per_month": 10,
        "notes": "",
        "consent_accepted": True,
        "website": "",
    }
