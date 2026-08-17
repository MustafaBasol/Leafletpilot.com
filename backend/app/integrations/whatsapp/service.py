"""Inbound orchestration for the central LeafletPilot WhatsApp channel.

The webhook controller stays thin; everything below happens here:

    Evolution webhook
      -> normalize event            (app/integrations/whatsapp/schemas.py)
      -> idempotency ledger         (whatsapp_webhook_events)
      -> ignore rules               (fromMe / group / non-text / self)
      -> verification challenge?    (whatsapp_verifications)
      -> resolve verified identity  (user_whatsapp_identities)
      -> command router             (app/integrations/whatsapp/commands.py)
      -> outbound reply             (EvolutionClientProtocol)

Two invariants govern this module:

1. **The sender is the source of truth.** A verification succeeds because the
   message arrived from a WhatsApp account, not because a number typed into
   the UI matched a string. The claimed phone is only ever advisory.
2. **Nothing is authorized from cache.** An identity proves *who* the sender
   is; every command re-reads `market_users` to decide *what they may do*, so
   a removed membership, a deactivated user or a suspended market takes
   effect on the very next message.
"""

from __future__ import annotations

import logging
import re
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.security import hash_whatsapp_verification_code, normalize_whatsapp_verification_code
from app.integrations.whatsapp.client import EvolutionClientError, EvolutionClientProtocol
from app.integrations.whatsapp.schemas import (
    INBOUND_MESSAGE_EVENTS,
    NormalizedWhatsAppMessage,
    event_key,
)
from app.models import (
    ActivityLog,
    MarketUser,
    User,
    UserWhatsAppIdentity,
    WhatsAppIntegrationState,
    WhatsAppVerification,
    WhatsAppWebhookEvent,
)
from app.models.base import utc_now
from app.services.phone import mask_phone, normalize_phone_e164
from app.services.rate_limit import WHATSAPP_SENDER_KEY, consume_rate_limit

logger = logging.getLogger(__name__)

# Same lease semantics the Telegram ledger uses: an event whose processing
# crashed mid-flight becomes retryable after this long instead of wedging.
PROCESSING_LEASE = timedelta(minutes=5)

# Longest inbound message we will consider. Anything above this is almost
# certainly not a product list a market owner typed.
MAX_INBOUND_TEXT_LENGTH = 8000

# Matches a verification code anywhere inside a longer message ("Merhaba,
# kodum LP-X7K4-M92Q"), tolerating the separators WhatsApp clients insert.
_CODE_CANDIDATE_RE = re.compile(r"LP[\s\-_.]*([0-9A-Z][\s\-_.]*){8}", re.IGNORECASE)

UNVERIFIED_REPLY = (
    "Bu WhatsApp numarası LeafletPilot hesabınızla doğrulanmamış.\n\n"
    "LeafletPilot hesabınıza giriş yaparak Ekip sayfasından WhatsApp doğrulama "
    "işlemini başlatabilirsiniz."
)
INVALID_CODE_REPLY = (
    "Doğrulama kodu geçersiz veya süresi dolmuş. "
    "LeafletPilot üzerinden yeni bir kod oluşturabilirsiniz."
)


