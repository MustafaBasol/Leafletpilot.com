from __future__ import annotations

import asyncio
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models
from app.api.deps import get_catalog_session, get_current_user
from app.core.config import settings
from app.core.database import Base
from app.main import app
from app.models import (
    AIRevisionProposal,
    AIUsageEvent,
    Campaign,
    CampaignItem,
    CampaignRevision,
    Market,
    MarketUser,
    User,
)
from app.models.base import utc_now
from app.schemas.ai import AIRevisionParseEnvelope
from app.services.ai.dependencies import get_ai_revision_service
from app.services.ai.errors import (
    AIProviderTimeoutError,
    AIProviderTransientError,
    AIUnsupportedCapabilityError,
)
from app.services.ai.orchestrator import AIOrchestrator
from app.services.ai.provider import MockAIProvider
from app.services.ai.registry import AIProviderRegistry
from app.services.ai.revision_parser import AIRevisionService, _validate_actions
from app.services.ai.router import AIModelRouter, classify_revision_capability
from app.services.ai.types import AICapability, AIModelRoute


class NamedMockProvider(MockAIProvider):
    def __init__(self, name, responses):
        super().__init__(responses)
        self.name = name


class DelayedNamedMockProvider(NamedMockProvider):
    async def generate_structured(self, **kwargs):
        await asyncio.sleep(0.15)
        return await super().generate_structured(**kwargs)


def _service(
    provider: MockAIProvider, *, fallback: MockAIProvider | None = None
) -> AIRevisionService:
    registry = AIProviderRegistry()
    registry.register(provider)
    routes = {
        AICapability.CHEAP_TEXT_REVISION: [
            AIModelRoute(AICapability.CHEAP_TEXT_REVISION, provider.name, "cheap-test")
        ],
        AICapability.COMPLEX_TEXT_REVISION: [
            AIModelRoute(AICapability.COMPLEX_TEXT_REVISION, provider.name, "complex-test")
        ],
    }
    if fallback is not None:
        registry.register(fallback)
        routes[AICapability.CHEAP_TEXT_REVISION].append(
            AIModelRoute(AICapability.CHEAP_TEXT_REVISION, fallback.name, "fallback-test")
        )
    return AIRevisionService(AIOrchestrator(registry, AIModelRouter(routes)))


def _override_user(user_id):
    async def override_user():
        return User(id=user_id, email=f"ai-{user_id}@example.com", is_active=True)

    return override_user


def _campaign_graph(market_id):
    campaign = Campaign(
        id=uuid4(),
        market_id=market_id,
        title="AI test kampanyası",
        status="preview_ready",
        currency="EUR",
        language="tr",
        draft_revision=0,
        product_count=2,
        matched_count=2,
    )
    first = CampaignItem(
        id=uuid4(),
        campaign_id=campaign.id,
        market_id=market_id,
        raw_line="Coca Cola 2L 2.49",
        incoming_name="Coca Cola",
        display_name="Coca Cola",
        price=Decimal("2.49"),
        currency="EUR",
        sort_order=0,
        match_status="matched",
    )
    second = CampaignItem(
        id=uuid4(),
        campaign_id=campaign.id,
        market_id=market_id,
        raw_line="Nutella 750g 5.99",
        incoming_name="Nutella",
        display_name="Nutella",
        price=Decimal("5.99"),
        currency="EUR",
        sort_order=1,
        match_status="matched",
    )
    campaign.items = [first, second]
    return campaign, first, second


def test_provider_output_schema_is_strict_and_status_aware():
    with pytest.raises(ValidationError):
        AIRevisionParseEnvelope.model_validate(
            {"status": "ready", "actions": [], "unexpected": "attacker-controlled"}
        )
    with pytest.raises(ValidationError):
        AIRevisionParseEnvelope.model_validate({"status": "clarification_required", "actions": []})
    parsed = AIRevisionParseEnvelope.model_validate(
        {
            "status": "unsupported",
            "actions": [],
            "unsupported_reason": "Bu işlem desteklenmiyor.",
        }
    )
    assert parsed.status == "unsupported"


