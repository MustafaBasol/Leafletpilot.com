from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.lifecycle import inactive_market_message, market_allows_mutations
from app.core.roles import MARKET_MUTATION_ROLES
from app.integrations.telegram.client import TelegramClientError, TelegramClientProtocol
from app.integrations.telegram.edit_intents import (
    FlyerEditIntent,
    FlyerEditKind,
    normalize_for_match,
    parse_flyer_edit_intent,
)
from app.integrations.telegram.schemas import InlineKeyboardMarkup
from app.integrations.telegram.schemas import TelegramUpdate as TelegramUpdatePayload
from app.integrations.telegram.state_machine import TelegramState
from app.models import (
    Campaign,
    CampaignFile,
    CampaignItem,
    ExportJob,
    MarketUser,
    TelegramAccount,
    TelegramConversationState,
    TelegramUpdate,
)
from app.models.base import utc_now
from app.schemas.campaign import RAW_TEXT_MAX_LENGTH, CampaignCreateFromTextRequest
from app.schemas.export import ExportJobCreate
from app.services import campaign as campaign_service
from app.services.campaign_parser import ParsedCampaignLine, parse_campaign_text
from app.services.rendering import storage_path_for_key

logger = logging.getLogger(__name__)

HELP_TEXT = (
    "Komutlar:\n"
    "/start - botu baslat\n"
    "/markets - yetkili marketleri sec\n"
    "/new - yeni kampanya baslat\n"
    "/status - mevcut durumu goster\n"
    "/cancel - mevcut akisi iptal et\n"
    "/help - yardim\n\n"
    "Dogrudan urun listenizi gonderebilirsiniz. Ornek:\n"
    "Sut 1L - 1.29\n"
    "Coca Cola 2L old 1.99 new 1.59\n\n"
    "Sonra 'Coca Cola'yi buyut', 'Daha sade yap' veya 'PDF gonder' yazabilirsiniz."
)
PROCESSING_LEASE = timedelta(minutes=5)


async def process_update(
    session: AsyncSession,
    update: TelegramUpdatePayload,
    client: TelegramClientProtocol,
) -> None:
    record = await _begin_update(session, update)
    if record is None:
        return

    try:
        await _process_update_body(session, update, client)
    except Exception as exc:
        logger.exception(
            "Telegram update failed. update_id=%s update_type=%s",
            update.update_id,
            update.update_type,
        )
        record.status = "failed"
        record.last_error = _safe_error(exc)
        record.processed_at = utc_now()
        await session.commit()
        raise

    record.status = "completed"
    record.last_error = None
    record.processed_at = utc_now()
    await session.commit()


async def _begin_update(session: AsyncSession, update: TelegramUpdatePayload) -> TelegramUpdate | None:
    now = utc_now()
    existing = await session.scalar(
        select(TelegramUpdate).where(TelegramUpdate.update_id == update.update_id).with_for_update()
    )
    if existing is not None and existing.status == "completed":
        return None
    if existing is not None and existing.status in {"received", "processing"}:
        lease_started_at = existing.processing_started_at or existing.updated_at or existing.received_at
        if lease_started_at is not None and now - lease_started_at < PROCESSING_LEASE:
            return None
    if existing is not None:
        existing.status = "processing"
        existing.attempt_count += 1
        existing.last_error = None
        existing.processing_started_at = now
        await session.commit()
        return existing

    user = update.telegram_user
    chat = update.chat
    record = TelegramUpdate(
        update_id=update.update_id,
        status="processing",
        telegram_user_id=user.id if user else None,
        chat_id=chat.id if chat else None,
        update_type=update.update_type,
        attempt_count=1,
        processing_started_at=now,
    )
    session.add(record)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        duplicate = await session.scalar(select(TelegramUpdate).where(TelegramUpdate.update_id == update.update_id))
        if duplicate is None or duplicate.status != "failed":
            return None
        duplicate.status = "processing"
        duplicate.attempt_count += 1
        duplicate.processing_started_at = now
        await session.commit()
        return duplicate
    await session.refresh(record)
    return record