async def process_webhook_event(
    session: AsyncSession,
    normalized: NormalizedWhatsAppMessage,
    client: EvolutionClientProtocol,
) -> str:
    """Handles one Evolution webhook delivery.

    Returns a short outcome tag for observability. Never raises for a payload
    LeafletPilot simply does not act on — an unsupported Evolution event is a
    normal occurrence, not an error.
    """
    await _touch_integration_state(session, normalized)

    if normalized.event_type not in INBOUND_MESSAGE_EVENTS:
        await session.commit()
        return "ignored_event_type"
    if normalized.from_me:
        await session.commit()
        return "ignored_from_me"
    if normalized.is_group:
        await session.commit()
        return "ignored_group"

    sender_phone = normalized.sender_phone_e164
    if not sender_phone:
        # Reached when Evolution delivers only an @lid with no senderPn — an
        # older/misconfigured instance. Loud enough to diagnose, never a 500.
        logger.warning(
            "WhatsApp inbound message had no resolvable sender. instance=%s message_id=%s chat_jid_server=%s",
            normalized.instance,
            normalized.message_id,
            (normalized.chat_jid or "").rsplit("@", 1)[-1],
        )
        await session.commit()
        return "ignored_unknown_sender"
    if _is_platform_number(sender_phone):
        # Belt-and-braces companion to the fromMe check: never act on a
        # message attributed to the central LeafletPilot number itself.
        await session.commit()
        return "ignored_self"

    text = (normalized.text or "").strip()
    if not text:
        await session.commit()
        return "ignored_non_text"
    if len(text) > MAX_INBOUND_TEXT_LENGTH:
        text = text[:MAX_INBOUND_TEXT_LENGTH]

    record = await _begin_event(session, normalized)
    if record is None:
        logger.info(
            "Duplicate WhatsApp webhook event ignored. instance=%s message_id=%s",
            normalized.instance,
            normalized.message_id,
        )
        return "duplicate"

    # Finalize by key with a Core UPDATE rather than by mutating `record`.
    # Handlers below may commit mid-flow (campaign creation) or roll back
    # (a lost verification race), and a rollback expires every ORM instance —
    # touching an expired attribute afterwards would trigger an implicit
    # lazy load, which raises MissingGreenlet under the async session.
    key = event_key(normalized.instance, normalized.event_type, normalized.message_id)

    try:
        outcome = await _dispatch(session, normalized, sender_phone, text, client)
    except Exception as exc:
        logger.exception(
            "WhatsApp inbound processing failed. instance=%s message_id=%s sender=%s",
            normalized.instance,
            normalized.message_id,
            mask_phone(sender_phone),
        )
        await _finalize_event(session, key, status="failed", last_error=_safe_error(exc))
        raise

    await _finalize_event(session, key, status="completed", last_error=None)
    return outcome


async def _finalize_event(
    session: AsyncSession,
    key: str,
    *,
    status: str,
    last_error: str | None,
) -> None:
    await session.execute(
        update(WhatsAppWebhookEvent)
        .where(WhatsAppWebhookEvent.event_key == key)
        .values(status=status, last_error=last_error, processed_at=utc_now())
    )
    await session.commit()


async def _dispatch(
    session: AsyncSession,
    normalized: NormalizedWhatsAppMessage,
    sender_phone: str,
    text: str,
    client: EvolutionClientProtocol,
) -> str:
    # Per-sender flood protection. Applied before any identity lookup so an
    # unknown number cannot use us as an oracle or a reply amplifier.
    if await consume_rate_limit(
        session,
        key_type=WHATSAPP_SENDER_KEY,
        raw_value=sender_phone,
        limit=settings.whatsapp_inbound_message_limit,
    ):
        logger.warning("WhatsApp inbound rate limit hit. sender=%s", mask_phone(sender_phone))
        return "rate_limited"

    # Verification codes are matched BEFORE the identity lookup and before the
    # command router, so a code can never be parsed as a product list or fed
    # into brochure generation.
    code = extract_verification_code(text)
    if code is not None:
        return await _handle_verification_code(session, normalized, sender_phone, code, client)

    identity = await _resolve_verified_identity(session, sender_phone, normalized.sender_jid)
    if identity is None:
        return await _reply_unverified(session, sender_phone, client)

    if not identity.user.is_active:
        # The identity is real but the LeafletPilot account is disabled.
        # Deliberately the same generic answer as an unknown sender: a
        # disabled account must not be able to probe its own state.
        return await _reply_unverified(session, sender_phone, client)

    identity.last_seen_at = utc_now()

    from app.integrations.whatsapp import commands

    return await commands.handle_message(session, identity, text, client)


# --- verification ---------------------------------------------------------


