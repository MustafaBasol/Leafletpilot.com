import json
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


EXAMPLE_JWT_SECRETS = {
    "change-this-development-secret",
    "secret",
    "changeme",
    "change-this-platform-secret",
    "change-this-platform-secret-at-least-32-chars",
}
EXAMPLE_TELEGRAM_SECRETS = {
    "secret",
    "changeme",
    "change-me",
    "telegram-webhook-secret",
    "example-secret",
}
EXAMPLE_SIGNUP_THROTTLE_SECRETS = {
    "change-this-signup-throttle-secret-at-least-32-chars",
    "signup-throttle-secret",
    "secret",
    "changeme",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        hide_input_in_errors=True,
    )

    app_name: str = Field(default="LeafletPilot API", alias="APP_NAME")
    environment: str = Field(default="development", alias="ENVIRONMENT")
    debug: bool = Field(default=False, alias="DEBUG")
    api_prefix: str = Field(default="/api", alias="API_PREFIX")
    backend_cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"],
        alias="BACKEND_CORS_ORIGINS",
    )
    database_url: str | None = Field(default=None, alias="DATABASE_URL")
    test_database_url: str | None = Field(default=None, alias="TEST_DATABASE_URL")
    local_storage_dir: str = Field(default="storage", alias="LOCAL_STORAGE_DIR")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    trusted_hosts: list[str] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1", "::1", "testserver"],
        alias="TRUSTED_HOSTS",
    )
    secure_proxy_headers: bool = Field(default=False, alias="SECURE_PROXY_HEADERS")
    jwt_secret_key: str = Field(
        default="change-this-development-secret",
        alias="JWT_SECRET_KEY",
    )
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(default=480, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    platform_admin_enabled: bool = Field(default=False, alias="PLATFORM_ADMIN_ENABLED")
    platform_jwt_secret: str = Field(default="", alias="PLATFORM_JWT_SECRET")
    platform_access_token_expire_minutes: int = Field(default=240, alias="PLATFORM_ACCESS_TOKEN_EXPIRE_MINUTES")
    public_signup_throttle_secret: str = Field(default="", alias="PUBLIC_SIGNUP_THROTTLE_SECRET")
    public_signup_throttle_window_minutes: int = Field(default=60, alias="PUBLIC_SIGNUP_THROTTLE_WINDOW_MINUTES")
    public_signup_throttle_limit: int = Field(default=3, alias="PUBLIC_SIGNUP_THROTTLE_LIMIT")
    frontend_base_url: str = Field(default="http://localhost:5173", alias="FRONTEND_BASE_URL")
    invitation_expire_days: int = Field(default=7, alias="INVITATION_EXPIRE_DAYS")
    telegram_bot_enabled: bool = Field(default=False, alias="TELEGRAM_BOT_ENABLED")
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_webhook_secret: str = Field(default="", alias="TELEGRAM_WEBHOOK_SECRET")
    telegram_bot_username: str = Field(default="", alias="TELEGRAM_BOT_USERNAME")
    telegram_webhook_base_url: str = Field(default="", alias="TELEGRAM_WEBHOOK_BASE_URL")
    telegram_http_timeout_seconds: int = Field(default=20, alias="TELEGRAM_HTTP_TIMEOUT_SECONDS")
    telegram_http_max_attempts: int = Field(default=1, alias="TELEGRAM_HTTP_MAX_ATTEMPTS")

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def local_storage_path(self) -> Path:
        path = Path(self.local_storage_dir)
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[2] / path
        return path.resolve()

    @field_validator("backend_cors_origins", "trusted_hosts", mode="before")
    @classmethod
    def parse_string_list(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                return json.loads(stripped)
            return [origin.strip() for origin in stripped.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def validate_security_settings(self) -> "Settings":
        normalized_log_level = self.log_level.upper()
        valid_log_levels = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}
        if normalized_log_level not in valid_log_levels:
            raise ValueError("LOG_LEVEL must be a valid Python logging level.")
        self.log_level = normalized_log_level

        if self.access_token_expire_minutes < 1:
            raise ValueError("ACCESS_TOKEN_EXPIRE_MINUTES must be at least 1.")
        if self.platform_access_token_expire_minutes < 1:
            raise ValueError("PLATFORM_ACCESS_TOKEN_EXPIRE_MINUTES must be at least 1.")
        if self.public_signup_throttle_window_minutes < 1:
            raise ValueError("PUBLIC_SIGNUP_THROTTLE_WINDOW_MINUTES must be at least 1.")
        if self.public_signup_throttle_limit < 1:
            raise ValueError("PUBLIC_SIGNUP_THROTTLE_LIMIT must be at least 1.")
        if self.telegram_http_timeout_seconds < 1 or self.telegram_http_timeout_seconds > 60:
            raise ValueError("TELEGRAM_HTTP_TIMEOUT_SECONDS must be between 1 and 60.")
        if self.telegram_http_max_attempts != 1:
            raise ValueError(
                "TELEGRAM_HTTP_MAX_ATTEMPTS must be 1. Telegram send operations are not retried automatically."
            )
        if self.telegram_bot_enabled:
            self._validate_enabled_telegram_settings()
        if self.platform_admin_enabled:
            self._validate_platform_settings()

        if "*" in self.backend_cors_origins:
            raise ValueError("BACKEND_CORS_ORIGINS cannot include '*' while CORS credentials are enabled.")

        if self.jwt_algorithm != "HS256":
            raise ValueError("JWT_ALGORITHM must be HS256.")

        if not self.is_production:
            return self

        configured_fields = self.model_fields_set
        if self.debug:
            raise ValueError("DEBUG must be false when ENVIRONMENT=production.")
        if not self.database_url:
            raise ValueError("DATABASE_URL is required when ENVIRONMENT=production.")
        if "backend_cors_origins" not in configured_fields or not self.backend_cors_origins:
            raise ValueError("BACKEND_CORS_ORIGINS must be explicitly configured in production.")
        if "local_storage_dir" not in configured_fields or not self.local_storage_dir.strip():
            raise ValueError("LOCAL_STORAGE_DIR must be explicitly configured in production.")
        if "log_level" not in configured_fields or not self.log_level:
            raise ValueError("LOG_LEVEL must be explicitly configured in production.")
        if not self.frontend_base_url:
            raise ValueError("FRONTEND_BASE_URL is required when ENVIRONMENT=production.")
        if urlparse(self.frontend_base_url).scheme != "https":
            raise ValueError("FRONTEND_BASE_URL must use HTTPS in production.")
        if len(self.jwt_secret_key) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters in production.")
        if self.jwt_secret_key.strip().lower() in EXAMPLE_JWT_SECRETS:
            raise ValueError("JWT_SECRET_KEY must not use a development or example placeholder.")
        if not self.public_signup_throttle_secret:
            raise ValueError("PUBLIC_SIGNUP_THROTTLE_SECRET is required in production.")
        if len(self.public_signup_throttle_secret) < 32:
            raise ValueError("PUBLIC_SIGNUP_THROTTLE_SECRET must be at least 32 characters in production.")
        if self.public_signup_throttle_secret.strip().lower() in EXAMPLE_SIGNUP_THROTTLE_SECRETS:
            raise ValueError("PUBLIC_SIGNUP_THROTTLE_SECRET must not use an example placeholder.")
        if not self.trusted_hosts:
            raise ValueError("TRUSTED_HOSTS must include at least one host in production.")
        if "*" in self.trusted_hosts:
            raise ValueError("TRUSTED_HOSTS cannot include '*' in production.")
        return self

    def _validate_enabled_telegram_settings(self) -> None:
        if not self.telegram_bot_token.strip():
            raise ValueError("TELEGRAM_BOT_TOKEN is required when TELEGRAM_BOT_ENABLED=true.")
        if not self.telegram_webhook_secret.strip():
            raise ValueError("TELEGRAM_WEBHOOK_SECRET is required when TELEGRAM_BOT_ENABLED=true.")
        normalized_secret = self.telegram_webhook_secret.strip().lower()
        if len(self.telegram_webhook_secret.strip()) < 32 or normalized_secret in EXAMPLE_TELEGRAM_SECRETS:
            raise ValueError("TELEGRAM_WEBHOOK_SECRET must be a strong non-placeholder value.")
        if not self.telegram_webhook_base_url.strip():
            raise ValueError("TELEGRAM_WEBHOOK_BASE_URL is required when TELEGRAM_BOT_ENABLED=true.")
        if self.is_production and urlparse(self.telegram_webhook_base_url).scheme != "https":
            raise ValueError("TELEGRAM_WEBHOOK_BASE_URL must use HTTPS in production.")

    def _validate_platform_settings(self) -> None:
        normalized_secret = self.platform_jwt_secret.strip().lower()
        if len(self.platform_jwt_secret.strip()) < 32 or normalized_secret in EXAMPLE_JWT_SECRETS:
            raise ValueError("PLATFORM_JWT_SECRET must be a strong non-placeholder value when PLATFORM_ADMIN_ENABLED=true.")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