def test_ai_revision_pydantic_validation_remains_authoritative() -> None:
    action = AIRevisionParseEnvelope.model_validate(
        {
            "status": "ready",
            "actions": [
                {
                    "type": "update_price",
                    "item_id": str(uuid4()),
                    "price": "1.99",
                    "old_price": None,
                }
            ],
        }
    ).actions[0]
    assert action.old_price is None

    with pytest.raises(ValidationError):
        AIRevisionParseEnvelope.model_validate(
            {
                "status": "ready",
                "actions": [
                    {
                        "type": "update_price",
                        "item_id": str(uuid4()),
                        "price": "1.99",
                        "unexpected": "attacker-controlled",
                    }
                ],
            }
        )


@pytest.mark.parametrize(
    ("instruction", "expected"),
    [
        ("Sucuğu en alta al", AICapability.CHEAP_TEXT_REVISION),
        ("Mets le Nutella en première position", AICapability.CHEAP_TEXT_REVISION),
        ("Move Nutella to the top", AICapability.CHEAP_TEXT_REVISION),
        (
            "Kahvaltılık ürünleri üst tarafa topla ve içecekleri aşağı al",
            AICapability.COMPLEX_TEXT_REVISION,
        ),
    ],
)
def test_revision_router_classifies_multilingual_examples(instruction, expected):
    assert classify_revision_capability(instruction) == expected


@pytest.mark.asyncio
async def test_router_uses_explicit_same_capability_fallback():
    primary = NamedMockProvider(
        "primary",
        [AIProviderTransientError("temporary", provider="primary", model="cheap-test")],
    )
    fallback = NamedMockProvider(
        "fallback",
        [{"status": "unsupported", "actions": [], "unsupported_reason": "Not supported"}],
    )
    service = _service(primary, fallback=fallback)
    result = await service._orchestrator.generate_structured(
        capability=AICapability.CHEAP_TEXT_REVISION,
        system_prompt="system",
        user_prompt="Move Nutella",
        schema=AIRevisionParseEnvelope,
        context={"campaign": {}, "items": []},
    )
    assert result.provider == "fallback"
    assert len(primary.calls) == 1
    assert len(fallback.calls) == 1


def test_router_rejects_unsupported_capability():
    router = AIModelRouter({})
    with pytest.raises(AIUnsupportedCapabilityError):
        router.routes_for(AICapability.IMAGE_GENERATION)


def test_commercial_fact_validation_requires_explicit_price_and_rejects_foreign_ids():
    campaign, first, _ = _campaign_graph(uuid4())
    vague_action = AIRevisionParseEnvelope.model_validate(
        {
            "status": "ready",
            "actions": [{"type": "update_price", "item_id": str(first.id), "price": "1.99"}],
        }
    ).actions
    with pytest.raises(Exception, match="explicit price"):
        _validate_actions(campaign, vague_action, "Bu broşürü daha cazip yap")
    _validate_actions(campaign, vague_action, "Coca Cola fiyatını 1,99 yap")

    foreign_action = AIRevisionParseEnvelope.model_validate(
        {
            "status": "ready",
            "actions": [{"type": "remove_item", "item_id": str(uuid4())}],
        }
    ).actions
    with pytest.raises(Exception, match="foreign campaign item"):
        _validate_actions(campaign, foreign_action, "İkinci ürünü kaldır")