def extract_verification_code(text: str) -> str | None:
    """Finds a LeafletPilot verification code inside an arbitrary message.

    A code is recognised anywhere in the text so the natural "here is my code:
    LP-…" phrasing works, but the extracted candidate still has to satisfy
    `normalize_whatsapp_verification_code` (correct length, alphabet and
    prefix) before it counts.
    """
    for match in _CODE_CANDIDATE_RE.finditer(text):
        normalized = normalize_whatsapp_verification_code(match.group(0))
        if normalized is not None:
            return normalized
    # Also accept a message that is exactly the code with no surrounding text,
    # which the regex above already covers, plus the bare compact form.
    return normalize_whatsapp_verification_code(text)


async def _handle_verification_code(
    session: AsyncSession,
    normalized: NormalizedWhatsAppMessage,
    sender_phone: str,
    code: str,
    client: EvolutionClientProtocol,
) -> str:
    code_hash = hash_whatsapp_verification_code(code)
    verification = await session.scalar(
        select(WhatsAppVerification)
        .where(WhatsAppVerification.code_hash == code_hash, WhatsAppVerification.status == "pending")
        .with_for_update()
    )
    if verification is None:
        # Identical answer whether the code never existed, was already
        # consumed or belongs to someone else — no oracle.
        await _send(session, client, sender_phone, INVALID_CODE_REPLY)
        return "verification_unknown_code"

    now = utc_now()
    verification.attempt_count += 1

    if verification.expires_at <= now:
        verification.status = "expired"
        verification.failure_reason = "expired"
        verification.consumed_at = now
        _audit_verification(session, verification, "WHATSAPP_VERIFICATION_FAILED", sender_phone, "expired")
        await _send(session, client, sender_phone, INVALID_CODE_REPLY)
        return "verification_expired"

    if verification.attempt_count > settings.whatsapp_verification_max_attempts:
        verification.status = "failed"
        verification.failure_reason = "attempt_limit"
        verification.consumed_at = now
        _audit_verification(
            session, verification, "WHATSAPP_VERIFICATION_FAILED", sender_phone, "attempt_limit"
        )
        await _send(session, client, sender_phone, INVALID_CODE_REPLY)
        return "verification_attempt_limit"

    user = await session.get(User, verification.user_id)
    if user is None or not user.is_active:
        return await _fail_verification(
            session, verification, sender_phone, client, "user_inactive",
            "LeafletPilot hesabınız şu anda aktif değil. Lütfen market yöneticinizle görüşün.",
        )

    membership = await session.scalar(
        select(MarketUser)
        .options(selectinload(MarketUser.market))
        .where(
            MarketUser.user_id == verification.user_id,
            MarketUser.market_id == verification.market_id,
            MarketUser.is_active.is_(True),
        )
    )
    if membership is None or membership.market is None or not membership.market.is_active:
        return await _fail_verification(
            session, verification, sender_phone, client, "membership_revoked",
            "Bu market için erişiminiz artık bulunmuyor. Lütfen market yöneticinizle görüşün.",
        )

    sender_jid = normalized.sender_jid or f"{sender_phone.lstrip('+')}@s.whatsapp.net"

    # Phone/JID collision: this WhatsApp account is already proven to belong
    # to a different LeafletPilot user. Never silently move it.
    conflicting = await session.scalar(
        select(UserWhatsAppIdentity).where(
            UserWhatsAppIdentity.status == "verified",
            (UserWhatsAppIdentity.phone_e164 == sender_phone)
            | (UserWhatsAppIdentity.whatsapp_jid == sender_jid),
        )
    )
    if conflicting is not None and conflicting.user_id != verification.user_id:
        # Recoverable, unlike the account-level failures above: the code is
        # fine, it just arrived from the wrong handset. Keeping the challenge
        # pending lets the user resend from the correct phone inside the same
        # window instead of waiting out the resend cooldown for a new code —
        # and it is what makes `attempt_count`/the attempt limit meaningful,
        # since every other failure path is terminal by nature.
        return await _fail_verification(
            session, verification, sender_phone, client, "phone_already_linked",
            "Bu WhatsApp numarası başka bir LeafletPilot kullanıcısına bağlı. "
            "Devam etmek için önce mevcut bağlantının kaldırılması gerekir.",
            terminal=False,
        )

    # The target user already has a different verified number. The request API
    # blocks this, so reaching here means a concurrent verification; fail
    # closed rather than leaving two verified identities for one user.
    existing_for_user = await session.scalar(
        select(UserWhatsAppIdentity).where(
            UserWhatsAppIdentity.user_id == verification.user_id,
            UserWhatsAppIdentity.status == "verified",
        )
    )
    if existing_for_user is not None and existing_for_user.phone_e164 != sender_phone:
        return await _fail_verification(
            session, verification, sender_phone, client, "user_already_verified",
            "Bu LeafletPilot kullanıcısının doğrulanmış başka bir WhatsApp numarası var. "
            "Önce mevcut doğrulamayı kaldırın.",
        )

    if existing_for_user is not None:
        identity = existing_for_user
        identity.whatsapp_jid = sender_jid
        identity.verified_at = now
    else:
        identity = UserWhatsAppIdentity(
            user_id=verification.user_id,
            phone_e164=sender_phone,
            whatsapp_jid=sender_jid,
            status="verified",
            verified_source="evolution_whatsapp",
            verified_at=now,
            verified_via_market_id=verification.market_id,
            last_seen_at=now,
        )
        session.add(identity)

    verification.status = "verified"
    verification.consumed_at = now
    verification.resolved_phone_e164 = sender_phone
    verification.resolved_jid = sender_jid
    verification.failure_reason = None

    try:
        await session.flush()
    except IntegrityError:
        # A concurrent webhook delivery won the race for the same phone/user.
        await session.rollback()
        await _send(session, client, sender_phone, INVALID_CODE_REPLY)
        await session.commit()
        return "verification_conflict"

    _audit_verification(session, verification, "WHATSAPP_VERIFIED", sender_phone, None)
    logger.info(
        "WhatsApp identity verified. user_id=%s market_id=%s phone=%s",
        verification.user_id,
        verification.market_id,
        mask_phone(sender_phone),
    )

    message = ["WhatsApp numaranız doğrulandı."]
    claimed = verification.claimed_phone_e164
    if claimed and claimed != sender_phone:
        # Explained, never silently reconciled — the UI shows the same note.
        message.append(
            "Not: doğrulanan numara LeafletPilot'ta girilen numaradan farklı. "
            f"WhatsApp hesabınızın gerçek numarası ({mask_phone(sender_phone)}) kaydedildi."
        )
    await _send(session, client, sender_phone, "\n\n".join(message))

    from app.integrations.whatsapp import commands

    await commands.send_welcome(session, identity, client)
    return "verified"