async def _process_update_body(
    session: AsyncSession,
    update: TelegramUpdatePayload,
    client: TelegramClientProtocol,
) -> None:
    if update.callback_query is not None:
        await client.answer_callback_query(update.callback_query.id)

    user = update.telegram_user
    chat = update.chat
    if user is None or chat is None:
        return
    if chat.type != "private":
        await client.send_message(chat.id, "Bu bot MVP asamasinda sadece ozel sohbetlerde kullanilir.")
        return

    account = await _get_active_account(session, user.id)
    if account is None:
        await client.send_message(chat.id, "Telegram hesabiniz LeafletPilot kullanicisina bagli degil.")
        return
    if not account.user.is_active:
        await client.send_message(chat.id, "LeafletPilot kullaniciniz aktif degil.")
        return

    account.last_chat_id = chat.id
    account.username = user.username or account.username
    account.first_name = user.first_name or account.first_name
    account.last_name = user.last_name or account.last_name
    state = await _get_or_create_locked_state(session, account, chat.id)
    state.last_message_at = utc_now()
    await session.flush()

    if update.callback_data is not None:
        await _handle_callback(session, state, update.callback_data, client)
        return

    text = (update.text or "").strip()
    if not text:
        await client.send_message(chat.id, "Lutfen duz metin bir urun listesi veya komut gonderin.")
        return
    if text.startswith("/"):
        await _handle_command(session, state, text.split()[0].lower(), client)
        return
    await _handle_plain_text(session, state, text, client)


async def _handle_command(
    session: AsyncSession,
    state: TelegramConversationState,
    command: str,
    client: TelegramClientProtocol,
) -> None:
    chat_id = _chat_id(state)
    if command == "/start":
        await _start(session, state, client)
    elif command == "/markets":
        await _show_markets(session, state, client)
    elif command == "/new":
        membership = await _selected_membership(session, state)
        if membership is None:
            await client.send_message(chat_id, "Kampanya olusturmak icin market_admin veya market_staff rolu gerekir.")
            return
        if not market_allows_mutations(membership.market):
            await client.send_message(chat_id, inactive_market_message())
            return
        if membership.role not in MARKET_MUTATION_ROLES:
            await client.send_message(chat_id, "Kampanya olusturmak icin market_admin veya market_staff rolu gerekir.")
            return
        _reset_draft(state)
        state.state = TelegramState.AWAITING_PRODUCT_LIST.value
        await client.send_message(chat_id, "Urun listesini duz metin olarak gonderin.")
    elif command == "/status":
        await client.send_message(chat_id, await _status_text(session, state))
    elif command == "/cancel":
        await _cancel(session, state, client)
    elif command == "/help":
        await client.send_message(chat_id, HELP_TEXT)
    else:
        await client.send_message(chat_id, "Desteklenmeyen komut. /help yazabilirsiniz.")


async def _handle_plain_text(
    session: AsyncSession,
    state: TelegramConversationState,
    text: str,
    client: TelegramClientProtocol,
) -> None:
    chat_id = _chat_id(state)
    intent = parse_flyer_edit_intent(text) if state.campaign_id is not None else None
    if intent is not None:
        await _apply_flyer_edit(session, state, intent, client)
        return

    if state.state != TelegramState.AWAITING_TITLE.value:
        if len(text) > RAW_TEXT_MAX_LENGTH:
            await client.send_message(chat_id, "Liste cok uzun. Lutfen daha kisa bir liste gonderin.")
            return
        parsed = parse_campaign_text(text)
        usable = [item for item in parsed if item.incoming_name.strip()]
        priced = [item for item in parsed if item.incoming_name.strip() and item.price is not None]
        if priced:
            if len(usable) > 16:
                await client.send_message(chat_id, "Tek brosurde en fazla 16 urun kullanin; listeyi bolerek tekrar gonderin.")
                return
            await _create_and_send_flyer(session, state, text, parsed, client)
            return
        if state.state == TelegramState.AWAITING_PRODUCT_LIST.value:
            await client.send_message(
                chat_id,
                "Fiyatli bir urun satiri bulamadim. Ornek: Sut 1L - 1,29",
            )
            return

    if state.state == TelegramState.AWAITING_TITLE.value:
        if state.campaign_id is not None:
            await client.send_message(chat_id, "Bu kampanya basligi zaten islendi.")
            return
        title = text[:255].strip()
        if not title:
            await client.send_message(chat_id, "Lutfen kampanya basligi gonderin.")
            return
        membership = await _selected_membership(session, state)
        if membership is None or membership.role not in MARKET_MUTATION_ROLES:
            await client.send_message(chat_id, "Bu market icin kampanya olusturma yetkiniz yok.")
            return
        if not market_allows_mutations(membership.market):
            await client.send_message(chat_id, inactive_market_message())
            return
        payload = CampaignCreateFromTextRequest(
            title=title,
            raw_text=state.pending_raw_text or "",
            channel="telegram",
            source_type="text",
            currency=membership.market.currency,
            language=membership.market.language,
            generate_suggestions=False,
        )
        result = await campaign_service.create_campaign_from_text(session, payload, membership.market_id, commit=False)
        state.pending_title = title
        state.campaign_id = result.campaign_id
        state.state = TelegramState.AWAITING_CONFIRMATION.value
        await client.send_message(
            chat_id,
            (
                f"Kampanya olusturuldu: {title}\n"
                f"Urun: {result.product_count}, eslesen: {result.matched_count}, eksik: {result.missing_count}\n"
                "PDF ve PNG olusturulsun mu?"
            ),
            reply_markup=_confirmation_keyboard(),
        )
        return

    if state.state == TelegramState.AWAITING_CONFIRMATION.value and state.campaign_id is not None:
        await client.send_message(
            chat_id,
            "Bu kampanya aktif. 'Daha sade yap', 'bir urunu buyut' veya yeni bir fiyat listesi gonderebilirsiniz.",
        )
        return

    await client.send_message(
        chat_id,
        "Fiyatli urun listenizi dogrudan gonderin. Ornek: Sut 1L - 1,29",
    )


