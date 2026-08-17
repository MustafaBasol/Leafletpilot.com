"""Phone-number normalization shared by the central WhatsApp channel.

WhatsApp identity is security-relevant: the number a market admin types into
the LeafletPilot UI is only advisory, while the number derived from the
Evolution webhook sender is authoritative (see
`app/integrations/whatsapp/service.py`). Both sides go through this module so
"+33 6 12 34 56 78", "0033612345678" and the JID user part "33612345678"
collapse to exactly one canonical string before anything is compared or
stored.

Deliberately backed by `phonenumbers` (Google's libphonenumber port) rather
than prefix/string surgery: national-prefix stripping, variable country-code
lengths and per-region national number lengths are not something a regex gets
right, and a wrong answer here means one user's WhatsApp identity could be
matched against another user's record.
"""

from __future__ import annotations

from dataclasses import dataclass

import phonenumbers

# WhatsApp JID servers we understand. Anything else (newsletter, broadcast,
# status) is treated as unsupported and ignored by the webhook.
WHATSAPP_USER_SERVER = "s.whatsapp.net"
WHATSAPP_GROUP_SERVER = "g.us"
WHATSAPP_LID_SERVER = "lid"


@dataclass(frozen=True)
class WhatsAppJid:
    """Parsed WhatsApp JID.

    `phone_e164` is only populated for `@s.whatsapp.net` JIDs, whose user part
    is a real MSISDN. `@lid` (LinkedID) JIDs are privacy-preserving surrogate
    identifiers introduced in newer WhatsApp/Evolution versions and carry no
    phone number at all — the caller must fall back to a dedicated sender-phone
    field (`remoteJidAlt` / `senderPn`) instead of guessing.
    """

    raw: str
    user_part: str
    server: str
    phone_e164: str | None

    @property
    def is_group(self) -> bool:
        return self.server == WHATSAPP_GROUP_SERVER

    @property
    def is_lid(self) -> bool:
        return self.server == WHATSAPP_LID_SERVER

    @property
    def is_user(self) -> bool:
        return self.server == WHATSAPP_USER_SERVER


def normalize_phone_e164(raw: str | None, *, default_region: str | None = None) -> str | None:
    """Returns the E.164 form of `raw`, or None when it is not a valid number.

    `default_region` (an ISO-3166 alpha-2 code such as "FR") is only consulted
    for inputs without an international prefix; it is intentionally optional so
    webhook-derived numbers — which are always international — never depend on
    market configuration.
    """
    if not raw:
        return None
    candidate = raw.strip()
    if not candidate:
        return None
    # Accept the bare digit form WhatsApp uses in JIDs ("33612345678") by
    # promoting it to an international literal; libphonenumber needs either a
    # leading "+" or a region to anchor the country code.
    if candidate.isdigit() and default_region is None:
        candidate = f"+{candidate}"
    region = (default_region or "").strip().upper() or None
    try:
        parsed = phonenumbers.parse(candidate, region)
    except phonenumbers.NumberParseException:
        # A digits-only value with a region hint may still be an international
        # number that simply lost its "+" (e.g. copied from a WhatsApp JID).
        if region is not None and candidate.isdigit():
            return normalize_phone_e164(candidate, default_region=None)
        return None
    if not phonenumbers.is_valid_number(parsed):
        if region is not None and candidate.isdigit():
            return normalize_phone_e164(candidate, default_region=None)
        return None
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def phone_to_whatsapp_number(phone_e164: str) -> str:
    """Digits-only form Evolution expects as the `number` field of a send call."""
    return phone_e164.lstrip("+")


def mask_phone(phone_e164: str | None) -> str:
    """Log/audit-safe rendering: keeps the country code and last two digits.

    Audit metadata and structured logs must be able to identify *which*
    number an event concerned without storing the number itself, so this is
    the only form of a phone number allowed in either.
    """
    if not phone_e164:
        return ""
    digits = phone_e164.lstrip("+")
    if len(digits) <= 4:
        return "+" + "*" * len(digits)
    return f"+{digits[:2]}{'*' * (len(digits) - 4)}{digits[-2:]}"


def parse_whatsapp_jid(jid: str | None) -> WhatsAppJid | None:
    """Splits a WhatsApp JID into its user part and server.

    Device suffixes ("33612345678:12@s.whatsapp.net") and the agent/session
    suffix Evolution occasionally forwards are stripped, because they identify
    a *device*, not the account we authorize.
    """
    if not jid:
        return None
    raw = jid.strip()
    if "@" not in raw:
        return None
    user_part, _, server = raw.partition("@")
    server = server.strip().lower()
    user_part = user_part.split(":", 1)[0].strip()
    if not user_part or not server:
        return None
    phone = normalize_phone_e164(user_part) if server == WHATSAPP_USER_SERVER else None
    return WhatsAppJid(raw=raw, user_part=user_part, server=server, phone_e164=phone)