async def _fail_verification(
    session: AsyncSession,
    verification: WhatsAppVerification,
    sender_phone: str,
    client: EvolutionClientProtocol,
    reason: str,
    reply: str,
    *,
    terminal: bool = True,
) -> str:
    """Records a failed resolution of a matched challenge.

    `terminal=True` consumes the challenge (the failure cannot be fixed by
    resending — the account is disabled, the membership is gone). With
    `terminal=False` the challenge stays `pending` so the user can retry
    within its window; the attempt limit checked in
    `_handle_verification_code` is what eventually closes it out.
    """
    verification.failure_reason = reason
    verification.resolved_phone_e164 = sender_phone
    if terminal:
        verification.status = "failed"
        verification.consumed_at = utc_now()
    _audit_verification(session, verification, "WHATSAPP_VERIFICATION_FAILED", sender_phone, reason)
    await _send(session, client, sender_phone, reply)
    return f"verification_failed_{reason}"


def _audit_verification(
    session: AsyncSession,
    verification: WhatsAppVerification,
    action: str,
    sender_phone: str | None,
    reason: str | None,
) -> None:
    """Audit rows carry the masked phone and a reason code only.

    The plaintext code, its hash and the unmasked number are all excluded by
    construction — this is the single place verification outcomes are audited.
    """
    session.add(
        ActivityLog(
            market_id=verification.market_id,
            user_id=verification.user_id,
            entity_type="whatsapp_verification",
            entity_id=verification.id,
            action=action,
            description=action.replace("_", " ").lower(),
            metadata_={
                "sender_phone_masked": mask_phone(sender_phone),
                "reason": reason or "",
                "attempt_count": verification.attempt_count,
            },
        )
    )


