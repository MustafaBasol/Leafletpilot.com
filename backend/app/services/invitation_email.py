from __future__ import annotations

import asyncio
import logging
import smtplib
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr
from typing import Protocol

from app.core.config import settings

logger = logging.getLogger(__name__)

SUPPORTED_LANGUAGES = {"tr", "en", "fr", "de"}

SUBJECTS = {
    "tr": "LeafletPilot market aktivasyon daveti",
    "en": "LeafletPilot market activation invitation",
    "fr": "Invitation d'activation de votre marche LeafletPilot",
    "de": "LeafletPilot Einladung zur Marktaktivierung",
}

INTRO_LINES = {
    "tr": "Marketinizi LeafletPilot'ta aktifleştirmek için davet edildiniz.",
    "en": "You have been invited to activate your market on LeafletPilot.",
    "fr": "Vous avez ete invite a activer votre marche sur LeafletPilot.",
    "de": "Sie wurden eingeladen, Ihren Markt in LeafletPilot zu aktivieren.",
}

ACTION_LINES = {
    "tr": "Aktivasyon bağlantısı:",
    "en": "Activation link:",
    "fr": "Lien d'activation :",
    "de": "Aktivierungslink:",
}

EXPIRY_LINES = {
    "tr": "Bu davet su tarihte sona erer:",
    "en": "This invitation expires at:",
    "fr": "Cette invitation expire le :",
    "de": "Diese Einladung lauft ab am:",
}

PASSWORD_RESET_SUBJECTS = {
    "tr": "LeafletPilot şifre sıfırlama bağlantısı",
    "en": "LeafletPilot password reset link",
    "fr": "Lien de réinitialisation du mot de passe LeafletPilot",
    "de": "LeafletPilot Link zum Zurücksetzen des Passworts",
}

PASSWORD_RESET_INTRO_LINES = {
    "tr": "Hesabınız için bir şifre sıfırlama talebi oluşturuldu.",
    "en": "A password reset was requested for your account.",
    "fr": "Une réinitialisation de mot de passe a été demandée pour votre compte.",
    "de": "Für Ihr Konto wurde ein Zurücksetzen des Passworts angefordert.",
}

PASSWORD_RESET_ACTION_LINES = {
    "tr": "Şifre sıfırlama bağlantısı:",
    "en": "Password reset link:",
    "fr": "Lien de réinitialisation :",
    "de": "Link zum Zurücksetzen:",
}

EMAIL_CHANGE_SUBJECTS = {
    "tr": "LeafletPilot e-posta değişikliğini doğrulayın",
    "en": "Confirm your LeafletPilot email change",
    "fr": "Confirmez votre changement d'adresse e-mail LeafletPilot",
    "de": "Bestätigen Sie Ihre LeafletPilot E-Mail-Änderung",
}

EMAIL_CHANGE_INTRO_LINES = {
    "tr": "Hesabınızın e-posta adresini bu adres olarak değiştirme talebi alındı. Bu siz değilseniz bu e-postayı yok sayabilirsiniz.",
    "en": "A request was made to change your account's email address to this one. If this wasn't you, you can ignore this email.",
    "fr": "Une demande de changement d'adresse e-mail de votre compte vers celle-ci a été reçue. Si ce n'était pas vous, ignorez cet e-mail.",
    "de": "Es wurde beantragt, die E-Mail-Adresse Ihres Kontos auf diese zu ändern. Wenn Sie das nicht waren, ignorieren Sie diese E-Mail.",
}

EMAIL_CHANGE_ACTION_LINES = {
    "tr": "Doğrulama bağlantısı:",
    "en": "Verification link:",
    "fr": "Lien de vérification :",
    "de": "Bestätigungslink:",
}


@dataclass(frozen=True)
class OwnerInvitationEmail:
    to_email: str
    market_name: str
    role: str
    accept_url: str
    expires_at: datetime
    language: str


@dataclass(frozen=True)
class PasswordResetEmail:
    to_email: str
    reset_url: str
    expires_at: datetime
    language: str


@dataclass(frozen=True)
class EmailChangeEmail:
    to_email: str
    verify_url: str
    expires_at: datetime
    language: str


class InvitationEmailError(RuntimeError):
    pass


class InvitationDeliveryDisabled:
    """Marker for intentional operator-controlled delivery."""


class SMTPClient(Protocol):
    def __enter__(self) -> "SMTPClient": ...

    def __exit__(self, exc_type, exc, traceback) -> None: ...

    def starttls(self) -> object: ...

    def login(self, user: str, password: str) -> object: ...

    def send_message(self, msg: EmailMessage) -> object: ...


def normalize_language(language: str | None) -> str:
    normalized = (language or "en").strip().lower()
    return normalized if normalized in SUPPORTED_LANGUAGES else "en"


