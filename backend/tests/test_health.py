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
