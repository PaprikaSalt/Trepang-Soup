from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import AnyHttpUrl, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SERVER_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables and server/.env."""

    model_config = SettingsConfigDict(
        env_file=SERVER_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["development", "test", "production"] = "development"
    app_host: str = "127.0.0.1"
    app_port: int = Field(default=8787, ge=1, le=65535)
    public_base_url: AnyHttpUrl = AnyHttpUrl("http://127.0.0.1:8787")
    cors_allowed_origins: list[str] = Field(
        default_factory=lambda: [
            "http://127.0.0.1:1420",
            "http://localhost:1420",
            "tauri://localhost",
            "http://tauri.localhost",
        ]
    )
    database_url: str = "sqlite+aiosqlite:///./data/trepang.db"

    deepseek_api_key: SecretStr = SecretStr("")
    deepseek_base_url: AnyHttpUrl = AnyHttpUrl("https://api.deepseek.com")
    deepseek_model: str = "deepseek-chat"
    deepseek_timeout_seconds: float = Field(default=45, gt=0, le=180)

    admin_password_hash: SecretStr = SecretStr("")
    session_signing_key: SecretStr = SecretStr("")
    room_idle_seconds: int = Field(default=86_400, ge=60)
    host_transfer_seconds: int = Field(default=90, ge=10)
    max_room_players: int = Field(default=20, ge=2, le=20)
    recent_puzzle_window: int = Field(default=10, ge=0, le=100)

    @model_validator(mode="after")
    def validate_production_secrets(self) -> Self:
        if self.app_env != "production":
            return self

        signing_key = self.session_signing_key.get_secret_value()
        if len(signing_key.encode("utf-8")) < 32:
            raise ValueError("SESSION_SIGNING_KEY must contain at least 32 bytes in production")
        if not self.admin_password_hash.get_secret_value():
            raise ValueError("ADMIN_PASSWORD_HASH is required in production")
        if not self.deepseek_api_key.get_secret_value():
            raise ValueError("DEEPSEEK_API_KEY is required in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
