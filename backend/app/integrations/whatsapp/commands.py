"""Command router for verified WhatsApp senders.

Reached only after `app/integrations/whatsapp/service.py` has proven *who*
the sender is. This module decides *what they may do*, and it decides it from
current database state on every single message:

    verified identity -> LeafletPilot user -> active memberships -> active market

`WhatsAppSession.active_market_id` is a remembered *choice*, never an
authorization. If the membership behind it disappeared, the market was
suspended or the user was deactivated, the choice is discarded and the user is
asked to pick again — so removing someone from a market takes effect on their
next message with no cache to invalidate.

Brochure generation calls the same channel-independent services the panel and
the Telegram bot already use (`app.services.campaign`,
`app.services.templates`, `app.services.product_image_resolution`); nothing
about the Telegram integration is imported, referenced or altered.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.lifecycle import inactive_market_message, market_allows_mutations
from app.core.roles import MARKET_MUTATION_ROLES
from app.integrations.whatsapp.client import EvolutionClientProtocol
from app.models import (
    ActivityLog,
    Campaign,
    CampaignFile,
    ExportJob,
    MarketUser,
    UserWhatsAppIdentity,
    WhatsAppSession,
)
from app.models.base import utc_now
from app.schemas.campaign import RAW_TEXT_MAX_LENGTH, CampaignCreateFromTextRequest
from app.schemas.export import ExportJobCreate
from app.services import campaign as campaign_service
from app.services import templates as template_service
from app.services.campaign_parser import ParsedCampaignLine, parse_campaign_text
from app.services.phone import mask_phone
from app.services.product_image_resolution import resolve_campaign_product_images
from app.services.rendering import storage_path_for_key

logger = logging.getLogger(__name__)

# A confirmation that has been sitting unanswered this long is stale; the user
# is asked to start again rather than having an old "ONAYLA" fire against
# whatever market they happen to be in now.
PENDING_ACTION_TTL = timedelta(minutes=15)

# Matches the automated supermarket presets the flyer pipeline supports.
MAX_FLYER_ITEMS = 16

MAX_MARKET_CHOICES = 20

HELP_TEXT = (
    "LeafletPilot WhatsApp komutları:\n"
    "• Ürün listenizi doğrudan gönderin (örn. \"Süt 1L - 1,29\")\n"
    "• *market* — yetkili marketlerinizi listeler\n"
    "• *market değiştir* — aktif marketi değiştirir\n"
    "• *durum* — mevcut durumu gösterir\n"
    "• *iptal* — mevcut akışı iptal eder\n"
    "• *yardım* — bu mesajı gösterir\n\n"
    "Broşür hazır olduğunda PDF ve PNG göndermek için *ONAYLA* yazmanız istenir."
)

NO_MARKET_ACCESS = (
    "LeafletPilot hesabınız doğrulandı, ancak şu anda aktif bir market erişiminiz yok. "
    "Lütfen market yöneticinizle görüşün."
)
NO_MUTATION_ROLE = "Kampanya oluşturmak için market yöneticisi veya personel rolü gerekir."
LIST_HINT = (
    "Fiyatlı ürün listenizi doğrudan gönderebilirsiniz.\n"
    "Örnek:\nSüt 1L - 1,29\nCoca Cola 2L - 1,59\n\n"
    "Komutlar için *yardım* yazın."
)

_HELP_WORDS = {"yardim", "yardım", "help", "/help", "?"}
_MARKET_WORDS = {"market", "marketler", "/markets", "market degistir", "market değiştir", "marketi degistir", "marketi değiştir"}
_STATUS_WORDS = {"durum", "status", "/status"}
# "ıptal" is the result of normalising an ASCII-capital "IPTAL": Turkish
# lowercasing maps I -> ı, and plenty of people type the ASCII I rather than
# the correct "İPTAL". Both spellings must cancel.
_CANCEL_WORDS = {"iptal", "ıptal", "vazgec", "vazgeç", "cancel", "/cancel"}
_CONFIRM_WORDS = {"onayla", "onay", "evet", "tamam"}
_NEW_WORDS = {"yeni", "yeni kampanya", "/new"}


async def send_welcome(
    session: AsyncSession,
    identity: UserWhatsAppIdentity,
    client: EvolutionClientProtocol,
) -> None:
    """Greets a freshly verified sender and establishes their market context."""
    from app.integrations.whatsapp import service as inbound

    session_row = await _get_or_create_locked_session(session, identity)
    memberships = await _active_memberships(session, identity.user_id)
    if not memberships:
        await inbound.send_text(session, client, identity.phone_e164, NO_MARKET_ACCESS)
        return
    if len(memberships) == 1:
        session_row.active_market_id = memberships[0].market_id
        session_row.state = "idle"
        await inbound.send_text(
            session,
            client,
            identity.phone_e164,
            f"Hoş geldiniz. Aktif market: {memberships[0].market.name}\n\n{LIST_HINT}",
        )
        return
    await _prompt_market_choice(session, session_row, identity, memberships, client)


async def handle_message(
    session: AsyncSession,
    identity: UserWhatsAppIdentity,
    text: str,
    client: EvolutionClientProtocol,
) -> str:
    from app.integrations.whatsapp import service as inbound

    session_row = await _get_or_create_locked_session(session, identity)
    session_row.last_message_at = utc_now()

    # Authorization is recomputed here, from the database, on every message.
    memberships = await _active_memberships(session, identity.user_id)
    if not memberships:
        _clear_market_context(session_row)
        await inbound.send_text(session, client, identity.phone_e164, NO_MARKET_ACCESS)
        return "no_market_access"

    command = _normalize_command(text)

    if command in _HELP_WORDS:
        await inbound.send_text(session, client, identity.phone_e164, HELP_TEXT)
        return "help"

    if command in _MARKET_WORDS:
        await _prompt_market_choice(session, session_row, identity, memberships, client)
        return "market_prompt"

    if session_row.state == "awaiting_market" and command.isdigit():
        return await _select_market(session, session_row, identity, memberships, command, client)

    if command in _CANCEL_WORDS:
        return await _cancel(session, session_row, identity, client)

    if command in _CONFIRM_WORDS and session_row.pending_action:
        return await _execute_pending_action(session, session_row, identity, memberships, client)

    if command in _CONFIRM_WORDS:
        await inbound.send_text(
            session, client, identity.phone_e164, "Onay bekleyen bir işlem yok."
        )
        return "no_pending_action"

    membership = await _resolve_active_market(session, session_row, memberships)
    if membership is None:
        await _prompt_market_choice(session, session_row, identity, memberships, client)
        return "market_required"

    if command in _STATUS_WORDS:
        await inbound.send_text(session, client, identity.phone_e164, _status_text(session_row, membership))
        return "status"

    if command in _NEW_WORDS:
        _reset_draft(session_row)
        session_row.state = "awaiting_product_list"
        await inbound.send_text(session, client, identity.phone_e164, LIST_HINT)
        return "new"

    return await _handle_product_list(session, session_row, identity, membership, text, client)


# --- market context -------------------------------------------------------


async def _active_memberships(session: AsyncSession, user_id: UUID) -> list[MarketUser]:
    """Every membership that is authoritative *right now*.

    Filters on `MarketUser.is_active` and the market's own active/lifecycle
    state, so a removed member, a deactivated membership, a deactivated market
    or an archived/suspended market all disappear from the list immediately.
    """
    result = await session.scalars(
        select(MarketUser)
        .options(selectinload(MarketUser.market))
        .where(MarketUser.user_id == user_id, MarketUser.is_active.is_(True))
        .order_by(MarketUser.created_at.asc())
    )
    return [
        membership
        for membership in result.all()
        if membership.market is not None
        and membership.market.is_active
        and (membership.market.lifecycle_status or "active") not in {"archived", "suspended"}
    ]


async def _resolve_active_market(
    session: AsyncSession,
    session_row: WhatsAppSession,
    memberships: list[MarketUser],
) -> MarketUser | None:
    """Returns the market to act on, auto-resolving the single-market case."""
    if session_row.active_market_id is not None:
        for membership in memberships:
            if membership.market_id == session_row.active_market_id:
                return membership
        # The remembered choice is no longer authorized. Drop it (and any
        # confirmation bound to it) rather than falling through to another
        # market.
        _clear_market_context(session_row)
    if len(memberships) == 1:
        session_row.active_market_id = memberships[0].market_id
        session_row.state = "idle" if session_row.state == "awaiting_market" else session_row.state
        return memberships[0]
    return None


async def _prompt_market_choice(
    session: AsyncSession,
    session_row: WhatsAppSession,
    identity: UserWhatsAppIdentity,
    memberships: list[MarketUser],
    client: EvolutionClientProtocol,
) -> None:
    from app.integrations.whatsapp import service as inbound

    if len(memberships) == 1:
        session_row.active_market_id = memberships[0].market_id
        session_row.state = "idle"
        await inbound.send_text(
            session,
            client,
            identity.phone_e164,
            f"Aktif market: {memberships[0].market.name}",
        )
        return

    visible = memberships[:MAX_MARKET_CHOICES]
    # The mapping is stored server-side so the reply "2" is resolved against
    # the list we actually offered, not against an index the client controls.
    session_row.market_choice_json = {
        str(index + 1): str(membership.market_id) for index, membership in enumerate(visible)
    }
    session_row.state = "awaiting_market"
    lines = ["Birden fazla markete erişiminiz var.", ""]
    lines.extend(f"{index + 1}. {membership.market.name}" for index, membership in enumerate(visible))
    lines.append("")
    lines.append("İşlem yapmak istediğiniz marketin numarasını gönderin.")
    await inbound.send_text(session, client, identity.phone_e164, "\n".join(lines))


async def _select_market(
    session: AsyncSession,
    session_row: WhatsAppSession,
    identity: UserWhatsAppIdentity,
    memberships: list[MarketUser],
    choice: str,
    client: EvolutionClientProtocol,
) -> str:
    from app.integrations.whatsapp import service as inbound

    raw_market_id = (session_row.market_choice_json or {}).get(choice)
    membership = None
    if raw_market_id:
        try:
            target_id = UUID(raw_market_id)
        except ValueError:
            target_id = None
        if target_id is not None:
            # Re-checked against the memberships loaded this request: a market
            # the user lost access to between the prompt and the reply is not
            # selectable.
            membership = next((item for item in memberships if item.market_id == target_id), None)
    if membership is None:
        await inbound.send_text(
            session, client, identity.phone_e164, "Geçersiz seçim. Lütfen listedeki numaralardan birini gönderin."
        )
        return "market_invalid_choice"

    previous_market_id = session_row.active_market_id
    session_row.active_market_id = membership.market_id
    session_row.state = "idle"
    session_row.market_choice_json = None
    _clear_pending_action(session_row)
    session.add(
        ActivityLog(
            market_id=membership.market_id,
            user_id=identity.user_id,
            entity_type="whatsapp_session",
            entity_id=session_row.id,
            action="WHATSAPP_ACTIVE_MARKET_CHANGED",
            description="whatsapp active market changed",
            metadata_={
                "previous_market_id": str(previous_market_id) if previous_market_id else "",
                "market_id": str(membership.market_id),
                "sender_phone_masked": mask_phone(identity.phone_e164),
            },
        )
    )
    await inbound.send_text(
        session,
        client,
        identity.phone_e164,
        f"Aktif market: {membership.market.name}\n\n{LIST_HINT}",
    )
    return "market_selected"


# --- brochure flow --------------------------------------------------------


async def _handle_product_list(
    session: AsyncSession,
    session_row: WhatsAppSession,
    identity: UserWhatsAppIdentity,
    membership: MarketUser,
    text: str,
    client: EvolutionClientProtocol,
) -> str:
    from app.integrations.whatsapp import service as inbound

    phone = identity.phone_e164
    if len(text) > RAW_TEXT_MAX_LENGTH:
        await inbound.send_text(session, client, phone, "Liste çok uzun. Lütfen daha kısa bir liste gönderin.")
        return "list_too_long"

    parsed = parse_campaign_text(text)
    usable = [item for item in parsed if item.incoming_name.strip()]
    priced = [item for item in usable if item.price is not None]
    if not priced:
        await inbound.send_text(session, client, phone, LIST_HINT)
        return "not_a_product_list"

    if membership.role not in MARKET_MUTATION_ROLES:
        await inbound.send_text(session, client, phone, NO_MUTATION_ROLE)
        return "forbidden_role"
    if not market_allows_mutations(membership.market):
        await inbound.send_text(session, client, phone, inactive_market_message())
        return "market_inactive"
    if len(usable) > MAX_FLYER_ITEMS:
        await inbound.send_text(
            session,
            client,
            phone,
            f"Tek broşürde en fazla {MAX_FLYER_ITEMS} ürün kullanın; listeyi bölerek tekrar gönderin.",
        )
        return "too_many_items"

    await inbound.send_text(session, client, phone, "Listenizi aldım. Broşür hazırlanıyor...")

    title = f"{membership.market.name} Fırsatları"[:255]
    template = await template_service.resolve_automatic_supermarket_template(
        session, membership.market_id, len(usable)
    )
    payload = CampaignCreateFromTextRequest(
        title=title,
        raw_text=text,
        channel="whatsapp",
        source_type="text",
        template_id=template.id,
        currency=membership.market.currency,
        language=membership.market.language,
        generate_suggestions=True,
    )
    try:
        result = await campaign_service.create_campaign_from_text(session, payload, membership.market_id)
    except HTTPException as exc:
        await inbound.send_text(session, client, phone, _campaign_error_message(exc))
        return "campaign_error"

    _reset_draft(session_row)
    session_row.pending_raw_text = text
    session_row.parsed_summary = _parsed_summary(parsed)
    session_row.pending_title = title
    session_row.campaign_id = result.campaign_id
    session_row.state = "generating_exports"
    await session.commit()

    logger.info(
        "WhatsApp campaign created. campaign_id=%s market_id=%s user_id=%s product_count=%s matched_count=%s",
        result.campaign_id,
        membership.market_id,
        identity.user_id,
        result.product_count,
        result.matched_count,
    )

    image_resolution = await resolve_campaign_product_images(session, membership.market_id, result.campaign_id)
    await campaign_service.analyze_campaign_intelligence(session, result.campaign_id, membership.market_id)
    await campaign_service.apply_campaign_intelligence(session, result.campaign_id, membership.market_id)

    warning = ""
    if image_resolution.unresolved_names:
        visible_names = ", ".join(image_resolution.unresolved_names[:3])
        extra = len(image_resolution.unresolved_names) - 3
        suffix = f" ve {extra} ürün daha" if extra > 0 else ""
        warning = (
            f"\n\nGüvenilir görsel bulunamadı: {visible_names}{suffix}. "
            "LP yedeği kullanıldı; katalogdan görsel yükleyebilirsiniz."
        )

    preview = await _render_export(
        session, session_row, membership.market_id, identity, job_type="preview", formats=["png"]
    )
    if preview is None:
        session_row.state = "completed"
        await inbound.send_text(session, client, phone, "Broşür şu anda oluşturulamadı. Lütfen tekrar deneyin.")
        return "preview_failed"

    await inbound.send_media(
        session,
        client,
        phone,
        preview,
        media_type="image",
        mime_type="image/png",
        file_name="leafletpilot-onizleme.png",
        caption=f"Broşür önizlemeniz hazır.{warning}",
    )

    # Producing and sending the final PDF/PNG is the externally-visible step,
    # so it waits for an explicit confirmation bound to this user, this market
    # and this campaign.
    session_row.state = "awaiting_confirmation"
    session_row.pending_action = "final_export"
    session_row.pending_action_market_id = membership.market_id
    session_row.pending_action_payload = {"campaign_id": str(result.campaign_id)}
    session_row.pending_action_expires_at = utc_now() + PENDING_ACTION_TTL
    await inbound.send_text(
        session,
        client,
        phone,
        f"{membership.market.name} için PDF ve PNG oluşturulsun mu?\n\n"
        "Onaylamak için *ONAYLA*, vazgeçmek için *İPTAL* yazın.",
    )
    return "preview_sent"


async def _execute_pending_action(
    session: AsyncSession,
    session_row: WhatsAppSession,
    identity: UserWhatsAppIdentity,
    memberships: list[MarketUser],
    client: EvolutionClientProtocol,
) -> str:
    from app.integrations.whatsapp import service as inbound

    phone = identity.phone_e164
    action = session_row.pending_action
    market_id = session_row.pending_action_market_id
    expires_at = session_row.pending_action_expires_at
    payload = session_row.pending_action_payload or {}
    _clear_pending_action(session_row)

    if expires_at is None or expires_at <= utc_now():
        await inbound.send_text(
            session, client, phone, "Bu onayın süresi doldu. Lütfen listenizi tekrar gönderin."
        )
        return "confirmation_expired"

    # The confirmation is bound to the market it was issued for. If the user
    # switched markets or lost access in the meantime it cannot execute.
    membership = next((item for item in memberships if item.market_id == market_id), None)
    if membership is None:
        await inbound.send_text(
            session, client, phone, "Bu onay artık geçerli değil çünkü market erişiminiz değişti."
        )
        return "confirmation_market_lost"
    if membership.role not in MARKET_MUTATION_ROLES:
        await inbound.send_text(session, client, phone, NO_MUTATION_ROLE)
        return "confirmation_forbidden"
    if not market_allows_mutations(membership.market):
        await inbound.send_text(session, client, phone, inactive_market_message())
        return "confirmation_market_inactive"
    if action != "final_export":
        await inbound.send_text(session, client, phone, "Bu işlem artık desteklenmiyor.")
        return "confirmation_unknown_action"

    raw_campaign_id = payload.get("campaign_id")
    try:
        campaign_id = UUID(str(raw_campaign_id))
    except (TypeError, ValueError):
        await inbound.send_text(session, client, phone, "Onaylanacak kampanya bulunamadı.")
        return "confirmation_no_campaign"

    campaign = await session.get(Campaign, campaign_id)
    if campaign is None or campaign.market_id != membership.market_id:
        await inbound.send_text(session, client, phone, "Onaylanacak kampanya bu markete ait değil.")
        return "confirmation_wrong_market"

    if session_row.export_files_sent_at is not None and session_row.campaign_id == campaign_id:
        await inbound.send_text(session, client, phone, "Bu akış zaten tamamlandı; dosyalar tekrar gönderilmeyecek.")
        return "confirmation_already_sent"

    session_row.state = "generating_exports"
    await inbound.send_text(session, client, phone, "PDF ve PNG oluşturuluyor...")

    files = await _render_export_files(
        session, session_row, membership.market_id, identity, campaign_id,
        job_type="final_export", formats=["pdf", "png"],
    )
    if files is None:
        session_row.state = "awaiting_confirmation"
        session_row.pending_action = "final_export"
        session_row.pending_action_market_id = membership.market_id
        session_row.pending_action_payload = {"campaign_id": str(campaign_id)}
        session_row.pending_action_expires_at = utc_now() + PENDING_ACTION_TTL
        await inbound.send_text(session, client, phone, "PDF ve PNG hazırlanamadı. Daha sonra tekrar deneyin.")
        return "final_export_failed"

    pdf_path, png_path = files
    if pdf_path is not None:
        await inbound.send_media(
            session, client, phone, pdf_path,
            media_type="document", mime_type="application/pdf",
            file_name="leafletpilot-brosur.pdf", caption="LeafletPilot PDF",
        )
        session_row.export_document_sent_at = utc_now()
    if png_path is not None:
        await inbound.send_media(
            session, client, phone, png_path,
            media_type="image", mime_type="image/png",
            file_name="leafletpilot-brosur.png", caption="LeafletPilot PNG",
        )
        session_row.export_image_sent_at = utc_now()

    session_row.export_files_sent_at = utc_now()
    session_row.state = "completed"
    await inbound.send_text(session, client, phone, "PDF ve PNG gönderildi.")
    return "final_export_sent"


async def _render_export(
    session: AsyncSession,
    session_row: WhatsAppSession,
    market_id: UUID,
    identity: UserWhatsAppIdentity,
    *,
    job_type: str,
    formats: list[str],
) -> Path | None:
    if session_row.campaign_id is None:
        return None
    result = await _render_export_files(
        session, session_row, market_id, identity, session_row.campaign_id,
        job_type=job_type, formats=formats,
    )
    if result is None:
        return None
    pdf_path, png_path = result
    return png_path or pdf_path


async def _render_export_files(
    session: AsyncSession,
    session_row: WhatsAppSession,
    market_id: UUID,
    identity: UserWhatsAppIdentity,
    campaign_id: UUID,
    *,
    job_type: str,
    formats: list[str],
) -> tuple[Path | None, Path | None] | None:
    async def remember_export_job(created_job: ExportJob) -> None:
        created_job.requested_by_user_id = identity.user_id
        session_row.export_job_id = created_job.id

    try:
        job = await campaign_service.create_export_job(
            session,
            campaign_id,
            ExportJobCreate(job_type=job_type, requested_formats=formats),
            market_id,
            commit=False,
            after_flush=remember_export_job,
        )
    except HTTPException as exc:
        session_row.last_error = _safe_error(exc)
        logger.warning("WhatsApp export job failed. campaign_id=%s detail=%s", campaign_id, exc.status_code)
        return None

    files = await _ready_export_files(session, job.result_file_ids or [])
    pdf_path = _safe_path(_find_file(files, "pdf")) if "pdf" in formats else None
    png_path = _safe_path(_find_file(files, "png")) if "png" in formats else None
    if all(path is None for path in (pdf_path, png_path)):
        session_row.last_error = "Export produced no usable file."
        return None
    if "pdf" in formats and "png" in formats and (pdf_path is None or png_path is None):
        session_row.last_error = "Export did not produce both PDF and PNG."
        return None
    return pdf_path, png_path


async def _ready_export_files(session: AsyncSession, ids: list[str]) -> list[CampaignFile]:
    file_ids: list[UUID] = []
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


def _safe_path(file: CampaignFile | None) -> Path | None:
    if file is None or not file.storage_key:
        return None
    try:
        path = storage_path_for_key(file.storage_key)
    except ValueError:
        logger.warning("WhatsApp export file had an unsafe storage key. file_id=%s", file.id)
        return None
    if not path.is_file() or path.stat().st_size <= 0:
        return None
    return path


# --- session bookkeeping --------------------------------------------------


async def _get_or_create_locked_session(
    session: AsyncSession,
    identity: UserWhatsAppIdentity,
) -> WhatsAppSession:
    """Row-locks the sender's session so two concurrent webhook deliveries
    cannot interleave state transitions (two market changes, two confirms)."""
    session_row = await session.scalar(
        select(WhatsAppSession)
        .where(WhatsAppSession.identity_id == identity.id)
        .with_for_update()
    )
    if session_row is not None:
        session_row.user_id = identity.user_id
        return session_row
    session_row = WhatsAppSession(
        identity_id=identity.id,
        user_id=identity.user_id,
        state="idle",
    )
    session.add(session_row)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        session_row = await session.scalar(
            select(WhatsAppSession)
            .where(WhatsAppSession.identity_id == identity.id)
            .with_for_update()
        )
        if session_row is None:
            raise
    return session_row


async def _cancel(
    session: AsyncSession,
    session_row: WhatsAppSession,
    identity: UserWhatsAppIdentity,
    client: EvolutionClientProtocol,
) -> str:
    from app.integrations.whatsapp import service as inbound

    if session_row.campaign_id is not None and session_row.active_market_id is not None:
        try:
            await campaign_service.cancel_campaign(
                session, session_row.campaign_id, session_row.active_market_id, commit=False
            )
        except Exception:
            logger.exception("WhatsApp campaign cancellation failed. campaign_id=%s", session_row.campaign_id)
    _reset_draft(session_row)
    _clear_pending_action(session_row)
    session_row.state = "idle"
    await inbound.send_text(session, client, identity.phone_e164, "Akış iptal edildi.")
    return "cancelled"


def _status_text(session_row: WhatsAppSession, membership: MarketUser) -> str:
    lines = [f"Market: {membership.market.name}", f"Durum: {session_row.state}"]
    if session_row.pending_title:
        lines.append(f"Kampanya: {session_row.pending_title}")
    if session_row.pending_action:
        lines.append("Onay bekleyen işlem: PDF/PNG gönderimi (*ONAYLA* / *İPTAL*)")
    return "\n".join(lines)


def _reset_draft(session_row: WhatsAppSession) -> None:
    session_row.pending_raw_text = None
    session_row.parsed_summary = None
    session_row.pending_title = None
    session_row.campaign_id = None
    session_row.export_job_id = None
    session_row.export_document_sent_at = None
    session_row.export_image_sent_at = None
    session_row.export_files_sent_at = None
    session_row.revision_count = 0
    session_row.last_error = None


def _clear_pending_action(session_row: WhatsAppSession) -> None:
    session_row.pending_action = None
    session_row.pending_action_market_id = None
    session_row.pending_action_payload = None
    session_row.pending_action_expires_at = None


def _clear_market_context(session_row: WhatsAppSession) -> None:
    session_row.active_market_id = None
    session_row.market_choice_json = None
    session_row.state = "idle"
    _clear_pending_action(session_row)


def _normalize_command(text: str) -> str:
    # Turkish casefolding: the dotted/dotless i pair means str.lower() alone
    # turns "İPTAL" into "i̇ptal" (with a combining dot), so map explicitly.
    collapsed = " ".join(text.strip().split())
    return (
        collapsed.replace("I", "ı")
        .replace("İ", "i")
        .lower()
    )


def _parsed_summary(items: list[ParsedCampaignLine]) -> dict[str, object]:
    return {
        "parsed_count": len(items),
        "warning_count": sum(len(item.parsed_payload.get("warnings", [])) for item in items),
        "preview_names": [item.display_name for item in items[:5]],
    }


def _campaign_error_message(exc: HTTPException) -> str:
    if exc.status_code == 402:
        return "Bu ay için kampanya kotanız doldu. Planınızı yükseltebilirsiniz."
    if exc.status_code == 403:
        return "Bu market için kampanya oluşturma yetkiniz yok."
    return "Kampanya oluşturulamadı. Lütfen daha sonra tekrar deneyin."


def _safe_error(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"[:500]
