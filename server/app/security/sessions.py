import hashlib
import secrets
import unicodedata

INVITE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(12).rstrip('=')}"


def generate_invite_code(length: int = 6) -> str:
    return "".join(secrets.choice(INVITE_ALPHABET) for _ in range(length))


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def normalize_nickname(nickname: str) -> tuple[str, str]:
    display = unicodedata.normalize("NFKC", nickname).strip()
    return display, display.casefold()
