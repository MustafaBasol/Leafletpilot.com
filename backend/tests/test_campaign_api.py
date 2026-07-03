from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.api.deps import get_catalog_session
from app.core.config import settings
from app.core.database import Base
from app.main import app
from app.models import Campaign, CampaignItem, Market
from app.schemas.campaign import CampaignCreate, CampaignCreateFromTextRequest, CampaignItemResolveMatch
from app.schemas.export import CampaignFileCreate, ExportJobCreate
from app.services.campaign import recalculate_campaign_counts

client = TestClient(app)


def test_campaign_schemas_validate_sample_payloads() -> None:
    campaign = CampaignCreate(
        title="Hafta 28",
        raw_input_text="Coca Cola 2L - 1.59",
        items=[
            {
                "raw_line": "Coca Cola 2L - 1.59",
                "incoming_name": "Coca Cola 2L",
                "price": "1.59",
                "old_price": "1.99",
                "is_hero": True,
            }
        ],
    )
    resolution = CampaignItemResolveMatch(
        resolution="manual_selected",
        product_id=uuid4(),
        notes="Operator picked exact product.",
    )
    file_payload = CampaignFileCreate(file_type="preview_png", format="png")
    export_payload = ExportJobCreate(job_type="preview", requested_formats=["preview_png"])
    from_text = CampaignCreateFromTextRequest(
        title="Hafta 28",
        raw_text="Coca Cola 2L - 1.59€",
        channel="panel",
        source_type="text",
        currency="EUR",
        language="tr",
        generate_suggestions=True,
        suggestion_limit=5,
    )

    assert campaign.items[0].price == Decimal("1.59")
    assert resolution.resolution == "manual_selected"
    assert file_payload.status == "pending"
    assert export_payload.status == "queued"
    assert from_text.raw_text == "Coca Cola 2L - 1.59€"


def test_openapi_schema_contains_campaign_routes() -> None:
    schema = client.get("/openapi.json").json()

    assert "/api/campaigns" in schema["paths"]
    assert "/api/campaigns/parse-text" in schema["paths"]
    assert "/api/campaigns/from-text" in schema["paths"]
    assert "/api/campaigns/{campaign_id}" in schema["paths"]
    assert "/api/campaigns/{campaign_id}/items" in schema["paths"]
    assert "/api/campaigns/{campaign_id}/items/{item_id}/resolve-match" in schema["paths"]
    assert "/api/campaigns/{campaign_id}/items/{item_id}/generate-suggestions" in schema["paths"]
    assert "/api/campaigns/{campaign_id}/generate-suggestions" in schema["paths"]
    assert "/api/campaigns/{campaign_id}/files" in schema["paths"]
    assert "/api/campaigns/{campaign_id}/export-jobs" in schema["paths"]


def test_missing_market_id_returns_400_before_database_session_is_used() -> None:
    response = client.get("/api/campaigns")

    assert response.status_code == 400
    assert response.json()["detail"] == "X-Market-Id is required for campaign routes."

    item_response = client.post(f"/api/campaigns/{uuid4()}/items/{uuid4()}/generate-suggestions", json={})
    assert item_response.status_code == 400
    assert item_response.json()["detail"] == "X-Market-Id is required for campaign routes."

    campaign_response = client.post(f"/api/campaigns/{uuid4()}/generate-suggestions", json={})
    assert campaign_response.status_code == 400
    assert campaign_response.json()["detail"] == "X-Market-Id is required for campaign routes."

    from_text_response = client.post(
        "/api/campaigns/from-text",
        json={"title": "Hafta 28", "raw_text": "Coca Cola 2L - 1.59"},
    )
    assert from_text_response.status_code == 400
    assert from_text_response.json()["detail"] == "X-Market-Id is required for campaign routes."


