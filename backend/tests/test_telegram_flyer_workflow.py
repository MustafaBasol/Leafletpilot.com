from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.integrations.telegram import service
from app.integrations.telegram.edit_intents import FlyerEditIntent, FlyerEditKind
from app.models import Campaign, CampaignItem, Market, TelegramConversationState, Template
from app.services.campaign_intelligence import CampaignIntelligenceEngine
from app.services.campaign_parser import parse_campaign_text
from app.services.campaign_rendering import (
    build_campaign_render_payload,
    render_campaign_snapshot_html,
)
from app.services.preview_renderer import _live_payload, render_campaign_preview_html


class MessageClient:
    def __init__(self) -> None:
        self.messages: list[str] = []
        self.photos = []
        self.documents = []

    async def send_message(self, chat_id, text, *, reply_markup=None) -> None:
        self.messages.append(text)

    async def send_photo(self, chat_id, path, *, caption=None) -> None:
        self.photos.append((path, caption))

    async def send_document(self, chat_id, path, *, caption=None) -> None:
        self.documents.append((path, caption))


def _state(*, campaign_id=None, status="completed") -> TelegramConversationState:
    return TelegramConversationState(
        telegram_account_id=uuid4(),
        user_id=uuid4(),
        telegram_user_id=123,
        chat_id=123,
        selected_market_id=uuid4(),
        state=status,
        campaign_id=campaign_id,
        revision_count=0,
    )


def _campaign() -> Campaign:
    campaign = Campaign(
        id=uuid4(),
        market_id=uuid4(),
        title="Market Firsatlari",
        channel="telegram",
        source_type="text",
        builder_config_json={"smart_composition": True},
    )
    campaign.items = [
        CampaignItem(
            id=uuid4(),
            market_id=campaign.market_id,
            raw_line="Coca Cola 2L - 2.49",
            incoming_name="Coca Cola 2L",
            display_name="Coca Cola 2L",
            price=Decimal("2.49"),
            currency="EUR",
            sort_order=0,
            match_status="matched",
        ),
        CampaignItem(
            id=uuid4(),
            market_id=campaign.market_id,
            raw_line="Eti Burcak - 1.25",
            incoming_name="Eti Burcak",
            display_name="Eti Burcak",
            price=Decimal("1.25"),
            currency="EUR",
            sort_order=1,
            match_status="matched",
        ),
    ]
    return campaign


@pytest.mark.asyncio
async def test_create_message_runs_matching_intelligence_and_preview_without_title_prompt(monkeypatch) -> None:
    state = _state(status="awaiting_product_list")
    client = MessageClient()
    session = SimpleNamespace(commit=AsyncMock())
    market = SimpleNamespace(id=state.selected_market_id, name="Demo Market", currency="EUR", language="tr")
    membership = SimpleNamespace(market_id=state.selected_market_id, market=market, role="market_staff")
    campaign_id = uuid4()
    create = AsyncMock(
        return_value=SimpleNamespace(
            campaign_id=campaign_id,
            missing_count=1,
            low_confidence_count=0,
        )
    )
    analyze = AsyncMock()
    apply = AsyncMock()
    render = AsyncMock()
    template = Template(id=uuid4(), name="Supermarket Promo 4", slug="supermarket-promo-4")
    monkeypatch.setattr(service, "_require_selected_mutation_membership", AsyncMock(return_value=membership))
    monkeypatch.setattr(
        service.template_service,
        "resolve_automatic_supermarket_template",
        AsyncMock(return_value=template),
    )
    monkeypatch.setattr(service.campaign_service, "create_campaign_from_text", create)
    monkeypatch.setattr(service.campaign_service, "analyze_campaign_intelligence", analyze)
    monkeypatch.setattr(service.campaign_service, "apply_campaign_intelligence", apply)
    monkeypatch.setattr(service, "_render_and_send_flyer", render)

    text = "Coca Cola 2L - 2,49\nEti Burcak - 1,25"
    await service._create_and_send_flyer(session, state, text, parse_campaign_text(text), client)

    payload = create.await_args.args[1]
    assert payload.title == "Demo Market Firsatlari"
    assert payload.generate_suggestions is True
    assert payload.raw_text == text
    assert payload.template_id == template.id
    assert state.campaign_id == campaign_id
    assert state.revision_count == 0
    analyze.assert_awaited_once_with(session, campaign_id, state.selected_market_id)
    apply.assert_awaited_once_with(session, campaign_id, state.selected_market_id)
    render.assert_awaited_once()
    assert not any("basligini" in message.lower() for message in client.messages)


