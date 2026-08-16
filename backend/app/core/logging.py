import logging
import re

# Telegram Bot API embeds the bot token directly in the request path
# (https://api.telegram.org/bot<TOKEN>/<method>). httpx logs the full
# request URL at INFO level on every call, and httpx.HTTPStatusError's
# default __str__ also includes the URL -- so the token can leak either
# through httpx's own "HTTP Request: ..." log line or through an
# application exception traceback that chains an httpx error.
#
# The path segment (rather than the full "api.telegram.org/bot..." URL) is
# the anchor: at DEBUG level, httpcore's http11 tracer logs the raw request
# target (e.g. target=b'/bot<TOKEN>/sendMessage') without the host, so a
# pattern requiring the domain would miss that leak. "/bot<digits>:<token>"
# is a shape unique to Telegram's Bot API URL convention, so anchoring on it
# (rather than a specific known token value) safely catches both cases
# regardless of which logger emitted the record.
_TELEGRAM_BOT_TOKEN_RE = re.compile(r"(/bot)\d+:[A-Za-z0-9_-]+")
_TELEGRAM_BOT_TOKEN_REPLACEMENT = r"\1[REDACTED]"


class TelegramTokenRedactionFilter(logging.Filter):
    """Redacts Telegram bot tokens from log record messages and exception
    tracebacks.

    This is attached at the handler level (see `install_telegram_token_redaction`)
    so it applies to every record that reaches a handler regardless of which
    logger produced it -- third-party loggers like httpx/httpcore included --
    without requiring individual call sites to remember to redact.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted_message = _TELEGRAM_BOT_TOKEN_RE.sub(_TELEGRAM_BOT_TOKEN_REPLACEMENT, message)
        if redacted_message != message:
            record.msg = redacted_message
            record.args = ()

        if record.exc_info:
            if record.exc_text is None:
                record.exc_text = logging.Formatter().formatException(record.exc_info)
            record.exc_text = _TELEGRAM_BOT_TOKEN_RE.sub(_TELEGRAM_BOT_TOKEN_REPLACEMENT, record.exc_text)

        return True


def install_telegram_token_redaction() -> None:
    """Attaches `TelegramTokenRedactionFilter` to every handler on the root
    logger. Idempotent, so it is safe to call repeatedly (e.g. once per test)."""
    root = logging.getLogger()
    for handler in root.handlers:
        if not any(isinstance(existing, TelegramTokenRedactionFilter) for existing in handler.filters):
            handler.addFilter(TelegramTokenRedactionFilter())


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    install_telegram_token_redaction()
