from fastapi.testclient import TestClient
import pytest

from app.core.config import Settings
from app.main import app


client = TestClient(app)


def test_app_can_be_imported() -> None:
    assert app.title == "LeafletPilot API"


def test_health_endpoint_returns_ok() -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "LeafletPilot API",
    }


def test_config_loads_default_values(monkeypatch) -> None:
    for key in (
        "APP_NAME",
        "ENVIRONMENT",
        "DEBUG",
        "API_PREFIX",
        "BACKEND_CORS_ORIGINS",
        "DATABASE_URL",
        "TEST_DATABASE_URL",
        "LOG_LEVEL",
        "FRONTEND_BASE_URL",
        "LOCAL_STORAGE_DIR",
        "TRUSTED_HOSTS",
        "SECURE_PROXY_HEADERS",
        "JWT_SECRET_KEY",
        "JWT_ALGORITHM",
        "ACCESS_TOKEN_EXPIRE_MINUTES",
        "TELEGRAM_BOT_ENABLED",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_WEBHOOK_SECRET",
        "TELEGRAM_BOT_USERNAME",
        "TELEGRAM_WEBHOOK_BASE_URL",
        "TELEGRAM_HTTP_TIMEOUT_SECONDS",
        "TELEGRAM_HTTP_MAX_ATTEMPTS",
    ):
        monkeypatch.delenv(key, raising=False)

    settings = Settings(_env_file=None)

    assert settings.app_name == "LeafletPilot API"
    assert settings.environment == "development"
    assert settings.debug is False
    assert settings.api_prefix == "/api"
    assert settings.backend_cors_origins == ["http://localhost:5173", "http://127.0.0.1:5173"]
    assert settings.jwt_algorithm == "HS256"
    assert settings.access_token_expire_minutes == 480
    assert settings.frontend_base_url == "http://localhost:5173"
    assert settings.telegram_bot_enabled is False
    assert settings.telegram_bot_token == ""
    assert settings.telegram_http_max_attempts == 1


def test_frontend_base_url_has_single_development_default(monkeypatch) -> None:
    monkeypatch.delenv("FRONTEND_BASE_URL", raising=False)

    settings = Settings(_env_file=None)

    assert Settings.model_fields["frontend_base_url"].default == "http://localhost:5173"
    assert settings.frontend_base_url == "http://localhost:5173"


def test_health_response_exposes_no_secret_values() -> None:
    response = client.get("/api/health")
    body = response.text

    assert response.status_code == 200
    assert "JWT_SECRET_KEY" not in body
    assert "DATABASE_URL" not in body
    assert "change-this-development-secret" not in body


def test_production_rejects_debug_true(monkeypatch) -> None:
    _set_valid_production_env(monkeypatch)
    monkeypatch.setenv("DEBUG", "true")

    with pytest.raises(ValueError, match="DEBUG must be false"):
        Settings(_env_file=None)


def test_production_rejects_placeholder_jwt_secret(monkeypatch) -> None:
    _set_valid_production_env(monkeypatch)
    monkeypatch.setenv("JWT_SECRET_KEY", "change-this-development-secret")

    with pytest.raises(ValueError, match="JWT_SECRET_KEY"):
        Settings(_env_file=None)


def test_production_rejects_short_jwt_secret(monkeypatch) -> None:
    _set_valid_production_env(monkeypatch)
    monkeypatch.setenv("JWT_SECRET_KEY", "short")

    with pytest.raises(ValueError, match="at least 32"):
        Settings(_env_file=None)


def test_production_rejects_wildcard_cors(monkeypatch) -> None:
    _set_valid_production_env(monkeypatch)
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", '["*"]')

    with pytest.raises(ValueError, match="cannot include"):
        Settings(_env_file=None)


def test_production_requires_https_frontend_base_url(monkeypatch) -> None:
    _set_valid_production_env(monkeypatch)
    monkeypatch.setenv("FRONTEND_BASE_URL", "http://app.example.com")

    with pytest.raises(ValueError, match="HTTPS"):
        Settings(_env_file=None)


def test_production_requires_database_url(monkeypatch) -> None:
    _set_valid_production_env(monkeypatch)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValueError, match="DATABASE_URL is required"):
        Settings(_env_file=None)


