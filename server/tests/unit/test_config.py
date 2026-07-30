import pytest
from app.config import Settings
from pydantic import ValidationError


def test_development_settings_allow_empty_secrets() -> None:
    settings = Settings(_env_file=None)

    assert settings.app_env == "development"
    assert settings.max_room_players == 20
    assert settings.deepseek_api_key.get_secret_value() == ""


def test_uppercase_environment_variables_are_loaded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_PORT", "9000")

    settings = Settings(_env_file=None)

    assert settings.app_port == 9000


def test_production_settings_require_secrets() -> None:
    with pytest.raises(ValidationError, match="SESSION_SIGNING_KEY"):
        Settings(app_env="production", _env_file=None)


def test_production_settings_accept_required_secrets() -> None:
    settings = Settings(
        app_env="production",
        session_signing_key="x" * 32,
        admin_password_hash="$argon2id$example",
        deepseek_api_key="secret",
        _env_file=None,
    )

    assert settings.app_env == "production"