# --- identity -------------------------------------------------------------


async def _resolve_verified_identity(
    session: AsyncSession,
    sender_phone: str,
    sender_jid: str | None,
) -> UserWhatsAppIdentity | None:
    """Looks up the verified identity for a sender.

    Matches on the canonical phone first (the JID's device/server form can
    change between WhatsApp releases), falling back to an exact JID match.
    """
    statement = (
        select(UserWhatsAppIdentity)
        .options(selectinload(UserWhatsAppIdentity.user))
        .where(
            UserWhatsAppIdentity.status == "verified",
            UserWhatsAppIdentity.phone_e164 == sender_phone,
        )
    )
    identity = await session.scalar(statement)
    if identity is not None or not sender_jid:
        return identity
    return await session.scalar(
        select(UserWhatsAppIdentity)
        .options(selectinload(UserWhatsAppIdentity.user))
        .where(
            UserWhatsAppIdentity.status == "verified",
            UserWhatsAppIdentity.whatsapp_jid == sender_jid,
        )
    )


async def _reply_unverified(
    session: AsyncSession,
    sender_phone: str,
    client: EvolutionClientProtocol,
) -> str:
    """Answers an unknown sender without confirming or denying anything.

    Replying to every message from an unknown number would make the channel a
    reflector, so the generic answer itself is rate limited: after a few
    messages in the window we simply stay silent.
    """
    if await consume_rate_limit(
        session,
        key_type=WHATSAPP_SENDER_KEY,
        raw_value=f"unverified:{sender_phone}",
        limit=3,
    ):
        return "unverified_silenced"
    await _send(session, client, sender_phone, UNVERIFIED_REPLY)
    return "unverified"


# --- outbound + ledger ----------------------------------------------------


async def _send(
    session: AsyncSession,
    client: EvolutionClientProtocol,
    phone_e164: str,
    text: str,
) -> bool:
    """Sends a reply, recording success/failure for Platform Admin.

    A failed outbound send must not abort inbound processing (the inbound
    state change is what matters and is already committed by the caller), so
    the Evolution error is captured and swallowed here.
    """
    state = await _integration_state(session)
    try:
        await client.send_text(phone_e164, text)
    except EvolutionClientError as exc:
        logger.warning(
            "WhatsApp outbound send failed. to=%s error=%s",
            mask_phone(phone_e164),
            _safe_error(exc),
            exc_info=True,
        )
        if state is not None:
            state.last_outbound_error = _safe_error(exc)
            state.last_outbound_error_at = utc_now()
        return False
    if state is not None:
        # `last_outbound_error` is sticky: it is the LAST error, not the
        # CURRENT one. A single inbound message can trigger several sends
        # (confirmation, then the welcome/market prompt), so clearing it on
        # success would let a later send in the same request erase a genuine
        # failure an operator never got to see. `last_outbound_at` vs
        # `last_outbound_error_at` is what tells Platform Admin whether the
        # error is stale.
        state.last_outbound_at = utc_now()
    return True


async def send_media(
    session: AsyncSession,
    client: EvolutionClientProtocol,
    phone_e164: str,
    path,
    *,
    media_type: str,
    mime_type: str,
    file_name: str,
    caption: str | None = None,
) -> bool:
    state = await _integration_state(session)
    try:
        await client.send_media(
            phone_e164,
            path,
            media_type=media_type,
            mime_type=mime_type,
            file_name=file_name,
            caption=caption,
        )
    except EvolutionClientError as exc:
        logger.warning(
            "WhatsApp outbound media send failed. to=%s error=%s",
            mask_phone(phone_e164),
            _safe_error(exc),
            exc_info=True,
        )
        if state is not None:
            state.last_outbound_error = _safe_error(exc)
            state.last_outbound_error_at = utc_now()
        return False
    if state is not None:
        # `last_outbound_error` is sticky: it is the LAST error, not the
        # CURRENT one. A single inbound message can trigger several sends
        # (confirmation, then the welcome/market prompt), so clearing it on
        # success would let a later send in the same request erase a genuine
        # failure an operator never got to see. `last_outbound_at` vs
        # `last_outbound_error_at` is what tells Platform Admin whether the
        # error is stale.
        state.last_outbound_at = utc_now()
    return True


