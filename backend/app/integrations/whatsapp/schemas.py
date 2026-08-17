"""Evolution API (WhatsApp) webhook envelope schemas and normalizer.

Evolution's webhook payload shape varies across events (`messages.upsert`,
`messages.update`, `connection.update`, `presence.update`, ...), and even
within `messages.upsert` the text payload lives in a different nested field
depending on the WhatsApp message type (plain text, reply, caption, button
reply, ...). These models are deliberately lenient (`extra="ignore"`,
everything optional) so parsing never raises on a shape we have not seen yet;
`normalize_evolution_event` is the single place that turns that lenient,
uncertain payload into a small, well-typed record the rest of the codebase
can rely on.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.services.phone import parse_whatsapp_jid

# Evolution webhooks arrive as MESSAGES_UPSERT (older/env-configured) or
# messages.upsert (dotted, lowercase). Only inbound customer messages are
# ever acted on downstream; everything else is recorded and ignored.
INBOUND_MESSAGE_EVENTS = frozenset({"MESSAGES_UPSERT"})


class EvolutionMessageKey(BaseModel):
    model_config = ConfigDict(extra="ignore")

    remoteJid: str | None = None
    fromMe: bool | None = None
    id: str | None = None
    participant: str | None = None
    remoteJidAlt: str | None = None
    senderPn: str | None = None


class EvolutionMessageData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    key: EvolutionMessageKey | None = None
    pushName: str | None = None
    status: str | None = None
    # The message content is a union of many shapes depending on messageType
    # (conversation / extendedTextMessage / imageMessage / ...); kept as a
    # raw mapping and walked explicitly by `_extract_text` rather than
    # modeled field-by-field.
    message: dict[str, Any] | None = None
    messageType: str | None = None
    messageTimestamp: int | float | None = None
    instanceId: str | None = None
    source: str | None = None


class EvolutionWebhookEnvelope(BaseModel):
    model_config = ConfigDict(extra="ignore")

    event: str | None = None
    instance: str | None = None
    destination: str | None = None
    date_time: str | None = None
    sender: str | None = None
    server_url: str | None = None
    apikey: str | None = None
    data: EvolutionMessageData | None = None


@dataclass(frozen=True)
class NormalizedWhatsAppMessage:
    event_type: str
    instance: str | None
    message_id: str | None
    chat_jid: str | None
    sender_jid: str | None
    sender_phone_e164: str | None
    push_name: str | None
    text: str | None
    message_type: str | None
    timestamp: datetime | None
    from_me: bool
    is_group: bool
    raw_event_name: str | None


def normalize_evolution_event(payload: Mapping[str, Any]) -> NormalizedWhatsAppMessage | None:
    """Best-effort normalization of an Evolution webhook body.

    Returns None only when `payload` is not a dict-like/mapping value (i.e.
    structurally unusable). Any mapping, including an empty one or one
    describing a non-message event, yields a `NormalizedWhatsAppMessage` with
    whatever fields could be extracted so the caller can record + ignore
    non-message events uniformly. Never raises.
    """
    if not isinstance(payload, Mapping):
        return None
    try:
        envelope = EvolutionWebhookEnvelope.model_validate(dict(payload))
    except Exception:  # noqa: BLE001 - webhook input must never raise, shape is untrusted
        return None

    try:
        data = envelope.data
        key = data.key if data is not None else None
        message = data.message if data is not None else None

        raw_event_name = envelope.event
        event_type = _normalize_event_type(raw_event_name)
        sender_jid, sender_phone_e164 = _resolve_sender(key)

        return NormalizedWhatsAppMessage(
            event_type=event_type,
            instance=envelope.instance,
            message_id=key.id if key is not None else None,
            chat_jid=key.remoteJid if key is not None else None,
            sender_jid=sender_jid,
            sender_phone_e164=sender_phone_e164,
            push_name=data.pushName if data is not None else None,
            text=_extract_text(message),
            message_type=data.messageType if data is not None else None,
            timestamp=_parse_timestamp(data.messageTimestamp if data is not None else None),
            from_me=bool(key.fromMe) if key is not None and key.fromMe is not None else False,
            is_group=_is_group(key),
            raw_event_name=raw_event_name,
        )
    except Exception:  # noqa: BLE001 - webhook input must never raise, shape is untrusted
        return None


def event_key(instance: str | None, event_type: str, message_id: str | None) -> str:
    """Idempotency key for recording an inbound webhook event exactly once."""
    key = f"{instance or '-'}:{event_type}:{message_id or '-'}"
    return key[:512]


def _normalize_event_type(raw_event_name: str | None) -> str:
    if not raw_event_name:
        return ""
    return raw_event_name.strip().upper().replace(".", "_")


def _resolve_sender(key: EvolutionMessageKey | None) -> tuple[str | None, str | None]:
    """Resolves the authoritative sender JID/phone.

    Precedence: `senderPn` (newer Evolution's always-real-phone field), then
    `remoteJidAlt`, then the conversation JID — `participant` for a group,
    `remoteJid` for a 1:1 chat. The first candidate that `parse_whatsapp_jid`
    resolves to a phone number wins; `@lid` JIDs carry no phone number, so
    they are skipped automatically without any bespoke string handling.

    The envelope's top-level `sender` is deliberately NOT a candidate. In
    Evolution v2 that field is the *instance owner's* JID — i.e. the central
    LeafletPilot number itself — so using it as a fallback would attribute a
    message whose real sender could not be resolved (a pure `@lid` delivery,
    say) to whichever LeafletPilot user had verified the platform's own
    number. Failing closed with "unknown sender" is the only safe answer
    here; `app/integrations/whatsapp/service.py` additionally refuses any
    message that resolves to the platform's own number.
    """
    if key is None:
        return None, None
    conversation_candidate = key.participant if _is_group(key) else key.remoteJid
    for candidate in (key.senderPn, key.remoteJidAlt, conversation_candidate):
        parsed = parse_whatsapp_jid(candidate)
        if parsed is not None and parsed.phone_e164:
            return parsed.raw, parsed.phone_e164
    return None, None


def _is_group(key: EvolutionMessageKey | None) -> bool:
    if key is None:
        return False
    parsed = parse_whatsapp_jid(key.remoteJid)
    if parsed is not None and parsed.is_group:
        return True
    return bool(key.participant)


def _extract_text(message: dict[str, Any] | None) -> str | None:
    if not isinstance(message, dict):
        return None

    conversation = message.get("conversation")
    if isinstance(conversation, str) and conversation:
        return conversation

    extended_text = _string_field(message.get("extendedTextMessage"), "text")
    if extended_text:
        return extended_text

    for field_name in ("imageMessage", "videoMessage", "documentMessage"):
        caption = _string_field(message.get(field_name), "caption")
        if caption:
            return caption

    buttons_reply = _string_field(message.get("buttonsResponseMessage"), "selectedDisplayText")
    if buttons_reply:
        return buttons_reply

    list_reply = _string_field(message.get("listResponseMessage"), "title")
    if list_reply:
        return list_reply

    template_reply = _string_field(
        message.get("templateButtonReplyMessage"), "selectedDisplayText"
    )
    if template_reply:
        return template_reply

    ephemeral = message.get("ephemeralMessage")
    if isinstance(ephemeral, dict):
        inner = ephemeral.get("message")
        if isinstance(inner, dict):
            inner_conversation = inner.get("conversation")
            if isinstance(inner_conversation, str) and inner_conversation:
                return inner_conversation
            inner_extended_text = _string_field(inner.get("extendedTextMessage"), "text")
            if inner_extended_text:
                return inner_extended_text

    return None


def _string_field(container: Any, field_name: str) -> str | None:
    if not isinstance(container, dict):
        return None
    value = container.get(field_name)
    return value if isinstance(value, str) and value else None


def _parse_timestamp(value: float | None) -> datetime | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric <= 0:
        return None
    # Evolution typically sends Unix seconds, but some webhook configurations
    # forward milliseconds; anything beyond a plausible seconds range is
    # treated as milliseconds.
    if numeric > 10**12:
        numeric /= 1000
    try:
        return datetime.fromtimestamp(numeric, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None
