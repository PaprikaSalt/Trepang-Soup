from time import time
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import Field, ValidationInfo, field_validator

from app.api.dependencies import (
    admin_domain_error,
    get_admin_auth,
    get_puzzle_repository,
    require_admin,
)
from app.domain.errors import DomainError
from app.library.models import LibraryPuzzle
from app.library.repository import (
    PuzzleConflictError,
    PuzzleNotFoundError,
    PuzzleRepository,
)
from app.protocol.constants import ErrorCode
from app.protocol.models import ProtocolModel
from app.security.admin import AdminAuthError, AdminAuthService
from app.security.sessions import generate_id

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])
AdminGuard = Annotated[None, Depends(require_admin)]


def now_ms() -> int:
    return int(time() * 1000)


class PasswordKdfResponse(ProtocolModel):
    name: Literal["argon2id"] = "argon2id"
    salt: str
    time_cost: int
    memory_cost: int
    parallelism: int
    hash_length: int


class AdminChallengeResponse(ProtocolModel):
    challenge_id: str
    nonce: str
    issued_at: int
    expires_at: int
    mac: Literal["hmac-sha256"] = "hmac-sha256"
    password_kdf: PasswordKdfResponse


class AdminLoginRequest(ProtocolModel):
    challenge_id: str = Field(min_length=20, max_length=100)
    timestamp: int = Field(ge=0)
    response: str = Field(min_length=64, max_length=64, pattern=r"^[a-fA-F0-9]{64}$")


class AdminLoginResponse(ProtocolModel):
    access_token: str
    token_type: Literal["Bearer"] = "Bearer"
    expires_at: int


class PuzzleWrite(ProtocolModel):
    title: str = Field(min_length=1, max_length=80)
    surface: str = Field(min_length=20, max_length=800)
    truth: str = Field(min_length=40, max_length=2_000)
    key_facts: list[str] = Field(min_length=2, max_length=8)
    active: bool = True

    @field_validator("title", "surface", "truth")
    @classmethod
    def validate_trimmed_text(cls, value: str, info: ValidationInfo) -> str:
        cleaned = value.strip()
        minimums = {"title": 1, "surface": 20, "truth": 40}
        minimum = minimums.get(info.field_name or "")
        if minimum is None:
            raise AssertionError("unexpected puzzle text field")
        if len(cleaned) < minimum:
            raise ValueError("text is too short after trimming")
        return cleaned

    @field_validator("key_facts")
    @classmethod
    def validate_key_facts(cls, value: list[str]) -> list[str]:
        if any(not item.strip() for item in value):
            raise ValueError("key facts must not be blank")
        cleaned = [item.strip() for item in value]
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("key facts must be unique")
        return cleaned


class PuzzleResponse(PuzzleWrite):
    id: str
    created_at: int
    updated_at: int


class PuzzleListResponse(ProtocolModel):
    items: list[PuzzleResponse]
    total: int


class PuzzleImportItem(PuzzleWrite):
    id: str = Field(pattern=r"^puzzle_[A-Za-z0-9_-]+$", min_length=8, max_length=80)
    created_at: int | None = Field(default=None, ge=0)
    updated_at: int | None = Field(default=None, ge=0)


class PuzzleImportRequest(ProtocolModel):
    mode: Literal["upsert", "replace"] = "upsert"
    puzzles: list[PuzzleImportItem] = Field(min_length=1, max_length=1_000)


class PuzzleImportResponse(ProtocolModel):
    imported: int


class PuzzleExportResponse(ProtocolModel):
    schema_version: Literal[1] = 1
    exported_at: int
    puzzles: list[PuzzleResponse]


def puzzle_response(puzzle: LibraryPuzzle) -> PuzzleResponse:
    return PuzzleResponse(
        id=puzzle.id,
        title=puzzle.title,
        surface=puzzle.surface,
        truth=puzzle.truth,
        key_facts=list(puzzle.key_facts),
        active=puzzle.active,
        created_at=puzzle.created_at,
        updated_at=puzzle.updated_at,
    )


def puzzle_error(exc: Exception) -> DomainError:
    if isinstance(exc, PuzzleNotFoundError):
        return DomainError(
            ErrorCode.PUZZLE_NOT_FOUND,
            "没有找到这个私人题目。",
            status_code=404,
        )
    return DomainError(
        ErrorCode.PUZZLE_CONFLICT,
        "私人题目 ID 已经存在。",
        status_code=409,
    )