@pytest.mark.asyncio
async def test_ai_revision_api_lifecycle_when_test_database_url_is_configured(monkeypatch):
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed AI revision tests skipped.")

    engine = create_async_engine(settings.test_database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    market_id = uuid4()
    other_market_id = uuid4()
    user_id = uuid4()
    staff_user_id = uuid4()
    campaign, first, second = _campaign_graph(market_id)
    responses = [
        {
            "status": "ready",
            "actions": [
                {"type": "move_item", "item_id": str(second.id), "target_position": 1},
                {"type": "set_item_emphasis", "item_id": str(second.id), "emphasis": "large"},
            ],
            "confidence": 0.99,
        },
        {
            "status": "ready",
            "actions": [{"type": "remove_item", "item_id": str(first.id)}],
        },
        {
            "status": "ready",
            "actions": [{"type": "set_hero", "item_id": str(second.id), "is_hero": True}],
        },
        {
            "status": "clarification_required",
            "actions": [],
            "clarification_question": "Hangi peynir ürününü kastediyorsunuz?",
        },
        {
            "status": "unsupported",
            "actions": [],
            "unsupported_reason": "Görsel üretimi AI-2 kapsamında değil.",
        },
        {
            "status": "ready",
            "actions": [{"type": "remove_item", "item_id": str(uuid4())}],
        },
        {
            "status": "ready",
            "actions": [{"type": "update_price", "item_id": str(first.id), "price": "3.99"}],
        },
        {
            "status": "ready",
            "actions": [{"type": "update_price", "item_id": str(first.id), "price": "1.99"}],
        },
    ]
    provider = DelayedNamedMockProvider("mock_primary", responses)
    ai_service = _service(provider)
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "ai_revision_enabled", True)
    monkeypatch.setattr(settings, "ai_revision_rate_limit_per_minute", 100)

    async with session_factory() as session:
        market = Market(id=market_id, name="AI Market", slug=f"ai-{market_id}")
        other_market = Market(
            id=other_market_id,
            name="Other AI Market",
            slug=f"ai-{other_market_id}",
        )
        user = User(id=user_id, email=f"ai-{user_id}@example.com", is_active=True)
        staff_user = User(
            id=staff_user_id,
            email=f"ai-staff-{staff_user_id}@example.com",
            is_active=True,
        )
        session.add_all(
            [
                market,
                other_market,
                user,
                staff_user,
                MarketUser(
                    market_id=market_id,
                    user_id=user_id,
                    role="market_admin",
                    is_active=True,
                ),
                MarketUser(
                    market_id=market_id,
                    user_id=staff_user_id,
                    role="market_staff",
                    is_active=True,
                ),
                MarketUser(
                    market_id=other_market_id,
                    user_id=user_id,
                    role="market_admin",
                    is_active=True,
                ),
                campaign,
            ]
        )
        await session.commit()

    async def override_session():
        async with session_factory() as session:
            yield session

    async def override_ai_service():
        return ai_service

    app.dependency_overrides[get_catalog_session] = override_session
    app.dependency_overrides[get_current_user] = _override_user(user_id)
    app.dependency_overrides[get_ai_revision_service] = override_ai_service
    headers = {"X-Market-Id": str(market_id)}
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            payload = {
                "instruction": "Nutella'yı ilk sıraya al ve daha büyük göster",
                "expected_revision": 0,
                "client_request_id": "ai-ready-1",
            }
            preview, concurrent_replay = await asyncio.gather(
                client.post(
                    f"/api/campaigns/{campaign.id}/revision-intent",
                    headers=headers,
                    json=payload,
                ),
                client.post(
                    f"/api/campaigns/{campaign.id}/revision-intent",
                    headers=headers,
                    json=payload,
                ),
            )
            assert preview.status_code == 200, preview.text
            assert concurrent_replay.status_code == 200, concurrent_replay.text
            proposal = preview.json()
            assert proposal["status"] == "ready"
            assert len(proposal["summary"]) == 2
            assert concurrent_replay.json()["id"] == proposal["id"]
            assert sorted([proposal["idempotent"], concurrent_replay.json()["idempotent"]]) == [
                False,
                True,
            ]
            assert len(provider.calls) == 1

            async with session_factory() as session:
                stored_campaign = await session.get(Campaign, campaign.id)
                assert stored_campaign.draft_revision == 0
                assert await session.scalar(select(CampaignRevision)) is None

            conflict = await client.post(
                f"/api/campaigns/{campaign.id}/revision-intent",
                headers=headers,
                json={**payload, "instruction": "İkinci ürünü kaldır"},
            )
            assert conflict.status_code == 409
            assert len(provider.calls) == 1

            spoofed = await client.post(
                f"/api/campaigns/{campaign.id}/revision-intent",
                headers=headers,
                json={**payload, "client_request_id": "spoofed", "source": "panel"},
            )
            assert spoofed.status_code == 422
            assert len(provider.calls) == 1

            cross_market = await client.post(
                f"/api/campaigns/{campaign.id}/revision-intent/{proposal['id']}/apply",
                headers={"X-Market-Id": str(other_market_id)},
            )
            assert cross_market.status_code == 404

            calls_before_cross_market = len(provider.calls)
            cross_market_create = await client.post(
                f"/api/campaigns/{campaign.id}/revision-intent",
                headers={"X-Market-Id": str(other_market_id)},
                json={**payload, "client_request_id": "ai-cross-market-create"},
            )
            assert cross_market_create.status_code == 404
            assert len(provider.calls) == calls_before_cross_market

            applied = await client.post(
                f"/api/campaigns/{campaign.id}/revision-intent/{proposal['id']}/apply",
                headers=headers,
                json={
                    "actions": [
                        {"type": "remove_item", "item_id": str(first.id)},
                    ]
                },
            )
            assert applied.status_code == 200, applied.text
            assert applied.json()["revision"]["revision"]["source"] == "ai"
            assert applied.json()["revision"]["revision"]["created_by_user_id"] == str(user_id)
            assert applied.json()["revision"]["draft_revision"] == 1
            async with session_factory() as session:
                stored_first = await session.get(CampaignItem, first.id)
                stored_second = await session.get(CampaignItem, second.id)
                assert stored_first.is_hidden is False
                assert stored_second.sort_order == 0
                assert stored_second.emphasis == "large"

            applied_replay = await client.post(
                f"/api/campaigns/{campaign.id}/revision-intent/{proposal['id']}/apply",
                headers=headers,
            )
            assert applied_replay.status_code == 200
            assert applied_replay.json()["revision"]["idempotent"] is True

            stale_preview = await client.post(
                f"/api/campaigns/{campaign.id}/revision-intent",
                headers=headers,
                json={
                    "instruction": "Coca Cola'yı kaldır",
                    "expected_revision": 1,
                    "client_request_id": "ai-stale-1",
                },
            )
            assert stale_preview.status_code == 200
            async with session_factory() as session:
                stored_campaign = await session.get(Campaign, campaign.id)
                stored_campaign.draft_revision = 2
                await session.commit()
            stale_apply = await client.post(
                f"/api/campaigns/{campaign.id}/revision-intent/{stale_preview.json()['id']}/apply",
                headers=headers,
            )
            assert stale_apply.status_code == 409

            expiring = await client.post(
                f"/api/campaigns/{campaign.id}/revision-intent",
                headers=headers,
                json={
                    "instruction": "Nutella'yı ana ürün yap",
                    "expected_revision": 2,
                    "client_request_id": "ai-expired-1",
                },
            )
            assert expiring.status_code == 200
            async with session_factory() as session:
                stored = await session.get(AIRevisionProposal, expiring.json()["id"])
                stored.expires_at = utc_now() - timedelta(seconds=1)
                await session.commit()
            expired_apply = await client.post(
                f"/api/campaigns/{campaign.id}/revision-intent/{expiring.json()['id']}/apply",
                headers=headers,
            )
            assert expired_apply.status_code == 409
            assert expired_apply.json()["detail"]["code"] == "proposal_expired"

            clarification = await client.post(
                f"/api/campaigns/{campaign.id}/revision-intent",
                headers=headers,
                json={
                    "instruction": "Peyniri yukarı al",
                    "expected_revision": 2,
                    "client_request_id": "ai-clarify-1",
                },
            )
            assert clarification.status_code == 200
            assert clarification.json()["status"] == "clarification_required"
            assert clarification.json()["actions"] == []

            unsupported = await client.post(
                f"/api/campaigns/{campaign.id}/revision-intent",
                headers=headers,
                json={
                    "instruction": "Yeni bir sucuk görseli üret",
                    "expected_revision": 2,
                    "client_request_id": "ai-unsupported-1",
                },
            )
            assert unsupported.status_code == 200
            assert unsupported.json()["status"] == "unsupported"

            foreign_item = await client.post(
                f"/api/campaigns/{campaign.id}/revision-intent",
                headers=headers,
                json={
                    "instruction": "İkinci ürünü kaldır",
                    "expected_revision": 2,
                    "client_request_id": "ai-foreign-1",
                },
            )
            assert foreign_item.status_code == 502

            vague_price = await client.post(
                f"/api/campaigns/{campaign.id}/revision-intent",
                headers=headers,
                json={
                    "instruction": "Bu broşürü daha cazip yap",
                    "expected_revision": 2,
                    "client_request_id": "ai-vague-price-1",
                },
            )
            assert vague_price.status_code == 502

            explicit_price = await client.post(
                f"/api/campaigns/{campaign.id}/revision-intent",
                headers=headers,
                json={
                    "instruction": "Coca Cola fiyatını 1,99 yap",
                    "expected_revision": 2,
                    "client_request_id": "ai-explicit-price-1",
                },
            )
            assert explicit_price.status_code == 200, explicit_price.text
            explicit_apply = await client.post(
                f"/api/campaigns/{campaign.id}/revision-intent/{explicit_price.json()['id']}/apply",
                headers=headers,
            )
            assert explicit_apply.status_code == 200, explicit_apply.text

            async with session_factory() as session:
                stored_campaign = await session.get(Campaign, campaign.id)
                stored_campaign.frozen_at = utc_now()
                await session.commit()
            calls_before_frozen = len(provider.calls)
            frozen = await client.post(
                f"/api/campaigns/{campaign.id}/revision-intent",
                headers=headers,
                json={
                    "instruction": "Nutella'yı en alta al",
                    "expected_revision": 3,
                    "client_request_id": "ai-frozen-1",
                },
            )
            assert frozen.status_code == 409
            assert len(provider.calls) == calls_before_frozen

            async with session_factory() as session:
                membership = await session.scalar(
                    select(MarketUser).where(
                        MarketUser.market_id == market_id,
                        MarketUser.user_id == user_id,
                    )
                )
                membership.role = "viewer"
                await session.commit()
            unauthorized = await client.post(
                f"/api/campaigns/{campaign.id}/revision-intent",
                headers=headers,
                json={
                    "instruction": "Nutella'yı en alta al",
                    "expected_revision": 3,
                    "client_request_id": "ai-staff-1",
                },
            )
            assert unauthorized.status_code == 403
            assert len(provider.calls) == calls_before_frozen
            async with session_factory() as session:
                membership = await session.scalar(
                    select(MarketUser).where(
                        MarketUser.market_id == market_id,
                        MarketUser.user_id == user_id,
                    )
                )
                membership.role = "market_admin"
                await session.commit()

            async with session_factory() as session:
                stored_campaign = await session.get(Campaign, campaign.id)
                stored_campaign.frozen_at = None
                await session.commit()

            timeout_provider = NamedMockProvider(
                "timeout_provider",
                [
                    AIProviderTimeoutError(
                        "timeout",
                        provider="timeout_provider",
                        model="cheap-test",
                    )
                ],
            )
            timeout_service = _service(timeout_provider)

            async def override_timeout_service():
                return timeout_service

            app.dependency_overrides[get_ai_revision_service] = override_timeout_service
            timeout = await client.post(
                f"/api/campaigns/{campaign.id}/revision-intent",
                headers=headers,
                json={
                    "instruction": "Nutella'yı en alta al",
                    "expected_revision": 3,
                    "client_request_id": "ai-timeout-1",
                },
            )
            assert timeout.status_code == 503
            assert timeout.json()["detail"]["code"] == "provider_timeout"

            malformed_provider = NamedMockProvider(
                "malformed_provider",
                [{"status": "ready", "actions": [{"type": "execute_sql"}]}],
            )
            malformed_service = _service(malformed_provider)

            async def override_malformed_service():
                return malformed_service

            app.dependency_overrides[get_ai_revision_service] = override_malformed_service
            malformed = await client.post(
                f"/api/campaigns/{campaign.id}/revision-intent",
                headers=headers,
                json={
                    "instruction": "Nutella'yı en alta al",
                    "expected_revision": 3,
                    "client_request_id": "ai-malformed-1",
                },
            )
            assert malformed.status_code == 502
            assert malformed.json()["detail"]["code"] == "schema_invalid"

        async with session_factory() as session:
            usage = list(await session.scalars(select(AIUsageEvent)))
            assert any(event.status == "success" and event.input_tokens is None for event in usage)
            assert sum(event.status == "failed" for event in usage) >= 2
            assert any(event.status == "timeout" for event in usage)
            assert all(not hasattr(event, "instruction") for event in usage)
        first_context = provider.calls[0]["context"]
        assert set(first_context) == {"campaign", "items"}
        assert "user" not in str(first_context).casefold()
    finally:
        app.dependency_overrides.pop(get_catalog_session, None)
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_ai_revision_service, None)
        await engine.dispose()
