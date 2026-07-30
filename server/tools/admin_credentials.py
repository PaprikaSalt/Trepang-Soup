"""Generate an admin verifier or answer an API login challenge."""

import argparse
import getpass
import json
import sys
from pathlib import Path
from typing import Any

from app.security.admin import (
    AdminChallenge,
    PasswordKdf,
    derive_challenge_response,
)
from pwdlib import PasswordHash


def read_password(*, confirm: bool) -> str:
    password = getpass.getpass("Admin password: ")
    if len(password) < 16:
        raise SystemExit("admin password must contain at least 16 characters")
    if confirm and password != getpass.getpass("Confirm admin password: "):
        raise SystemExit("passwords do not match")
    return password


def load_challenge(path: str) -> dict[str, Any]:
    raw = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    body = json.loads(raw)
    if not isinstance(body, dict):
        raise SystemExit("challenge input must be a JSON object")
    return body


def challenge_from_wire(body: dict[str, Any]) -> AdminChallenge:
    kdf = body.get("passwordKdf")
    if not isinstance(kdf, dict):
        raise SystemExit("challenge JSON is missing passwordKdf")
    try:
        return AdminChallenge(
            id=str(body["challengeId"]),
            nonce=str(body["nonce"]),
            issued_at=int(body["issuedAt"]),
            expires_at=int(body["expiresAt"]),
            kdf=PasswordKdf(
                salt=str(kdf["salt"]),
                time_cost=int(kdf["timeCost"]),
                memory_cost=int(kdf["memoryCost"]),
                parallelism=int(kdf["parallelism"]),
                hash_length=int(kdf["hashLength"]),
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise SystemExit("challenge JSON has invalid fields") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("hash", help="generate an Argon2id ADMIN_PASSWORD_HASH")
    response_parser = subcommands.add_parser(
        "respond",
        help="compute a one-time HMAC response for a challenge JSON document",
    )
    response_parser.add_argument(
        "--challenge-file",
        default="-",
        help="challenge JSON file, or - to read standard input",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "hash":
        print(PasswordHash.recommended().hash(read_password(confirm=True)))
        return

    challenge = challenge_from_wire(load_challenge(args.challenge_file))
    response = derive_challenge_response(read_password(confirm=False), challenge)
    print(
        json.dumps(
            {
                "challengeId": challenge.id,
                "timestamp": challenge.issued_at,
                "response": response,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
