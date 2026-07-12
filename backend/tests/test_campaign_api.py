from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.api.deps import get_catalog_session, get_current_user
from app.core.config import settings
from app.core.database import Base
from app.main import app
from app.models import Brand, Campaign, CampaignItem, Market, MarketUser, Product, ProductImage, Template, User
from app.schemas.campaign import CampaignCreate, CampaignCreateFromTextRequest, CampaignItemResolveMatch
from app.schemas.export import CampaignFileCreate, ExportJobCreate
from app.services.campaign import recalculate_campaign_counts

client = TestClient(app)


def _override_user(user_id):
    async def override_user():
        return User(id=user_id, email=f"campaign-{user_id}@example.com", is_active=True)

    return override_user


async def _create_market_user(session, market_id, user_id) -> None:
    market = Market(id=market_id, name=f"Campaign Test Market {market_id}", slug=f"m-{market_id}")
    user = User(id=user_id, email=f"campaign-{user_id}@example.com", is_active=True)
    membership = MarketUser(market_id=market_id, user_id=user_id, role="market_admin", is_active=True)
    session.add_all([market, user, membership])
    await session.commit()


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
    export_payload = ExportJobCreate(job_type="final_export", requested_formats=["pdf", "png"])
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
    assert export_payload.requested_formats == ["pdf", "png"]
    with pytest.raises(ValidationError):
        ExportJobCreate(job_type="final_export", requested_formats=["docx"])
    assert from_text.raw_text == "Coca Cola 2L - 1.59€"


def test_openapi_schema_contains_campaign_routes() -> None:
    schema = client.get("/openapi.json").json()

    assert "/api/campaigns" in schema["paths"]
    assert "/api/campaigns/parse-text" in schema["paths"]
    assert "/api/campaigns/from-text" in schema["paths"]
    assert "/api/campaigns/{campaign_id}" in schema["paths"]
    assert "/api/campaigns/{campaign_id}/preview-html" in schema["paths"]
    assert "/api/campaigns/{campaign_id}/items" in schema["paths"]
    assert "/api/campaigns/{campaign_id}/items/{item_id}/resolve-match" in schema["paths"]
    assert "/api/campaigns/{campaign_id}/items/{item_id}/generate-suggestions" in schema["paths"]
    assert "/api/campaigns/{campaign_id}/generate-suggestions" in schema["paths"]
    assert "/api/campaigns/{campaign_id}/files" in schema["paths"]
    assert "/api/campaigns/{campaign_id}/files/{file_id}/download" in schema["paths"]
    assert "/api/campaigns/{campaign_id}/export-jobs" in schema["paths"]


def test_campaign_routes_reject_missing_token_before_database_session_is_used() -> None:
    response = client.get("/api/campaigns")

    assert response.status_code == 401

    item_response = client.post(f"/api/campaigns/{uuid4()}/items/{uuid4()}/generate-suggestions", json={})
    assert item_response.status_code == 401

    campaign_response = client.post(f"/api/campaigns/{uuid4()}/generate-suggestions", json={})
    assert campaign_response.status_code == 401

    preview_response = client.get(f"/api/campaigns/{uuid4()}/preview-html")
    assert preview_response.status_code == 401

    export_response = client.post(
        f"/api/campaigns/{uuid4()}/export-jobs",
        json={"job_type": "final_export", "requested_formats": ["pdf", "png"]},
    )
    assert export_response.status_code == 401

    download_response = client.get(f"/api/campaigns/{uuid4()}/files/{uuid4()}/download")
    assert download_response.status_code == 401

    from_text_response = client.post(
        "/api/campaigns/from-text",
        json={"title": "Hafta 28", "raw_text": "Coca Cola 2L - 1.59"},
    )
    assert from_text_response.status_code == 401


def test_parse_text_endpoint_requires_auth() -> None:
    response = client.post(
        "/api/campaigns/parse-text",
        json={"raw_text": "Coca Cola 2L - 1.59€\nNo Price", "default_currency": "EUR"},
    )

    assert response.status_code == 401


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
    user_id = uuid4()
    app.dependency_overrides[get_catalog_session] = override_session
    app.dependency_overrides[get_current_user] = _override_user(user_id)
    try:
        async with session_factory() as session:
            await _create_market_user(session, market_id, user_id)

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
        app.dependency_overrides.pop(get_current_user, None)
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
    user_id = uuid4()
    app.dependency_overrides[get_catalog_session] = override_session
    app.dependency_overrides[get_current_user] = _override_user(user_id)
    try:
        async with session_factory() as session:
            await _create_market_user(session, market_id, user_id)

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
        app.dependency_overrides.pop(get_current_user, None)
        await engine.dispose()


@pytest.mark.asyncio
async def test_campaign_preview_html_runs_when_test_database_url_is_configured() -> None:
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured; DB-backed campaign preview tests skipped.")

    engine = create_async_engine(settings.test_database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def override_session():
        async with session_factory() as session:
            yield session

    market_id = uuid4()
    user_id = uuid4()
    app.dependency_overrides[get_catalog_session] = override_session
    app.dependency_overrides[get_current_user] = _override_user(user_id)
    try:
        async with session_factory() as session:
            market = Market(
                id=market_id,
                name=f"Campaign Preview Market {market_id}",
                slug=f"p-{market_id}",
                promo_profile_json={"promo_title": "Market Weekend Deals"},
            )
            user = User(id=user_id, email=f"campaign-{user_id}@example.com", is_active=True)
            membership = MarketUser(market_id=market_id, user_id=user_id, role="market_admin", is_active=True)
            template = Template(
                name=f"Premium Market {market_id}",
                slug=f"premium-market-{market_id}",
                template_type="premium",
                is_global=True,
                is_active=True,
                config_json={"layout": "premium-market", "columns": 3},
            )
            brand = Brand(name="Coca Cola", slug=f"coca-{market_id}", market_id=market_id)
            product = Product(
                name="Coca Cola 2L",
                market_id=market_id,
                brand=brand,
                package_size="2L",
                badge_text="Hafta Fırsatı",
                images=[ProductImage(storage_key="missing-test-image.png", is_primary=True, mime_type="image/png")],
            )
            campaign = Campaign(title="Preview <Campaign>", market_id=market_id, template=template)
            campaign.items = [
                CampaignItem(
                    raw_line="Coca Cola 2L - 1.59",
                    incoming_name="Coca Cola 2L",
                    display_name="Coca Cola 2L",
                    price=Decimal("1.59"),
                    old_price=Decimal("1.99"),
                    currency="EUR",
                    product=product,
                    market_id=market_id,
                    match_status="not_found",
                )
            ]
            session.add_all([market, user, membership, template, brand, product, campaign])
            await session.commit()
            campaign_id = campaign.id
            template_id = template.id

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as async_client:
            response = await async_client.get(
                f"/api/campaigns/{campaign_id}/preview-html",
                headers={"X-Market-Id": str(market_id)},
            )

            assert response.status_code == 200
            body = response.json()
            assert body["campaign_id"] == str(campaign_id)
            assert body["template_id"] == str(template_id)
            assert body["template_name"] == f"Premium Market {market_id}"
            assert "Preview &lt;Campaign&gt;" in body["html"]
            assert "Market Weekend Deals" in body["html"]
            assert 'class="product-brand">Coca Cola' in body["html"]
            assert 'class="product-unit">2L' in body["html"]
            assert 'class="promo-badge">Hafta Fırsatı' in body["html"]
            assert "Coca Cola 2L" in body["html"]
    finally:
        app.dependency_overrides.pop(get_catalog_session, None)
        app.dependency_overrides.pop(get_current_user, None)
        await engine.dispose()