@pytest.mark.asyncio
async def test_direct_three_product_route_uses_refinement_and_conversational_geometry(
    monkeypatch,
) -> None:
    state = _state(status="awaiting_product_list")
    client = MessageClient()
    session = SimpleNamespace(commit=AsyncMock())
    market = Market(
        id=state.selected_market_id,
        name="Demo Market",
        slug=f"demo-{state.selected_market_id}",
        currency="EUR",
        language="tr",
    )
    membership = SimpleNamespace(
        market_id=state.selected_market_id,
        market=market,
        role="market_staff",
    )
    template = Template(
        id=uuid4(),
        name="Supermarket Promo 4",
        slug="supermarket-promo-4",
        template_type="supermarket",
        is_global=True,
        is_active=True,
        status="published",
        config_json={"layout": "supermarket-promo-4"},
    )
    campaign = Campaign(
        id=uuid4(),
        market_id=market.id,
        title="Demo Market Firsatlari",
        channel="telegram",
        source_type="text",
        currency="EUR",
        language="tr",
        template_id=template.id,
        template=template,
        market=market,
        builder_config_json={},
    )
    text = "Coca Cola 1L - 29,90\nEti Bur\u00e7ak - 44,90\nS\u00fcta\u015f Yo\u011furt - 74,90"
    parsed = parse_campaign_text(text)
    campaign.items = [
        CampaignItem(
            id=uuid4(),
            market_id=market.id,
            raw_line=item.raw_line,
            incoming_name=item.incoming_name,
            display_name=item.display_name,
            price=item.price,
            currency=item.currency,
            sort_order=index,
            match_status="not_found",
        )
        for index, item in enumerate(parsed)
    ]

    async def create_campaign(_session, payload, market_id):
        assert market_id == market.id
        assert payload.template_id == template.id
        return SimpleNamespace(
            campaign_id=campaign.id,
            missing_count=3,
            low_confidence_count=0,
        )

    async def analyze_campaign(_session, campaign_id, market_id):
        assert (campaign_id, market_id) == (campaign.id, market.id)
        payload = _live_payload(campaign, campaign.template, include_applied_intelligence=False)
        campaign.intelligence_json = CampaignIntelligenceEngine().analyze(
            str(campaign.id),
            list(payload["items"]),
        )

    async def apply_intelligence(_session, campaign_id, market_id):
        assert (campaign_id, market_id) == (campaign.id, market.id)
        campaign.builder_config_json = {
            **(campaign.builder_config_json or {}),
            "smart_composition": True,
            "campaign_intelligence": campaign.intelligence_json,
        }

    rendered_html: list[str] = []

    async def capture_render(*_args, **_kwargs):
        rendered_html.append(
            render_campaign_preview_html(
                campaign,
                campaign.template,
                generated_at=datetime(2026, 8, 9, tzinfo=UTC),
            )
        )

    monkeypatch.setattr(service, "_require_selected_mutation_membership", AsyncMock(return_value=membership))
    monkeypatch.setattr(
        service.template_service,
        "resolve_automatic_supermarket_template",
        AsyncMock(return_value=template),
    )
    monkeypatch.setattr(service.campaign_service, "create_campaign_from_text", create_campaign)
    monkeypatch.setattr(service.campaign_service, "analyze_campaign_intelligence", analyze_campaign)
    monkeypatch.setattr(service.campaign_service, "apply_campaign_intelligence", apply_intelligence)
    monkeypatch.setattr(service.campaign_service, "get_campaign", AsyncMock(return_value=campaign))
    monkeypatch.setattr(service, "_render_and_send_flyer", capture_render)

    await service._create_and_send_flyer(session, state, text, parsed, client)

    default_html = rendered_html[-1]
    assert "preview-supermarket-promo-4" in default_html
    assert 'data-refinement-strategy="balanced-trio"' in default_html
    assert "small-layout-balanced-trio" in default_html
    assert 'data-layout="2x2"' in default_html
    assert "layout-3x1" not in default_html
    assert "Gorsel mevcut degil" in default_html

    await service._apply_flyer_edit(
        session,
        state,
        FlyerEditIntent(FlyerEditKind.CHANGE_HERO_PRODUCT, product_reference="Coca Cola"),
        client,
    )
    hero_html = rendered_html[-1]
    assert 'data-refinement-strategy="hero-trio"' in hero_html
    assert 'data-visual-weight="dominant"' in hero_html
    assert 'data-smart-role="hero"' in hero_html
    assert hero_html != default_html

    await service._apply_flyer_edit(
        session,
        state,
        FlyerEditIntent(FlyerEditKind.ADJUST_VISUAL_DENSITY, value="simpler"),
        client,
    )
    simple_html = rendered_html[-1]
    assert 'data-visual-mode="simple"' in simple_html
    assert 'data-refinement-strategy="simplified-grid"' in simple_html
    assert "composition-simplified-grid" in simple_html
    assert simple_html != hero_html

    snapshot = build_campaign_render_payload(campaign, campaign.template)
    snapshot_html = render_campaign_snapshot_html(
        snapshot,
        generated_at=datetime(2026, 8, 9, tzinfo=UTC),
    )
    snapshot_preview_html = snapshot_html.replace(
        "<body>",
        '<body data-output-format="pdf" data-preview-width="1240" data-preview-height="1754">',
        1,
    )
    assert snapshot_preview_html == simple_html

    legacy_template = Template(
        id=uuid4(),
        name="Legacy Promo 4",
        slug="promo-4",
        template_type="flyer",
        is_global=False,
        is_active=True,
        status="published",
        config_json={"layout": "promo-4"},
    )
    legacy_html = render_campaign_preview_html(
        campaign,
        legacy_template,
        generated_at=datetime(2026, 8, 9, tzinfo=UTC),
    )
    assert "template-promo-4" in legacy_html
    assert "layout-3x1" in legacy_html
    assert "data-refinement-strategy" not in legacy_html