def test_parse_text_endpoint_works_without_database() -> None:
    response = client.post(
        "/api/campaigns/parse-text",
        json={"raw_text": "Coca Cola 2L - 1.59€\nNo Price", "default_currency": "EUR"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_lines"] == 2
    assert body["parsed_count"] == 2
    assert body["warning_count"] == 1
    assert body["items"][0]["incoming_name"] == "Coca Cola 2L"
    assert body["items"][0]["price"] == "1.59"
    assert body["items"][1]["price"] is None
    assert body["items"][1]["warnings"] == ["no_price_found"]


def test_campaign_count_recalculation_uses_non_excluded_items() -> None:
    campaign = Campaign(title="Counts", market_id=uuid4())
    campaign.items = [
        CampaignItem(raw_line="A", incoming_name="A", market_id=campaign.market_id, match_status="matched"),
        CampaignItem(
            raw_line="B",
            incoming_name="B",
            market_id=campaign.market_id,
            match_status="manual_selected",
        ),
        CampaignItem(raw_line="C", incoming_name="C", market_id=campaign.market_id, match_status="not_found"),
        CampaignItem(
            raw_line="D",
            incoming_name="D",
            market_id=campaign.market_id,
            match_status="new_product_needed",
        ),
        CampaignItem(
            raw_line="E",
            incoming_name="E",
            market_id=campaign.market_id,
            match_status="use_without_image",
        ),
        CampaignItem(
            raw_line="F",
            incoming_name="F",
            market_id=campaign.market_id,
            match_status="low_confidence",
        ),
        CampaignItem(raw_line="G", incoming_name="G", market_id=campaign.market_id, match_status="excluded"),
    ]

    recalculate_campaign_counts(campaign)

    assert campaign.product_count == 6
    assert campaign.matched_count == 2
    assert campaign.missing_count == 3
    assert campaign.low_confidence_count == 1


@pytest.mark.asyncio
async def test_campaign_api_crud_runs_when_test_database_url_is_configured() -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed campaign CRUD tests skipped.")

    engine = create_async_engine(settings.test_database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def override_session():
        async with session_factory() as session:
            yield session

    market_id = uuid4()
    app.dependency_overrides[get_catalog_session] = override_session
    try:
        async with session_factory() as session:
            session.add(Market(id=market_id, name=f"Campaign Test Market {market_id}", slug=f"m-{market_id}"))
            await session.commit()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as async_client:
            headers = {"X-Market-Id": str(market_id)}
            create_response = await async_client.post(
                "/api/campaigns",
                headers=headers,
                json={
                    "title": "Hafta 28",
                    "raw_input_text": "Coca Cola 2L - 1.59",
                    "items": [
                        {
                            "raw_line": "Coca Cola 2L - 1.59",
                            "incoming_name": "Coca Cola 2L",
                            "price": "1.59",
                        }
                    ],
                },
            )
            assert create_response.status_code == 201
            campaign = create_response.json()
            assert campaign["product_count"] == 1
            assert campaign["missing_count"] == 1

            list_response = await async_client.get("/api/campaigns", headers=headers)
            assert list_response.status_code == 200
            assert list_response.json()["total"] >= 1

            detail_response = await async_client.get(f"/api/campaigns/{campaign['id']}", headers=headers)
            assert detail_response.status_code == 200
            assert detail_response.json()["items"][0]["incoming_name"] == "Coca Cola 2L"
    finally:
        app.dependency_overrides.pop(get_catalog_session, None)
        await engine.dispose()


@pytest.mark.asyncio
async def test_campaign_from_text_runs_when_test_database_url_is_configured() -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed campaign from-text tests skipped.")

    engine = create_async_engine(settings.test_database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def override_session():
        async with session_factory() as session:
            yield session

    market_id = uuid4()
    app.dependency_overrides[get_catalog_session] = override_session
    try:
        async with session_factory() as session:
            session.add(Market(id=market_id, name=f"Campaign Text Market {market_id}", slug=f"t-{market_id}"))
            await session.commit()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as async_client:
            response = await async_client.post(
                "/api/campaigns/from-text",
                headers={"X-Market-Id": str(market_id)},
                json={
                    "title": "Hafta 28",
                    "raw_text": "Coca Cola 2L - 1.59€\nEti Burcak - 0.99€",
                    "generate_suggestions": False,
                },
            )

            assert response.status_code == 201
            body = response.json()
            assert body["parsed_count"] == 2
            assert body["product_count"] == 2
            assert body["missing_count"] == 2
            assert body["suggestions_created"] == 0
            assert body["campaign"]["items"][0]["parsed_payload"]["parser"] == "deterministic_text_v1"
    finally:
        app.dependency_overrides.pop(get_catalog_session, None)
        await engine.dispose()
