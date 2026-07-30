from typing import cast

from fastapi import Header, Request

from app.config import Settings
from app.domain.errors import DomainError
from app.library.repository import PuzzleRepository
from app.protocol.constants import ErrorCode
from app.rooms.manager import RoomManager
from app.security.admin import AdminAuthError, AdminAuthService


async def get_room_manager(request: Request) -> RoomManager:
    return cast(RoomManager, request.app.state.room_manager)


async def get_puzzle_repository(request: Request) -> PuzzleRepository:
    return cast(PuzzleRepository, request.app.state.puzzle_repository)


async def get_admin_auth(request: Request) -> AdminAuthService:
    return cast(AdminAuthService, request.app.state.admin_auth)


async def get_app_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def admin_domain_error(exc: AdminAuthError) -> DomainError:
    if exc.status_code == 503:
        code = ErrorCode.ADMIN_AUTH_DISABLED
    elif exc.status_code == 429:
        code = ErrorCode.ADMIN_RATE_LIMITED
    else:
        code = ErrorCode.ADMIN_AUTH_INVALID
    return DomainError(
        code,
        str(exc),
        status_code=exc.status_code,
        retryable=exc.retryable,
    )


async def require_admin(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise DomainError(
            ErrorCode.ADMIN_AUTH_REQUIRED,
            "需要有效的管理员令牌。",
            status_code=401,
        )
    auth = await get_admin_auth(request)
    try:
        auth.authenticate(authorization.removeprefix("Bearer ").strip())
    except AdminAuthError as exc:
        raise admin_domain_error(exc) from exc
