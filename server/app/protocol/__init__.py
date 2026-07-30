"""Shared HTTP and WebSocket protocol primitives."""

from app.protocol.constants import PROTOCOL_VERSION, ErrorCode
from app.protocol.models import ClientCommand, ErrorResponse, ServerEvent

__all__ = [
    "PROTOCOL_VERSION",
    "ClientCommand",
    "ErrorCode",
    "ErrorResponse",
    "ServerEvent",
]