async def _create_and_send_flyer(
    session: AsyncSession,
    state: TelegramConversationState,
    text: str,
    parsed: list[ParsedCampaignLine],
    client: TelegramClientProtocol,
) -> None:
    chat_id = _chat_id(state)
    membership = await _require_selected_mutation_membership(session, state)
    if membership is None:
        memberships = await _active_memberships(session, state.user_id)
        eligible = [item for item in memberships if item.role in MARKET_MUTATION_ROLES and market_allows_mutations(item.market)]
        if len(eligible) == 1:
            membership = eligible[0]
            state.selected_market_id = membership.market_id
        else:
            await client.send_message(chat_id, "Once /markets ile kampanyanin marketini secin.")
            return

    title = f"{membership.market.name} Firsatlari"[:255]
    state.pending_raw_text = text
    state.parsed_summary = _parsed_summary(parsed)
    state.pending_title = title
    await client.send_message(chat_id, "Listenizi aldim. Brosur hazirlaniyor...")
    payload = CampaignCreateFromTextRequest(
        title=title,
        raw_text=text,
        channel="telegram",
        source_type="text",
        currency=membership.market.currency,
        language=membership.market.language,
        generate_suggestions=True,
    )
    result = await campaign_service.create_campaign_from_text(session, payload, membership.market_id)
    state.campaign_id = result.campaign_id
    state.revision_count = 0
    state.last_edit_intent_json = None
    state.export_job_id = None
    state.state = TelegramState.GENERATING_EXPORTS.value
    await session.commit()

    await campaign_service.analyze_campaign_intelligence(session, result.campaign_id, membership.market_id)
    await campaign_service.apply_campaign_intelligence(session, result.campaign_id, membership.market_id)
    warning = ""
    if result.missing_count or result.low_confidence_count:
        warning = f" {result.missing_count + result.low_confidence_count} urun gorsel/eslesme uyarisiyla devam edildi."
    await _render_and_send_flyer(
        session,
        state,
        membership.market_id,
        client,
        acknowledgement=f"Brosurunuz hazir.{warning}",
    )