def test_telegram_disabled_permits_empty_config(monkeypatch) -> None:
    _set_valid_production_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_ENABLED", "false")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("TELEGRAM_WEBHOOK_BASE_URL", raising=False)

    settings = Settings(_env_file=None)

    assert settings.telegram_bot_enabled is False


def test_telegram_enabled_requires_token(monkeypatch) -> None:
    _set_valid_production_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_ENABLED", "true")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "s" * 40)
    monkeypatch.setenv("TELEGRAM_WEBHOOK_BASE_URL", "https://api.example.com")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
        Settings(_env_file=None)


def test_telegram_enabled_requires_webhook_secret(monkeypatch) -> None:
    _set_valid_production_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_ENABLED", "true")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_BASE_URL", "https://api.example.com")
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)

    with pytest.raises(ValueError, match="TELEGRAM_WEBHOOK_SECRET"):
        Settings(_env_file=None)


def test_telegram_rejects_placeholder_secret_and_http_url_in_production(monkeypatch) -> None:
    _set_valid_production_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_ENABLED", "true")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "telegram-webhook-secret")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_BASE_URL", "https://api.example.com")

    with pytest.raises(ValueError, match="non-placeholder"):
        Settings(_env_file=None)

    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "s" * 40)
    monkeypatch.setenv("TELEGRAM_WEBHOOK_BASE_URL", "http://api.example.com")
    with pytest.raises(ValueError, match="HTTPS"):
        Settings(_env_file=None)


def test_telegram_rejects_invalid_timeout_and_retry(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_HTTP_TIMEOUT_SECONDS", "0")
    with pytest.raises(ValueError, match="TELEGRAM_HTTP_TIMEOUT_SECONDS"):
        Settings(_env_file=None)

    monkeypatch.setenv("TELEGRAM_HTTP_TIMEOUT_SECONDS", "20")
    monkeypatch.setenv("TELEGRAM_HTTP_MAX_ATTEMPTS", "2")
    with pytest.raises(ValueError, match="TELEGRAM_HTTP_MAX_ATTEMPTS"):
        Settings(_env_file=None)


def test_telegram_validation_error_does_not_echo_token_or_secret(monkeypatch) -> None:
    _set_valid_production_env(monkeypatch)
    token = "123:should-not-appear"
    secret = "s" * 40
    monkeypatch.setenv("TELEGRAM_BOT_ENABLED", "true")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", token)
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", secret)
    monkeypatch.setenv("TELEGRAM_WEBHOOK_BASE_URL", "http://api.example.com")

    with pytest.raises(ValueError) as exc_info:
        Settings(_env_file=None)

    assert token not in str(exc_info.value)
    assert secret not in str(exc_info.value)


def _set_valid_production_env(monkeypatch) -> None:
    for key in (
        "APP_NAME",
        "ENVIRONMENT",
        "DEBUG",
        "API_PREFIX",
        "BACKEND_CORS_ORIGINS",
        "DATABASE_URL",
        "TEST_DATABASE_URL",
        "LOG_LEVEL",
        "FRONTEND_BASE_URL",
        "LOCAL_STORAGE_DIR",
        "TRUSTED_HOSTS",
        "SECURE_PROXY_HEADERS",
        "JWT_SECRET_KEY",
        "JWT_ALGORITHM",
        "ACCESS_TOKEN_EXPIRE_MINUTES",
        "TELEGRAM_BOT_ENABLED",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_WEBHOOK_SECRET",
        "TELEGRAM_BOT_USERNAME",
        "TELEGRAM_WEBHOOK_BASE_URL",
        "TELEGRAM_HTTP_TIMEOUT_SECONDS",
        "TELEGRAM_HTTP_MAX_ATTEMPTS",
    ):
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@postgres:5432/app")
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 48)
    monkeypatch.setenv("JWT_ALGORITHM", "HS256")
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", '["https://app.example.com"]')
    monkeypatch.setenv("FRONTEND_BASE_URL", "https://app.example.com")
    monkeypatch.setenv("LOCAL_STORAGE_DIR", "/app/storage")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    monkeypatch.setenv("TRUSTED_HOSTS", '["api.example.com"]')