async def send_text(
    session: AsyncSession,
    client: EvolutionClientProtocol,
    phone_e164: str,
    text: str,
) -> bool:
    """Public wrapper so the command router shares the observability path."""
    return await _send(session, client, phone_e164, text)


async def _begin_event(
    session: AsyncSession,
    normalized: NormalizedWhatsAppMessage,
) -> WhatsAppWebhookEvent | None:
    """Claims an event for processing, or returns None if it is a duplicate.

    Evolution and WhatsApp both redeliver. Without this, a redelivered
    `messages.upsert` would consume a verification code twice or generate a
    second campaign.
    """
    key = event_key(normalized.instance, normalized.event_type, normalized.message_id)
    now = utc_now()
    existing = await session.scalar(
        select(WhatsAppWebhookEvent).where(WhatsAppWebhookEvent.event_key == key).with_for_update()
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

    record = WhatsAppWebhookEvent(
        event_key=key,
        instance_name=normalized.instance,
        event_type=normalized.event_type,
        status="processing",
        attempt_count=1,
        received_at=now,
        processing_started_at=now,
    )
    session.add(record)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        duplicate = await session.scalar(
            select(WhatsAppWebhookEvent).where(WhatsAppWebhookEvent.event_key == key)
        )
        if duplicate is None or duplicate.status != "failed":
            return None
        duplicate.status = "processing"
        duplicate.attempt_count += 1
        duplicate.processing_started_at = now
        await session.commit()
        return duplicate
    await session.refresh(record)
    return record


async def _integration_state(session: AsyncSession) -> WhatsAppIntegrationState | None:
    instance = (settings.evolution_instance_name or "").strip()
    if not instance:
        return None
    return await session.scalar(
        select(WhatsAppIntegrationState).where(WhatsAppIntegrationState.instance_name == instance)
    )


async def _touch_integration_state(
    session: AsyncSession,
    normalized: NormalizedWhatsAppMessage,
) -> None:
    """Records "a webhook arrived" for the Platform Admin health card.

    Keyed on the CONFIGURED instance name, not the one the delivery declares.
    Platform Admin's health endpoint looks the row up by
    `settings.evolution_instance_name`, and `_integration_state` (used for
    outbound bookkeeping) does the same — keying this write off the payload
    instead would let a delivery declaring a different instance write a row
    nobody ever reads, silently freezing the "last webhook" indicator.
    """
    instance = (settings.evolution_instance_name or normalized.instance or "").strip()
    if not instance:
        return
    now = utc_now()
    state = await session.scalar(
        select(WhatsAppIntegrationState).where(WhatsAppIntegrationState.instance_name == instance)
    )
    if state is None:
        state = WhatsAppIntegrationState(instance_name=instance)
        session.add(state)
        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
            state = await session.scalar(
                select(WhatsAppIntegrationState).where(
                    WhatsAppIntegrationState.instance_name == instance
                )
            )
            if state is None:
                return
    state.last_webhook_at = now
    state.last_webhook_event_type = normalized.event_type or None
    if normalized.event_type in INBOUND_MESSAGE_EVENTS and not normalized.from_me:
        state.last_inbound_message_at = now


def _is_platform_number(phone_e164: str) -> bool:
    configured = normalize_phone_e164(settings.leafletpilot_whatsapp_number)
    return configured is not None and configured == phone_e164


def _safe_error(exc: Exception) -> str:
    """Bounded, credential-free error text safe to persist."""
    return f"{type(exc).__name__}: {exc}"[:500]


__all__ = [
    "PROCESSING_LEASE",
    "extract_verification_code",
    "process_webhook_event",
    "send_media",
    "send_text",
]