async def _apply_flyer_edit(
    session: AsyncSession,
    state: TelegramConversationState,
    intent: FlyerEditIntent,
    client: TelegramClientProtocol,
) -> None:
    chat_id = _chat_id(state)
    membership = await _require_selected_mutation_membership(session, state)
    if membership is None or state.campaign_id is None:
        await client.send_message(chat_id, "Duzenlenecek aktif bir brosur bulunamadi. Fiyatli urun listenizi gonderin.")
        return
    campaign = await campaign_service.get_campaign(session, state.campaign_id, membership.market_id)
    if campaign.frozen_at is not None or campaign.finalized_at is not None:
        await client.send_message(chat_id, "Bu brosur sonlandirilmis. Yeni bir fiyat listesiyle yeni brosur baslatin.")
        return

    item = None
    product_intents = {
        FlyerEditKind.CHANGE_HERO_PRODUCT,
        FlyerEditKind.REDUCE_PRODUCT_EMPHASIS,
        FlyerEditKind.REMOVE_PRODUCT,
    }
    if intent.product_reference and intent.kind in product_intents:
        item, ambiguous = _find_campaign_item(campaign.items, intent.product_reference)
        if ambiguous:
            await client.send_message(chat_id, "Birden fazla urun eslesti. Urun adini biraz daha acik yazin.")
            return
        if item is None:
            await client.send_message(chat_id, f"'{intent.product_reference}' aktif brosurde bulunamadi.")
            return

    rerun_intelligence = False
    acknowledgement = "Degisiklik uygulandi."
    config = dict(campaign.builder_config_json or {})
    if intent.kind == FlyerEditKind.CHANGE_HERO_PRODUCT and item is not None:
        for candidate in campaign.items:
            candidate.is_hero = candidate.id == item.id
        reduced = [value for value in config.get("reduced_emphasis_item_ids", []) if value != str(item.id)]
        config["reduced_emphasis_item_ids"] = reduced
        rerun_intelligence = True
        acknowledgement = f"{item.display_name or item.incoming_name} one cikarildi."
    elif intent.kind == FlyerEditKind.REDUCE_PRODUCT_EMPHASIS and item is not None:
        item.is_hero = False
        reduced = {str(value) for value in config.get("reduced_emphasis_item_ids", [])}
        reduced.add(str(item.id))
        config["reduced_emphasis_item_ids"] = sorted(reduced)
        rerun_intelligence = True
        acknowledgement = f"{item.display_name or item.incoming_name} vurgusu azaltildi."
    elif intent.kind == FlyerEditKind.REMOVE_PRODUCT and item is not None:
        item.match_status = "excluded"
        item.is_hero = False
        campaign_service.recalculate_campaign_counts(campaign)
        rerun_intelligence = True
        acknowledgement = f"{item.display_name or item.incoming_name} brosurden kaldirildi."
    elif intent.kind == FlyerEditKind.SET_TITLE and intent.value:
        campaign.title = intent.value
        config["headline"] = intent.value
        acknowledgement = "Baslik degistirildi."
    elif intent.kind == FlyerEditKind.ADJUST_VISUAL_DENSITY:
        if intent.value == "simpler":
            config.update(
                {
                    "visual_density": "simple",
                    "header_style": "minimal",
                    "card_style": "outlined",
                    "badge_style": "pill",
                    "show_additional_logos": False,
                    "show_payment_icons": False,
                    "show_footer_note": False,
                    "show_footer": False,
                }
            )
            acknowledgement = "Tasarim sadelestirildi."
        else:
            config.update(
                {
                    "visual_density": "expressive",
                    "header_style": "burst",
                    "card_style": "shadow",
                    "badge_style": "burst",
                    "headline_emphasis": "high",
                    "show_additional_logos": True,
                }
            )
            acknowledgement = "Tasarim daha dikkat cekici hale getirildi."
    elif intent.kind == FlyerEditKind.INCREASE_PRICE_PROMINENCE:
        config.update({"price_prominence": "high", "price_style": "panel", "show_old_price": True})
        acknowledgement = "Fiyat vurgusu artirildi."
    elif intent.kind == FlyerEditKind.REGROUP_PRODUCTS:
        grouped = _regroup_campaign_items(campaign.items, intent.product_reference)
        if intent.product_reference and grouped == 0:
            await client.send_message(chat_id, f"'{intent.product_reference}' aktif brosurde bulunamadi.")
            return
        config.pop("campaign_intelligence", None)
        config["smart_composition"] = False
        config["manual_grouping"] = intent.product_reference or "similar_products"
        acknowledgement = "Urunler birlikte gruplanacak sekilde siralandi."
    elif intent.kind == FlyerEditKind.CHANGE_FORMAT:
        if intent.value == "pdf":
            await _render_and_send_flyer(
                session,
                state,
                membership.market_id,
                client,
                acknowledgement="PDF hazir.",
                file_format="pdf",
            )
            return
        config["output_format"] = intent.value
        acknowledgement = "Yeni format uygulandi."
    elif intent.kind != FlyerEditKind.RERENDER_CURRENT_CAMPAIGN:
        await client.send_message(chat_id, "Bu degisiklik henuz desteklenmiyor.")
        return

    campaign.builder_config_json = config
    state.last_edit_intent_json = intent.as_dict()
    state.revision_count = (state.revision_count or 0) + 1
    state.export_job_id = None
    state.export_files_sent_at = None
    state.export_photo_sent_at = None
    state.export_document_sent_at = None
    await session.commit()
    if rerun_intelligence:
        await campaign_service.analyze_campaign_intelligence(session, campaign.id, membership.market_id)
        await campaign_service.apply_campaign_intelligence(session, campaign.id, membership.market_id)
    await _render_and_send_flyer(
        session,
        state,
        membership.market_id,
        client,
        acknowledgement=acknowledgement,
    )


