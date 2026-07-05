from fastapi.testclient import TestClient

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
    ):
        monkeypatch.delenv(key, raising=False)

    settings = Settings(_env_file=None)

    assert settings.app_name == "LeafletPilot API"
    assert settings.environment == "development"
    assert settings.debug is False
    assert settings.api_prefix == "/api"
    assert settings.backend_cors_origins == ["http://localhost:5173", "http://127.0.0.1:5173"]