def build_owner_invitation_email(message: OwnerInvitationEmail) -> EmailMessage:
    language = normalize_language(message.language)
    email = EmailMessage()
    email["Subject"] = SUBJECTS[language]
    email["From"] = formataddr((settings.invitation_smtp_from_name, settings.invitation_smtp_from_address))
    email["To"] = message.to_email
    body = "\n".join(
        [
            INTRO_LINES[language],
            "",
            f"Market: {message.market_name}",
            f"Role: {message.role}",
            "",
            ACTION_LINES[language],
            message.accept_url,
            "",
            f"{EXPIRY_LINES[language]} {message.expires_at.isoformat()}",
        ]
    )
    email.set_content(body)
    return email


def build_password_reset_email(message: PasswordResetEmail) -> EmailMessage:
    language = normalize_language(message.language)
    email = EmailMessage()
    email["Subject"] = PASSWORD_RESET_SUBJECTS[language]
    email["From"] = formataddr((settings.invitation_smtp_from_name, settings.invitation_smtp_from_address))
    email["To"] = message.to_email
    body = "\n".join(
        [
            PASSWORD_RESET_INTRO_LINES[language],
            "",
            PASSWORD_RESET_ACTION_LINES[language],
            message.reset_url,
            "",
            f"{EXPIRY_LINES[language]} {message.expires_at.isoformat()}",
        ]
    )
    email.set_content(body)
    return email


async def send_owner_invitation_email(message: OwnerInvitationEmail) -> InvitationDeliveryDisabled | None:
    return await _send_transactional_email(build_owner_invitation_email(message), to_email=message.to_email)


async def send_password_reset_email(message: PasswordResetEmail) -> InvitationDeliveryDisabled | None:
    return await _send_transactional_email(build_password_reset_email(message), to_email=message.to_email)


def build_email_change_email(message: EmailChangeEmail) -> EmailMessage:
    language = normalize_language(message.language)
    email = EmailMessage()
    email["Subject"] = EMAIL_CHANGE_SUBJECTS[language]
    email["From"] = formataddr((settings.invitation_smtp_from_name, settings.invitation_smtp_from_address))
    email["To"] = message.to_email
    body = "\n".join(
        [
            EMAIL_CHANGE_INTRO_LINES[language],
            "",
            EMAIL_CHANGE_ACTION_LINES[language],
            message.verify_url,
            "",
            f"{EXPIRY_LINES[language]} {message.expires_at.isoformat()}",
        ]
    )
    email.set_content(body)
    return email


async def send_email_change_email(message: EmailChangeEmail) -> InvitationDeliveryDisabled | None:
    return await _send_transactional_email(build_email_change_email(message), to_email=message.to_email)


async def _send_transactional_email(email: EmailMessage, *, to_email: str) -> InvitationDeliveryDisabled | None:
    """Shared delivery path for every email this service sends (invitations, password
    resets, ...) — same SMTP infra and delivery-mode handling for all of them, only the
    message content differs per caller."""
    if settings.invitation_email_delivery == "disabled":
        return InvitationDeliveryDisabled()
    if settings.invitation_email_delivery == "fake":
        if settings.environment.lower() not in {"development", "test", "testing"}:
            raise InvitationEmailError("Fake invitation email delivery is only allowed in development or test environments.")
        logger.info("Transactional email accepted by fake mailer.", extra={"to_domain": _safe_domain(to_email)})
        return None
    if settings.invitation_email_delivery == "smtp":
        await asyncio.to_thread(_send_smtp_email, email, to_email)
        return None
    raise InvitationEmailError("Unsupported invitation email delivery mode.")


def _send_smtp_email(email: EmailMessage, to_email: str) -> None:
    _validate_smtp_runtime_settings()
    try:
        smtp_class = smtplib.SMTP_SSL if settings.invitation_smtp_security == "ssl" else smtplib.SMTP
        with smtp_class(
            settings.invitation_smtp_host,
            settings.invitation_smtp_port,
            timeout=settings.invitation_smtp_timeout_seconds,
        ) as client:
            if settings.invitation_smtp_security == "starttls":
                client.starttls()
            client.login(settings.invitation_smtp_username, settings.invitation_smtp_password)
            client.send_message(email)
    except Exception as exc:
        logger.warning(
            "Transactional email delivery failed.",
            extra={"to_domain": _safe_domain(to_email), "error_type": exc.__class__.__name__},
        )
        raise InvitationEmailError("Email delivery failed.") from exc


def _validate_smtp_runtime_settings() -> None:
    missing = []
    if not settings.invitation_smtp_host.strip():
        missing.append("INVITATION_SMTP_HOST")
    if not settings.invitation_smtp_username.strip():
        missing.append("INVITATION_SMTP_USERNAME")
    if not settings.invitation_smtp_password.strip():
        missing.append("INVITATION_SMTP_PASSWORD")
    if not settings.invitation_smtp_from_address.strip():
        missing.append("INVITATION_SMTP_FROM_ADDRESS")
    if missing:
        raise InvitationEmailError(f"Incomplete invitation SMTP configuration: {', '.join(missing)}.")


def _safe_domain(email: str) -> str:
    return email.rsplit("@", 1)[-1] if "@" in email else "invalid"