async def _render_and_send_flyer(
    session: AsyncSession,
    state: TelegramConversationState,
    market_id: UUID,
    client: TelegramClientProtocol,
    *,
    acknowledgement: str,
    file_format: str = "png",
) -> None:
    if state.campaign_id is None:
        raise RuntimeError("Telegram flyer campaign is missing.")
    job_type = "preview" if state.revision_count == 0 else "regenerate_preview"
    if file_format == "pdf":
        job_type = "send_files"

    async def remember_export_job(created_job: ExportJob) -> None:
        created_job.requested_by_user_id = state.user_id
        state.export_job_id = created_job.id

    job = await campaign_service.create_export_job(
        session,
        state.campaign_id,
        ExportJobCreate(job_type=job_type, requested_formats=[file_format]),
        market_id,
        commit=False,
        after_flush=remember_export_job,
    )
    files = await _ready_export_files(session, job.result_file_ids or [])
    rendered = _find_file(files, file_format)
    if rendered is None:
        state.state = TelegramState.COMPLETED.value
        state.last_error = f"{file_format.upper()} preview was not produced."
        await client.send_message(_chat_id(state), "Brosur su anda olusturulamadi. Lutfen tekrar deneyin.")
        return
    try:
        if file_format == "pdf":
            await client.send_document(_chat_id(state), _safe_file_path(rendered), caption=acknowledgement)
            state.export_document_sent_at = utc_now()
        else:
            await client.send_message(_chat_id(state), acknowledgement)
            await client.send_photo(
                _chat_id(state),
                _safe_file_path(rendered),
                caption="Ilk taslak hazir. 'Daha sade yap' veya 'bir urunu buyut' diyebilirsiniz.",
            )
            state.export_photo_sent_at = utc_now()
    except TelegramClientError as exc:
        state.last_error = _safe_error(exc)
        await client.send_message(_chat_id(state), "Brosur Telegram'a gonderilemedi. Tekrar deneyebilirsiniz.")
        return
    state.state = TelegramState.COMPLETED.value
    state.export_files_sent_at = utc_now()
    state.last_error = None
    await session.flush()


def _find_campaign_item(items: list[CampaignItem], reference: str) -> tuple[CampaignItem | None, bool]:
    needle = normalize_for_match(reference)
    active = [item for item in items if item.match_status != "excluded"]
    exact = [item for item in active if needle in {normalize_for_match(item.incoming_name), normalize_for_match(item.display_name or "")}]
    matches = exact or [
        item
        for item in active
        if needle and needle in normalize_for_match(f"{item.display_name or ''} {item.incoming_name}")
    ]
    return (matches[0], False) if len(matches) == 1 else (None, len(matches) > 1)


def _regroup_campaign_items(items: list[CampaignItem], reference: str | None) -> int:
    needle = normalize_for_match(reference or "")
    active = [item for item in items if item.match_status != "excluded"]

    def key(item: CampaignItem) -> tuple[str, int]:
        haystack = normalize_for_match(f"{item.display_name or ''} {item.incoming_name}")
        if needle:
            return ("0" if needle in haystack else "1", item.sort_order)
        group = normalize_for_match(item.category_hint or "") or normalize_for_match(item.incoming_name).split(" ")[0]
        return (group, item.sort_order)

    for index, item in enumerate(sorted(active, key=key)):
        item.sort_order = index
    return sum(
        1
        for item in active
        if not needle or needle in normalize_for_match(f"{item.display_name or ''} {item.incoming_name}")
    )


async def _handle_callback(
    session: AsyncSession,
    state: TelegramConversationState,
    data: str,
    client: TelegramClientProtocol,
) -> None:
    chat_id = _chat_id(state)
    if len(data) > 64 or ":" not in data:
        await client.send_message(chat_id, "Gecersiz islem.")
        return
    namespace, value = data.split(":", 1)
    if namespace == "market":
        if state.state != TelegramState.AWAITING_MARKET.value:
            await client.send_message(chat_id, "Bu market secimi artik gecerli degil. /markets yazabilirsiniz.")
            return
        await _select_market(session, state, value, client)
    elif namespace == "export" and value == "confirm":
        await _generate_exports(session, state, client)
    elif namespace == "draft" and value == "restart":
        if state.state not in {TelegramState.AWAITING_CONFIRMATION.value, TelegramState.COMPLETED.value}:
            await client.send_message(chat_id, "Bu taslak islemi artik gecerli degil.")
            return
        state.pending_raw_text = None
        state.parsed_summary = None
        state.pending_title = None
        state.campaign_id = None
        state.export_job_id = None
        state.export_document_sent_at = None
        state.export_photo_sent_at = None
        state.export_files_sent_at = None
        state.export_delivery_started_at = None
        state.state = TelegramState.AWAITING_PRODUCT_LIST.value
        await client.send_message(chat_id, "Listeyi yeniden gonderin.")
    elif namespace == "flow" and value == "cancel":
        if state.state == TelegramState.COMPLETED.value:
            await client.send_message(chat_id, "Bu akis zaten tamamlandi.")
            return
        await _cancel(session, state, client)
    else:
        await client.send_message(chat_id, "Gecersiz islem.")


