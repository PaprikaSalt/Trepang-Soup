from typing import Any

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.protocol.constants import (
    PROTOCOL_VERSION,
    CommandType,
    ErrorCode,
    EventType,
    ProtocolVersion,
)


def to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class ProtocolModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
        extra="forbid",
    )


class ClientCommand(ProtocolModel):
    protocol_version: ProtocolVersion
    command_id: str = Field(min_length=5, max_length=80, pattern=r"^cmd_[A-Za-z0-9_-]+$")
    type: CommandType
    room_id: str = Field(min_length=6, max_length=80, pattern=r"^room_[A-Za-z0-9_-]+$")
    session_token: SecretStr
    client_time: int = Field(ge=0)
    payload: dict[str, Any] = Field(default_factory=dict)


class ServerEvent(ProtocolModel):
    protocol_version: ProtocolVersion = PROTOCOL_VERSION
    event_id: int = Field(ge=0)
    type: EventType
    room_id: str = Field(min_length=6, max_length=80, pattern=r"^room_[A-Za-z0-9_-]+$")
    server_time: int = Field(ge=0)
    caused_by_command_id: str | None = Field(
        default=None,
        min_length=5,
        max_length=80,
        pattern=r"^cmd_[A-Za-z0-9_-]+$",
    )
    payload: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(ProtocolModel):
    code: ErrorCode
    message: str = Field(min_length=1, max_length=240)
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)
