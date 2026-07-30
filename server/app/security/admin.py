import base64
import hashlib
import hmac
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from time import time

from argon2.low_level import Type, hash_secret_raw

from app.config import Settings

Clock = Callable[[], float]


class AdminAuthError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int = 401,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class PasswordKdf:
    salt: str
    time_cost: int
    memory_cost: int
    parallelism: int
    hash_length: int


@dataclass(frozen=True, slots=True)
class AdminChallenge:
    id: str
    nonce: str
    issued_at: int
    expires_at: int
    kdf: PasswordKdf

    def message(self) -> bytes:
        return f"{self.id}\n{self.nonce}\n{self.issued_at}".encode()


@dataclass(slots=True)
class FailureState:
    count: int = 0
    blocked_until: int = 0


@dataclass(frozen=True, slots=True)
class AdminToken:
    token_hash: str
    expires_at: int


def _decode_unpadded(value: str) -> bytes:
    return base64.b64decode(value + "=" * (-len(value) % 4))


def _encode_unpadded(value: bytes) -> str:
    return base64.b64encode(value).decode().rstrip("=")


def parse_argon2id_verifier(encoded_hash: str) -> tuple[PasswordKdf, bytes]:
    try:
        empty, algorithm, version, parameters, salt_text, digest_text = encoded_hash.split("$")
        if empty or algorithm != "argon2id" or version != "v=19":
            raise ValueError
        parsed = {
            key: int(value)
            for key, value in (item.split("=", maxsplit=1) for item in parameters.split(","))
        }
        digest = _decode_unpadded(digest_text)
        kdf = PasswordKdf(
            salt=salt_text,
            time_cost=parsed["t"],
            memory_cost=parsed["m"],
            parallelism=parsed["p"],
            hash_length=len(digest),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("ADMIN_PASSWORD_HASH must be an Argon2id encoded hash") from exc
    return kdf, digest


def derive_challenge_response(password: str, challenge: AdminChallenge) -> str:
    kdf = challenge.kdf
    verifier = hash_secret_raw(
        secret=password.encode(),
        salt=_decode_unpadded(kdf.salt),
        time_cost=kdf.time_cost,
        memory_cost=kdf.memory_cost,
        parallelism=kdf.parallelism,
        hash_len=kdf.hash_length,
        type=Type.ID,
        version=19,
    )
    return hmac.new(verifier, challenge.message(), hashlib.sha256).hexdigest()


class AdminAuthService:
    def __init__(self, settings: Settings, *, clock: Clock = time) -> None:
        self.settings = settings
        self._clock = clock
        configured_hash = settings.admin_password_hash.get_secret_value()
        self._kdf: PasswordKdf | None = None
        self._verifier: bytes | None = None
        if configured_hash:
            self._kdf, self._verifier = parse_argon2id_verifier(configured_hash)
        self._challenges: dict[str, AdminChallenge] = {}
        self._tokens: dict[str, AdminToken] = {}
        self._failures: dict[str, FailureState] = {}

    @property
    def enabled(self) -> bool:
        return self._verifier is not None

    def create_challenge(self, subject: str) -> AdminChallenge:
        self._require_enabled()
        now = int(self._clock())
        self._prune(now)
        state = self._failures.get(subject)
        if state is not None and state.blocked_until > now:
            raise AdminAuthError(
                "管理员登录尝试过于频繁，请稍后重试。",
                status_code=429,
                retryable=True,
            )
        assert self._kdf is not None
        challenge = AdminChallenge(
            id=f"challenge_{secrets.token_urlsafe(18)}",
            nonce=secrets.token_urlsafe(32),
            issued_at=now,
            expires_at=now + self.settings.admin_challenge_ttl_seconds,
            kdf=self._kdf,
        )
        self._challenges[challenge.id] = challenge
        return challenge

    def login(
        self,
        *,
        subject: str,
        challenge_id: str,
        timestamp: int,
        response: str,
    ) -> tuple[str, int]:
        self._require_enabled()
        now = int(self._clock())
        self._prune(now)
        state = self._failures.setdefault(subject, FailureState())
        if state.blocked_until > now:
            raise AdminAuthError(
                "管理员登录尝试过于频繁，请稍后重试。",
                status_code=429,
                retryable=True,
            )

        challenge = self._challenges.pop(challenge_id, None)
        valid = challenge is not None and timestamp == challenge.issued_at
        if valid and challenge is not None:
            assert self._verifier is not None
            expected = hmac.new(
                self._verifier,
                challenge.message(),
                hashlib.sha256,
            ).hexdigest()
            valid = hmac.compare_digest(expected, response.lower())
        if not valid:
            self._record_failure(subject, now)
            raise AdminAuthError("管理员挑战响应无效。")

        self._failures.pop(subject, None)
        raw_token = secrets.token_urlsafe(32)
        expires_at = now + self.settings.admin_token_ttl_seconds
        token_hash = self._token_hash(raw_token)
        self._tokens[token_hash] = AdminToken(token_hash=token_hash, expires_at=expires_at)
        return raw_token, expires_at

    def authenticate(self, raw_token: str) -> None:
        self._require_enabled()
        now = int(self._clock())
        self._prune(now)
        token = self._tokens.get(self._token_hash(raw_token))
        if token is None or token.expires_at <= now:
            raise AdminAuthError("管理员令牌无效或已过期。")

    def _record_failure(self, subject: str, now: int) -> None:
        state = self._failures.setdefault(subject, FailureState())
        state.count += 1
        if state.count >= self.settings.admin_max_failures:
            state.count = 0
            state.blocked_until = now + self.settings.admin_lockout_seconds

    def _prune(self, now: int) -> None:
        self._challenges = {
            key: value for key, value in self._challenges.items() if value.expires_at > now
        }
        self._tokens = {key: value for key, value in self._tokens.items() if value.expires_at > now}
        self._failures = {
            key: value
            for key, value in self._failures.items()
            if value.count > 0 or value.blocked_until > now
        }

    def _require_enabled(self) -> None:
        if not self.enabled:
            raise AdminAuthError(
                "服务端尚未配置管理员凭据。",
                status_code=503,
            )

    @staticmethod
    def _token_hash(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode()).hexdigest()