async def _start(session: AsyncSession, state: TelegramConversationState, client: TelegramClientProtocol) -> None:
    chat_id = _chat_id(state)
    memberships = await _active_memberships(session, state.user_id)
    if not memberships:
        state.state = TelegramState.IDLE.value
        await client.send_message(chat_id, "LeafletPilot hesabiniz bagli, ancak aktif market erisiminiz yok.")
        return
    if len(memberships) == 1:
        state.selected_market_id = memberships[0].market_id
        state.state = TelegramState.IDLE.value
        await client.send_message(chat_id, f"Hos geldiniz. Secili market: {memberships[0].market.name}")
        return
    state.state = TelegramState.AWAITING_MARKET.value
    await client.send_message(chat_id, "Hos geldiniz. Market secin:", reply_markup=_market_keyboard(memberships))


async def _show_markets(session: AsyncSession, state: TelegramConversationState, client: TelegramClientProtocol) -> None:
    memberships = await _active_memberships(session, state.user_id)
    if not memberships:
        await client.send_message(_chat_id(state), "Aktif market erisiminiz yok.")
        return
    state.state = TelegramState.AWAITING_MARKET.value
    await client.send_message(_chat_id(state), "Market secin:", reply_markup=_market_keyboard(memberships))


async def _select_market(
    session: AsyncSession,
    state: TelegramConversationState,
    raw_market_id: str,
    client: TelegramClientProtocol,
) -> None:
    try:
        market_id = UUID(raw_market_id)
    except ValueError:
        await client.send_message(_chat_id(state), "Gecersiz market secimi.")
        return
    membership = await _membership(session, state.user_id, market_id)
    if membership is None:
        await client.send_message(_chat_id(state), "Bu market icin yetkiniz yok.")
        return
    state.selected_market_id = market_id
    state.state = TelegramState.IDLE.value
    await client.send_message(_chat_id(state), f"Secili market: {membership.market.name}")


async def _generate_exports(
    session: AsyncSession,
    state: TelegramConversationState,
    client: TelegramClientProtocol,
) -> None:
    chat_id = _chat_id(state)
    if state.state == TelegramState.COMPLETED.value:
        await client.send_message(chat_id, "Bu akis zaten tamamlandi; dosyalar tekrar gonderilmeyecek.")
        return
    if state.state not in {TelegramState.AWAITING_CONFIRMATION.value, TelegramState.GENERATING_EXPORTS.value}:
        await client.send_message(chat_id, "Bu export onayi artik gecerli degil.")
        return
    membership = await _selected_membership(session, state)
    if membership is None or membership.role not in MARKET_MUTATION_ROLES:
        await client.send_message(chat_id, "Bu market icin export olusturma yetkiniz yok.")
        return
    if not market_allows_mutations(membership.market):
        await client.send_message(chat_id, inactive_market_message())
        return
    if state.campaign_id is None:
        await client.send_message(chat_id, "Export icin kampanya bulunamadi.")
        return
    campaign = await session.get(Campaign, state.campaign_id)
    if campaign is None or campaign.market_id != membership.market_id:
        await client.send_message(chat_id, "Export icin kampanya bu markete ait degil.")
        return
    job = await _get_reusable_export_job(session, state, membership.market_id)
    if job is None:
        if state.export_job_id is not None:
            await client.send_message(chat_id, "Bu export onayi artik gecerli degil.")
            return
        state.state = TelegramState.GENERATING_EXPORTS.value
        state.export_document_sent_at = None
        state.export_photo_sent_at = None
        state.export_files_sent_at = None
        state.export_delivery_started_at = utc_now()
        await client.send_message(chat_id, "PDF ve PNG olusturuluyor...")

        async def remember_export_job(created_job: ExportJob) -> None:
            created_job.requested_by_user_id = state.user_id
            state.export_job_id = created_job.id

        job = await campaign_service.create_export_job(
            session,
            state.campaign_id,
            ExportJobCreate(job_type="final_export", requested_formats=["pdf", "png"]),
            membership.market_id,
            commit=False,
            after_flush=remember_export_job,
        )
    elif state.export_files_sent_at is not None:
        state.state = TelegramState.COMPLETED.value
        await client.send_message(chat_id, "Bu akis zaten tamamlandi; dosyalar tekrar gonderilmeyecek.")
        return
    else:
        state.state = TelegramState.GENERATING_EXPORTS.value
        state.export_delivery_started_at = utc_now()
        await client.send_message(chat_id, "Mevcut PDF ve PNG yeniden gonderiliyor...")
    files = await _ready_export_files(session, job.result_file_ids or [])
    pdf = _find_file(files, "pdf")
    png = _find_file(files, "png")
    if pdf is None or png is None:
        state.state = TelegramState.AWAITING_CONFIRMATION.value
        state.last_error = "Export did not produce both PDF and PNG."
        await client.send_message(chat_id, "PDF ve PNG hazirlanamadi. Daha sonra tekrar deneyin.")
        return
    try:
        if state.export_document_sent_at is None:
            await client.send_document(chat_id, _safe_file_path(pdf), caption="LeafletPilot PDF")
            state.export_document_sent_at = utc_now()
        if state.export_photo_sent_at is None:
            await client.send_photo(chat_id, _safe_file_path(png), caption="LeafletPilot PNG")
            state.export_photo_sent_at = utc_now()
    except TelegramClientError as exc:
        state.state = TelegramState.AWAITING_CONFIRMATION.value
        state.last_error = _safe_error(exc)
        await client.send_message(chat_id, "Dosyalar Telegram'a gonderilemedi. Tekrar deneyebilirsiniz.")
        return
    state.state = TelegramState.COMPLETED.value
    state.export_files_sent_at = utc_now()
    await client.send_message(chat_id, "PDF ve PNG gonderildi.")


