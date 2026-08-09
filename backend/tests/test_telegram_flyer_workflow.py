from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.integrations.telegram import service
from app.integrations.telegram.edit_intents import FlyerEditIntent, FlyerEditKind
from app.models import Campaign, CampaignItem, TelegramConversationState
from app.services.campaign_parser import parse_campaign_text


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
    monkeypatch.setattr(service, "_require_selected_mutation_membership", AsyncMock(return_value=membership))
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
    assert state.campaign_id == campaign_id
    assert state.revision_count == 0
    analyze.assert_awaited_once_with(session, campaign_id, state.selected_market_id)
    apply.assert_awaited_once_with(session, campaign_id, state.selected_market_id)
    render.assert_awaited_once()
    assert not any("basligini" in message.lower() for message in client.messages)


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
