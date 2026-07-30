from typing import Any

import pytest
from app.config import Settings
from app.security.admin import (
    AdminAuthError,
    AdminAuthService,
    derive_challenge_response,
)
from pwdlib import PasswordHash


def settings(password: str = "correct horse battery staple", **overrides: Any) -> Settings:
    return Settings(
        app_env="test",
        admin_password_hash=PasswordHash.recommended().hash(password),
        _env_file=None,
        **overrides,
    )


def test_challenge_is_single_use_and_token_expires() -> None:
    now = [1_000.0]
    password = "correct horse battery staple"
    auth = AdminAuthService(settings(password, admin_token_ttl_seconds=60), clock=lambda: now[0])
    challenge = auth.create_challenge("127.0.0.1")
    response = derive_challenge_response(password, challenge)

    token, expires_at = auth.login(
        subject="127.0.0.1",
        challenge_id=challenge.id,
        timestamp=challenge.issued_at,
        response=response,
    )

    assert expires_at == 1_060
    auth.authenticate(token)
    with pytest.raises(AdminAuthError, match="无效"):
        auth.login(
            subject="127.0.0.1",
            challenge_id=challenge.id,
            timestamp=challenge.issued_at,
            response=response,
        )

    now[0] = 1_061
    with pytest.raises(AdminAuthError, match="过期"):
        auth.authenticate(token)


def test_expired_challenge_and_failed_login_rate_limit() -> None:
    now = [2_000.0]
    auth = AdminAuthService(
        settings(
            admin_challenge_ttl_seconds=10,
            admin_max_failures=2,
            admin_lockout_seconds=30,
        ),
        clock=lambda: now[0],
    )
    expired = auth.create_challenge("client")
    now[0] = 2_011
    with pytest.raises(AdminAuthError, match="无效"):
        auth.login(
            subject="client",
            challenge_id=expired.id,
            timestamp=expired.issued_at,
            response="0" * 64,
        )

    challenge = auth.create_challenge("client")
    with pytest.raises(AdminAuthError, match="无效"):
        auth.login(
            subject="client",
            challenge_id=challenge.id,
            timestamp=challenge.issued_at,
            response="0" * 64,
        )
    with pytest.raises(AdminAuthError, match="频繁") as limited:
        auth.create_challenge("client")
    assert limited.value.status_code == 429

    now[0] = 2_042
    assert auth.create_challenge("client").expires_at == 2_052


def test_auth_is_disabled_without_configured_verifier() -> None:
    auth = AdminAuthService(Settings(app_env="test", _env_file=None))
    with pytest.raises(AdminAuthError, match="尚未配置") as disabled:
        auth.create_challenge("client")
    assert disabled.value.status_code == 503