async def _get_reusable_export_job(
    session: AsyncSession,
    state: TelegramConversationState,
    market_id: UUID,
) -> ExportJob | None:
    if state.export_job_id is None or state.campaign_id is None:
        return None
    job = await session.get(ExportJob, state.export_job_id)
    if job is None:
        return None
    if job.market_id != market_id or job.campaign_id != state.campaign_id:
        return None
    if job.status != "completed" or not job.result_file_ids:
        return None
    return job


async def _cancel(
    session: AsyncSession,
    state: TelegramConversationState,
    client: TelegramClientProtocol,
) -> None:
    if state.campaign_id is not None and state.selected_market_id is not None:
        try:
            await campaign_service.cancel_campaign(session, state.campaign_id, state.selected_market_id, commit=False)
        except Exception:
            logger.exception("Telegram campaign cancellation failed. campaign_id=%s", state.campaign_id)
    _reset_draft(state)
    state.state = TelegramState.IDLE.value
    await client.send_message(_chat_id(state), "Akis iptal edildi.")


async def _get_active_account(session: AsyncSession, telegram_user_id: int) -> TelegramAccount | None:
    return await session.scalar(
        select(TelegramAccount)
        .options(selectinload(TelegramAccount.user))
        .where(TelegramAccount.telegram_user_id == telegram_user_id, TelegramAccount.is_active.is_(True))
    )


async def _get_or_create_locked_state(
    session: AsyncSession,
    account: TelegramAccount,
    chat_id: int,
) -> TelegramConversationState:
    state = await session.scalar(
        select(TelegramConversationState)
        .where(TelegramConversationState.telegram_user_id == account.telegram_user_id)
        .with_for_update()
    )
    if state is None:
        state = TelegramConversationState(
            telegram_account_id=account.id,
            user_id=account.user_id,
            telegram_user_id=account.telegram_user_id,
            chat_id=chat_id,
            state=TelegramState.IDLE.value,
        )
        session.add(state)
        await session.flush()
    else:
        state.chat_id = chat_id
        state.telegram_account_id = account.id
        state.user_id = account.user_id
    return state


async def _active_memberships(session: AsyncSession, user_id: UUID) -> list[MarketUser]:
    result = await session.scalars(
        select(MarketUser)
        .options(selectinload(MarketUser.market))
        .where(MarketUser.user_id == user_id, MarketUser.is_active.is_(True))
        .order_by(MarketUser.created_at.asc())
    )
    return [membership for membership in result.all() if membership.market and membership.market.is_active]


async def _membership(session: AsyncSession, user_id: UUID, market_id: UUID) -> MarketUser | None:
    membership = await session.scalar(
        select(MarketUser)
        .options(selectinload(MarketUser.market))
        .where(
            MarketUser.user_id == user_id,
            MarketUser.market_id == market_id,
            MarketUser.is_active.is_(True),
        )
    )
    if membership is None or membership.market is None:
        return None
    return membership