@pytest.mark.asyncio
async def test_no_parseable_price_asks_one_useful_follow_up() -> None:
    state = _state(status="idle")
    state.campaign_id = None
    client = MessageClient()

    await service._handle_plain_text(SimpleNamespace(), state, "sadece urun adi", client)

    assert client.messages == ["Fiyatli urun listenizi dogrudan gonderin. Ornek: Sut 1L - 1,29"]
    assert state.state == "idle"


@pytest.mark.asyncio
async def test_edit_loop_applies_manual_hero_and_preserves_price(monkeypatch) -> None:
    campaign = _campaign()
    state = _state(campaign_id=campaign.id)
    state.selected_market_id = campaign.market_id
    client = MessageClient()
    session = SimpleNamespace(commit=AsyncMock())
    membership = SimpleNamespace(market_id=campaign.market_id, market=SimpleNamespace(), role="market_staff")
    render = AsyncMock()
    monkeypatch.setattr(service, "_require_selected_mutation_membership", AsyncMock(return_value=membership))
    monkeypatch.setattr(service.campaign_service, "get_campaign", AsyncMock(return_value=campaign))
    monkeypatch.setattr(service.campaign_service, "analyze_campaign_intelligence", AsyncMock())
    monkeypatch.setattr(service.campaign_service, "apply_campaign_intelligence", AsyncMock())
    monkeypatch.setattr(service, "_render_and_send_flyer", render)

    original_prices = [item.price for item in campaign.items]
    intent = FlyerEditIntent(FlyerEditKind.CHANGE_HERO_PRODUCT, product_reference="Coca Cola")
    await service._apply_flyer_edit(session, state, intent, client)

    assert campaign.items[0].is_hero is True
    assert campaign.items[1].is_hero is False
    assert [item.price for item in campaign.items] == original_prices
    assert state.revision_count == 1
    assert state.last_edit_intent_json["kind"] == "change_hero_product"
    render.assert_awaited_once()