@router.get("/challenge", response_model=AdminChallengeResponse)
async def admin_challenge(
    request: Request,
    auth: Annotated[AdminAuthService, Depends(get_admin_auth)],
) -> AdminChallengeResponse:
    subject = request.client.host if request.client is not None else "unknown"
    try:
        challenge = auth.create_challenge(subject)
    except AdminAuthError as exc:
        raise admin_domain_error(exc) from exc
    return AdminChallengeResponse(
        challenge_id=challenge.id,
        nonce=challenge.nonce,
        issued_at=challenge.issued_at,
        expires_at=challenge.expires_at,
        password_kdf=PasswordKdfResponse(
            salt=challenge.kdf.salt,
            time_cost=challenge.kdf.time_cost,
            memory_cost=challenge.kdf.memory_cost,
            parallelism=challenge.kdf.parallelism,
            hash_length=challenge.kdf.hash_length,
        ),
    )


@router.post("/login", response_model=AdminLoginResponse)
async def admin_login(
    body: AdminLoginRequest,
    request: Request,
    auth: Annotated[AdminAuthService, Depends(get_admin_auth)],
) -> AdminLoginResponse:
    subject = request.client.host if request.client is not None else "unknown"
    try:
        token, expires_at = auth.login(
            subject=subject,
            challenge_id=body.challenge_id,
            timestamp=body.timestamp,
            response=body.response,
        )
    except AdminAuthError as exc:
        raise admin_domain_error(exc) from exc
    return AdminLoginResponse(access_token=token, expires_at=expires_at)


@router.get("/puzzles", response_model=PuzzleListResponse)
async def list_puzzles(
    _: AdminGuard,
    repository: Annotated[PuzzleRepository, Depends(get_puzzle_repository)],
) -> PuzzleListResponse:
    items = [puzzle_response(item) for item in await repository.list_puzzles()]
    return PuzzleListResponse(items=items, total=len(items))


@router.post("/puzzles", response_model=PuzzleResponse, status_code=status.HTTP_201_CREATED)
async def create_puzzle(
    body: PuzzleWrite,
    _: AdminGuard,
    repository: Annotated[PuzzleRepository, Depends(get_puzzle_repository)],
) -> PuzzleResponse:
    try:
        puzzle = await repository.create_puzzle(
            puzzle_id=generate_id("puzzle"),
            title=body.title.strip(),
            surface=body.surface.strip(),
            truth=body.truth.strip(),
            key_facts=tuple(item.strip() for item in body.key_facts),
            active=body.active,
        )
    except PuzzleConflictError as exc:
        raise puzzle_error(exc) from exc
    return puzzle_response(puzzle)


@router.put("/puzzles/{puzzle_id}", response_model=PuzzleResponse)
async def update_puzzle(
    puzzle_id: str,
    body: PuzzleWrite,
    _: AdminGuard,
    repository: Annotated[PuzzleRepository, Depends(get_puzzle_repository)],
) -> PuzzleResponse:
    try:
        puzzle = await repository.update_puzzle(
            puzzle_id,
            title=body.title.strip(),
            surface=body.surface.strip(),
            truth=body.truth.strip(),
            key_facts=tuple(item.strip() for item in body.key_facts),
            active=body.active,
        )
    except PuzzleNotFoundError as exc:
        raise puzzle_error(exc) from exc
    return puzzle_response(puzzle)


@router.delete("/puzzles/{puzzle_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_puzzle(
    puzzle_id: str,
    _: AdminGuard,
    repository: Annotated[PuzzleRepository, Depends(get_puzzle_repository)],
) -> Response:
    try:
        await repository.delete_puzzle(puzzle_id)
    except PuzzleNotFoundError as exc:
        raise puzzle_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/puzzles/import", response_model=PuzzleImportResponse)
async def import_puzzles(
    body: PuzzleImportRequest,
    _: AdminGuard,
    repository: Annotated[PuzzleRepository, Depends(get_puzzle_repository)],
) -> PuzzleImportResponse:
    timestamp = now_ms()
    records = [
        LibraryPuzzle(
            id=item.id,
            title=item.title.strip(),
            surface=item.surface.strip(),
            truth=item.truth.strip(),
            key_facts=tuple(fact.strip() for fact in item.key_facts),
            active=item.active,
            # Zero is a valid imported timestamp; only omitted values receive server time.
            created_at=item.created_at if item.created_at is not None else timestamp,
            updated_at=item.updated_at if item.updated_at is not None else timestamp,
        )
        for item in body.puzzles
    ]
    imported = await repository.import_puzzles(records, replace=body.mode == "replace")
    return PuzzleImportResponse(imported=imported)


@router.get("/puzzles/export", response_model=PuzzleExportResponse)
async def export_puzzles(
    _: AdminGuard,
    repository: Annotated[PuzzleRepository, Depends(get_puzzle_repository)],
) -> PuzzleExportResponse:
    puzzles = [puzzle_response(item) for item in await repository.list_puzzles()]
    return PuzzleExportResponse(exported_at=now_ms(), puzzles=puzzles)