async def _require_selected_mutation_membership(
    session: AsyncSession,
    state: TelegramConversationState,
) -> MarketUser | None:
    membership = await _selected_membership(session, state)
    if membership is None or membership.role not in MARKET_MUTATION_ROLES or not market_allows_mutations(membership.market):
        return None
    return membership


async def _selected_membership(
    session: AsyncSession,
    state: TelegramConversationState,
) -> MarketUser | None:
    if state.selected_market_id is None:
        return None
    return await _membership(session, state.user_id, state.selected_market_id)


async def _status_text(session: AsyncSession, state: TelegramConversationState) -> str:
    market_name = "secili degil"
    if state.selected_market_id is not None:
        membership = await _membership(session, state.user_id, state.selected_market_id)
        if membership is not None:
            market_name = membership.market.name
        else:
            state.selected_market_id = None
    lines = [f"Market: {market_name}", f"Durum: {state.state}"]
    if state.pending_title:
        lines.append(f"Kampanya: {state.pending_title}")
    if state.campaign_id:
        lines.append(f"Kampanya ID: {state.campaign_id}")
    if state.export_job_id:
        lines.append(f"Export ID: {state.export_job_id}")
    if state.campaign_id:
        lines.append(f"Revizyon: {state.revision_count or 0}")
    return "\n".join(lines)


async def _ready_export_files(session: AsyncSession, ids: list[str]) -> list[CampaignFile]:
    file_ids = []
    for value in ids:
        try:
            file_ids.append(UUID(value))
        except ValueError:
            continue
    if not file_ids:
        return []
    result = await session.scalars(
        select(CampaignFile).where(CampaignFile.id.in_(file_ids), CampaignFile.status == "ready")
    )
    return list(result.all())


def _find_file(files: list[CampaignFile], file_format: str) -> CampaignFile | None:
    return next((file for file in files if file.format == file_format and file.storage_key), None)


def _safe_file_path(file: CampaignFile) -> Path:
    if not file.storage_key:
        raise TelegramClientError("Generated file has no storage key.")
    path = storage_path_for_key(file.storage_key)
    if not path.is_file() or path.stat().st_size <= 0:
        raise TelegramClientError("Generated file is missing or empty.")
    return path


def _parsed_summary(items: list[ParsedCampaignLine]) -> dict[str, int | list[str]]:
    return {
        "parsed_count": len(items),
        "warning_count": sum(len(item.parsed_payload.get("warnings", [])) for item in items),
        "preview_names": [item.display_name for item in items[:5]],
    }


def _summary_text(items: list[ParsedCampaignLine]) -> str:
    warning_count = sum(len(item.parsed_payload.get("warnings", [])) for item in items)
    lines = [f"Urun sayisi: {len(items)}", f"Uyari sayisi: {warning_count}", "Onizleme:"]
    for item in items[:5]:
        price = f" - {item.price} {item.currency}" if item.price is not None else ""
        lines.append(f"- {item.display_name[:80]}{price}")
    if len(items) > 5:
        lines.append(f"... ve {len(items) - 5} satir daha")
    return "\n".join(lines)


def _market_keyboard(memberships: list[MarketUser]) -> InlineKeyboardMarkup:
    return {
        "inline_keyboard": [
            [{"text": membership.market.name[:40], "callback_data": f"market:{membership.market_id}"}]
            for membership in memberships
        ]
    }


def _confirmation_keyboard() -> InlineKeyboardMarkup:
    return {
        "inline_keyboard": [
            [{"text": "Generate PDF + PNG", "callback_data": "export:confirm"}],
            [{"text": "Send list again", "callback_data": "draft:restart"}],
            [{"text": "Cancel", "callback_data": "flow:cancel"}],
        ]
    }


def _reset_draft(state: TelegramConversationState) -> None:
    state.pending_raw_text = None
    state.parsed_summary = None
    state.pending_title = None
    state.campaign_id = None
    state.export_job_id = None
    state.export_document_sent_at = None
    state.export_photo_sent_at = None
    state.export_files_sent_at = None
    state.export_delivery_started_at = None
    state.revision_count = 0
    state.last_edit_intent_json = None
    state.last_error = None


def _chat_id(state: TelegramConversationState) -> int:
    if state.chat_id is None:
        raise RuntimeError("Telegram chat ID is missing.")
    return state.chat_id


def _safe_error(exc: Exception) -> str:
    return (str(exc) or type(exc).__name__)[:1000]