@pytest.mark.asyncio
async def test_edit_loop_remove_title_simplify_and_unknown_product(monkeypatch) -> None:
    campaign = _campaign()
    state = _state(campaign_id=campaign.id)
    state.selected_market_id = campaign.market_id
    client = MessageClient()
    session = SimpleNamespace(commit=AsyncMock())
    membership = SimpleNamespace(market_id=campaign.market_id, market=SimpleNamespace(), role="market_staff")
    render = AsyncMock()
    monkeypatch.setattr(service, "_require_selected_mutation_membership", AsyncMock(return_value=membership))
    monkeypatch.setattr(service.campaign_service, "get_campaign", AsyncMock(return_value=campaign))
    monkeypatch.setattr(service.campaign_service, "analyze_campaign_intelligence", AsyncMock())
    monkeypatch.setattr(service.campaign_service, "apply_campaign_intelligence", AsyncMock())
    monkeypatch.setattr(service, "_render_and_send_flyer", render)

    await service._apply_flyer_edit(
        session,
        state,
        FlyerEditIntent(FlyerEditKind.REMOVE_PRODUCT, product_reference="Eti Burcak"),
        client,
    )
    assert campaign.items[1].match_status == "excluded"
    assert campaign.product_count == 1

    await service._apply_flyer_edit(
        session,
        state,
        FlyerEditIntent(FlyerEditKind.SET_TITLE, value="Hafta Sonu"),
        client,
    )
    assert campaign.title == "Hafta Sonu"
    assert campaign.builder_config_json["headline"] == "Hafta Sonu"

    await service._apply_flyer_edit(
        session,
        state,
        FlyerEditIntent(FlyerEditKind.ADJUST_VISUAL_DENSITY, value="simpler"),
        client,
    )
    assert campaign.builder_config_json["visual_density"] == "simple"
    assert campaign.builder_config_json["header_style"] == "minimal"
    assert campaign.builder_config_json["layout_strategy"] == "simplified_grid"
    assert campaign.builder_config_json["show_discount_badge"] is False
    assert campaign.builder_config_json["show_footer"] is False

    await service._apply_flyer_edit(
        session,
        state,
        FlyerEditIntent(FlyerEditKind.ADJUST_VISUAL_DENSITY, value="eye_catching"),
        client,
    )
    assert campaign.builder_config_json["visual_density"] == "expressive"
    assert campaign.builder_config_json["layout_strategy"] == "hero_focused"
    assert campaign.builder_config_json["hero_treatment"] == "strong"
    assert campaign.builder_config_json["price_prominence"] == "high"
    assert campaign.builder_config_json["smart_composition"] is True

    render.reset_mock()
    await service._apply_flyer_edit(
        session,
        state,
        FlyerEditIntent(FlyerEditKind.CHANGE_HERO_PRODUCT, product_reference="Olmayan Urun"),
        client,
    )
    render.assert_not_awaited()
    assert "bulunamadi" in client.messages[-1]


@pytest.mark.asyncio
async def test_preview_reply_path_sends_png_and_preserves_active_campaign(tmp_path, monkeypatch) -> None:
    campaign_id = uuid4()
    state = _state(campaign_id=campaign_id)
    state.revision_count = 2
    client = MessageClient()
    session = SimpleNamespace(flush=AsyncMock())
    output = tmp_path / "preview.png"
    output.write_bytes(b"png")
    file_id = uuid4()
    job = SimpleNamespace(id=uuid4(), result_file_ids=[str(file_id)])
    rendered = SimpleNamespace(id=file_id, format="png", storage_key="preview.png")
    monkeypatch.setattr(service.campaign_service, "create_export_job", AsyncMock(return_value=job))
    monkeypatch.setattr(service, "_ready_export_files", AsyncMock(return_value=[rendered]))
    monkeypatch.setattr(service, "_safe_file_path", lambda _: output)

    await service._render_and_send_flyer(
        session,
        state,
        state.selected_market_id,
        client,
        acknowledgement="Guncellendi.",
    )

    request = service.campaign_service.create_export_job.await_args.args[2]
    assert request.job_type == "regenerate_preview"
    assert request.requested_formats == ["png"]
    assert client.photos == [(output, "Ilk taslak hazir. 'Daha sade yap' veya 'bir urunu buyut' diyebilirsiniz.")]
    assert state.campaign_id == campaign_id
    assert state.state == "completed"
