import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from app import APP_VERSION
from app.api.health import router as health_router
from app.api.rooms import router as rooms_router
from app.api.sessions import router as sessions_router
from app.api.websocket import router as websocket_router
from app.config import get_settings
from app.domain.errors import DomainError
from app.logging import configure_logging
from app.protocol.constants import (
    PROTOCOL_VERSION,
    PROTOCOL_VERSION_HEADER,
    ErrorCode,
)
from app.protocol.models import ErrorResponse
from app.protocol.validation import public_validation_errors
from app.rooms.manager import RoomManager

logger = logging.getLogger(__name__)


def error_response(
    *,
    status_code: int,
    code: ErrorCode,
    message: str,
    retryable: bool = False,
    details: dict[str, object] | None = None,
) -> JSONResponse:
    body = ErrorResponse(
        code=code,
        message=message,
        retryable=retryable,
        details=details or {},
    )
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(body.model_dump(mode="json")),
    )


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging()
    logger.info(
        "application started",
        extra={"component": "api", "app_env": settings.app_env},
    )
    try:
        yield
    finally:
        manager = cast(RoomManager, application.state.room_manager)
        await manager.shutdown()
        logger.info("application stopped", extra={"component": "api"})


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title="Trepang Soup API",
        version=APP_VERSION,
        lifespan=lifespan,
    )
    application.state.room_manager = RoomManager(settings)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", PROTOCOL_VERSION_HEADER],
    )

    @application.middleware("http")
    async def enforce_protocol_version(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.method != "OPTIONS" and request.url.path.startswith("/api/v1"):
            received = request.headers.get(PROTOCOL_VERSION_HEADER)
            if received != str(PROTOCOL_VERSION):
                return error_response(
                    status_code=426,
                    code=ErrorCode.PROTOCOL_VERSION_UNSUPPORTED,
                    message=f"客户端协议版本不受支持，服务端要求版本 {PROTOCOL_VERSION}。",
                    details={
                        "expectedProtocolVersion": PROTOCOL_VERSION,
                        "receivedProtocolVersion": received,
                    },
                )
        return await call_next(request)

    @application.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        errors = public_validation_errors(exc.errors())
        return error_response(
            status_code=422,
            code=ErrorCode.VALIDATION_ERROR,
            message="请求内容不符合协议。",
            details={"errors": errors},
        )

    @application.exception_handler(DomainError)
    async def handle_domain_error(_: Request, exc: DomainError) -> JSONResponse:
        return error_response(
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            retryable=exc.retryable,
            details=exc.details,
        )

    application.include_router(health_router)
    application.include_router(rooms_router)
    application.include_router(sessions_router)
    application.include_router(websocket_router)
    return application


app = create_app()
