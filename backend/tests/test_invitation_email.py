from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import Settings, settings
from app.services import invitation_email
from app.services.invitation_email import (
    InvitationEmailError,
    OwnerInvitationEmail,
    build_owner_invitation_email,
    normalize_language,
    send_owner_invitation_email,
)


def _message(language: str = "en", url: str = "https://app.example.com/#/invite/token-value") -> OwnerInvitationEmail:
    return OwnerInvitationEmail(
        to_email="owner@example.com",
        market_name="Vatan Market",
        role="market_admin",
        accept_url=url,
        expires_at=datetime.now(UTC) + timedelta(days=7),
        language=language,
    )


@pytest.mark.asyncio
async def test_disabled_invitation_mail_fails_safely(monkeypatch) -> None:
    monkeypatch.setattr(settings, "invitation_email_delivery", "disabled")

    with pytest.raises(InvitationEmailError, match="not configured"):
        await send_owner_invitation_email(_message())


@pytest.mark.asyncio
async def test_fake_invitation_mail_is_development_only(monkeypatch) -> None:
    monkeypatch.setattr(settings, "invitation_email_delivery", "fake")
    monkeypatch.setattr(settings, "environment", "development")

    await send_owner_invitation_email(_message())

    monkeypatch.setattr(settings, "environment", "production")
    with pytest.raises(InvitationEmailError, match="only allowed"):
        await send_owner_invitation_email(_message())


def test_invitation_email_body_contains_activation_link_and_language_copy(monkeypatch) -> None:
    monkeypatch.setattr(settings, "invitation_smtp_from_name", "LeafletPilot")
    monkeypatch.setattr(settings, "invitation_smtp_from_address", "noreply@example.com")

    expected = {
        "tr": "LeafletPilot market aktivasyon daveti",
        "en": "LeafletPilot market activation invitation",
        "fr": "Invitation d'activation de votre marche LeafletPilot",
        "de": "LeafletPilot Einladung zur Marktaktivierung",
    }
    for language, subject in expected.items():
        email = build_owner_invitation_email(_message(language=language))
        assert email["Subject"] == subject
        assert "https://app.example.com/#/invite/token-value" in email.get_content()

    assert normalize_language("es") == "en"


@pytest.mark.asyncio
async def test_smtp_success_sends_message_without_logging_secret_or_token(monkeypatch, caplog) -> None:
    sent_messages = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            self.host = host
            self.port = port
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def starttls(self):
            return None

        def login(self, user, password):
            assert user == "mailer@example.com"
            assert password == "smtp-secret-password"

        def send_message(self, msg):
            sent_messages.append(msg)

    monkeypatch.setattr(settings, "invitation_email_delivery", "smtp")
    monkeypatch.setattr(settings, "invitation_smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "invitation_smtp_port", 587)
    monkeypatch.setattr(settings, "invitation_smtp_username", "mailer@example.com")
    monkeypatch.setattr(settings, "invitation_smtp_password", "smtp-secret-password")
    monkeypatch.setattr(settings, "invitation_smtp_from_address", "noreply@example.com")
    monkeypatch.setattr(settings, "invitation_smtp_from_name", "LeafletPilot")
    monkeypatch.setattr(settings, "invitation_smtp_security", "starttls")
    monkeypatch.setattr(settings, "invitation_smtp_timeout_seconds", 5)
    monkeypatch.setattr(invitation_email.smtplib, "SMTP", FakeSMTP)

    await send_owner_invitation_email(_message(url="https://app.example.com/#/invite/raw-token-secret"))

    assert len(sent_messages) == 1
    assert "raw-token-secret" in sent_messages[0].get_content()
    assert "smtp-secret-password" not in caplog.text
    assert "raw-token-secret" not in caplog.text


@pytest.mark.asyncio
async def test_smtp_failure_masks_error_details(monkeypatch, caplog) -> None:
    class BrokenSMTP:
        def __init__(self, host, port, timeout):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def starttls(self):
            return None

        def login(self, user, password):
            raise RuntimeError("smtp-secret-password raw-token-secret")

        def send_message(self, msg):
            raise AssertionError("send_message should not run")

    monkeypatch.setattr(settings, "invitation_email_delivery", "smtp")
    monkeypatch.setattr(settings, "invitation_smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "invitation_smtp_port", 587)
    monkeypatch.setattr(settings, "invitation_smtp_username", "mailer@example.com")
    monkeypatch.setattr(settings, "invitation_smtp_password", "smtp-secret-password")
    monkeypatch.setattr(settings, "invitation_smtp_from_address", "noreply@example.com")
    monkeypatch.setattr(settings, "invitation_smtp_from_name", "LeafletPilot")
    monkeypatch.setattr(settings, "invitation_smtp_security", "starttls")
    monkeypatch.setattr(settings, "invitation_smtp_timeout_seconds", 5)
    monkeypatch.setattr(invitation_email.smtplib, "SMTP", BrokenSMTP)

    with pytest.raises(InvitationEmailError, match="delivery failed"):
        await send_owner_invitation_email(_message(url="https://app.example.com/#/invite/raw-token-secret"))

    assert "smtp-secret-password" not in caplog.text
    assert "raw-token-secret" not in caplog.text


def test_incomplete_smtp_config_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@postgres:5432/app")
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 48)
    monkeypatch.setenv("JWT_ALGORITHM", "HS256")
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
    monkeypatch.setenv("PUBLIC_SIGNUP_THROTTLE_SECRET", "t" * 48)
    monkeypatch.setenv("PUBLIC_SIGNUP_THROTTLE_WINDOW_MINUTES", "60")
    monkeypatch.setenv("PUBLIC_SIGNUP_THROTTLE_LIMIT", "3")
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", '["https://app.example.com"]')
    monkeypatch.setenv("FRONTEND_BASE_URL", "https://app.example.com")
    monkeypatch.setenv("LOCAL_STORAGE_DIR", "/app/storage")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    monkeypatch.setenv("TRUSTED_HOSTS", '["api.example.com"]')
    monkeypatch.setenv("INVITATION_EMAIL_DELIVERY", "smtp")
    monkeypatch.setenv("INVITATION_SMTP_USERNAME", "mailer@example.com")
    monkeypatch.setenv("INVITATION_SMTP_PASSWORD", "smtp-secret-password")
    monkeypatch.setenv("INVITATION_SMTP_FROM_ADDRESS", "noreply@example.com")

    with pytest.raises(ValueError, match="INVITATION_SMTP_HOST"):
        Settings(_env_file=None)
