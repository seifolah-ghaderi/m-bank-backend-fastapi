from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    database_url: SecretStr
    migration_database_url: SecretStr | None = None
    jwt_secret: SecretStr = Field(min_length=32)
    csrf_secret: SecretStr = Field(min_length=32)
    sms_digest_secret: SecretStr = Field(min_length=32)
    environment: Literal["dev", "staging", "production"] = "dev"
    app_timezone: str = "Asia/Tehran"
    cors_origins: list[str] = ["http://localhost:5173"]
    access_token_minutes: int = Field(default=15, ge=1)
    refresh_token_days: int = Field(default=30, ge=1)
    sms_mode: Literal["fixed", "http"] = "fixed"
    sms_url: str | None = None
    sms_api_key: SecretStr | None = None
    sms_sender: str | None = None
    sms_timeout_seconds: float = Field(default=5, gt=0, le=30)
    sms_code_ttl_seconds: int = Field(default=300, ge=30)
    sms_max_attempts: int = Field(default=5, ge=1, le=10)
    sms_resend_cooldown_seconds: int = Field(default=60, ge=1)
    import_storage_dir: Path = Path("var/imports")
    import_max_mb: int = Field(default=10, ge=1, le=10)
    import_max_rows: int = Field(default=5000, ge=1, le=5000)

    @field_validator("database_url", "migration_database_url")
    @classmethod
    def postgres_url(cls, value: SecretStr | None) -> SecretStr | None:
        if value and not value.get_secret_value().startswith("postgresql+asyncpg://"):
            raise ValueError("Use a PostgreSQL asyncpg URL")
        return value

    @field_validator("app_timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        ZoneInfo(value)
        return value

    @field_validator("cors_origins")
    @classmethod
    def exact_origins(cls, value: list[str]) -> list[str]:
        from urllib.parse import urlsplit

        for origin in value:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or "*" in origin
                or parsed.path
                or parsed.query
                or parsed.fragment
                or parsed.username
            ):
                raise ValueError("CORS origins must be exact HTTP origins without paths")
        return value

    @model_validator(mode="after")
    def production_sms(self) -> "Settings":
        if self.environment != "dev" and self.sms_mode == "fixed":
            raise ValueError("Fixed SMS mode is restricted to development")
        if self.sms_mode == "http" and (not self.sms_url or not self.sms_api_key):
            raise ValueError("HTTP SMS mode requires provider URL and credentials")
        if self.environment != "dev" and (
            not self.sms_url or not self.sms_url.startswith("https://")
        ):
            raise ValueError("Non-development SMS requires HTTPS")
        return self
