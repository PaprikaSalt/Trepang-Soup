import asyncio
from contextlib import suppress
from typing import Any, cast

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.domain.errors import DomainError
from app.protocol.constants import CommandType, ErrorCode, EventType
from app.protocol.models import ClientCommand, ErrorResponse, ServerEvent
from app.protocol.payloads import SessionHelloPayload
from app.protocol.validation import public_validation_errors
from app.rooms.mailbox import ConnectionMailbox
from app.rooms.manager import RoomManager
from app.rooms.room import Room, now_ms

router = APIRouter()
HANDSHAKE_TIMEOUT_SECONDS = 10


def event_json(event: ServerEvent) -> dict[str, Any]:
    return event.model_dump(mode="json")


def rejection_event(
    *,
    room_id: str,
    event_type: EventType,
    error: ErrorResponse,
    command_id: str | None = None,
    event_id: int = 0,
) -> ServerEvent:
    return ServerEvent(
        event_id=event_id,
        type=event_type,
        room_id=room_id,
        server_time=now_ms(),
        caused_by_command_id=command_id,
        payload={"error": error.model_dump(mode="json")},
    )


async def send_rejection(
    websocket: WebSocket,
    *,
    room_id: str,
    event_type: EventType,
    code: ErrorCode,
    message: str,
    command_id: str | None = None,
    event_id: int = 0,
    retryable: bool = False,
    details: dict[str, Any] | None = None,
) -> None:
    event = rejection_event(
        room_id=room_id,
        event_type=event_type,
        command_id=command_id,
        event_id=event_id,
        error=ErrorResponse(
            code=code,
            message=message,
            retryable=retryable,
            details=details or {},
        ),
    )
    await websocket.send_json(event_json(event))


@router.websocket("/api/v1/rooms/{room_id}/ws")
async def room_websocket(websocket: WebSocket, room_id: str) -> None:
    manager = cast(RoomManager, websocket.app.state.room_manager)
    await websocket.accept()

    try:
        raw_hello = await asyncio.wait_for(
            websocket.receive_json(),
            timeout=HANDSHAKE_TIMEOUT_SECONDS,
        )
        hello = ClientCommand.model_validate(raw_hello)
        if hello.type is not CommandType.SESSION_HELLO or hello.room_id != room_id:
            raise ValueError("first command must be session.hello for the requested room")
        hello_payload = SessionHelloPayload.model_validate(hello.payload)
        room, session = await manager.authenticate(
            room_id,
            hello.session_token.get_secret_value(),
        )
    except TimeoutError:
        await send_rejection(
            websocket,
            room_id=room_id,
            event_type=EventType.SESSION_REJECTED,
            code=ErrorCode.SESSION_INVALID,
            message="连接握手超时。",
        )
        await websocket.close(code=4408)
        return
    except (ValidationError, ValueError) as exc:
        await send_rejection(
            websocket,
            room_id=room_id,
            event_type=EventType.SESSION_REJECTED,
            code=ErrorCode.VALIDATION_ERROR,
            message="WebSocket 握手不符合协议。",
            details={"reason": str(exc)},
        )
        await websocket.close(code=4400)
        return
    except DomainError as exc:
        await send_rejection(
            websocket,
            room_id=room_id,
            event_type=EventType.SESSION_REJECTED,
            code=exc.code,
            message=exc.message,
            retryable=exc.retryable,
            details=exc.details,
        )
        await websocket.close(code=4401)
        return

    mailbox, initial_events = await room.connect(
        session.player_id,
        hello_payload.last_event_id,
    )
    for event in initial_events:
        await websocket.send_json(event_json(event))

    sender = asyncio.create_task(
        send_mailbox_events(websocket, mailbox),
        name=f"ws-sender:{mailbox.id}",
    )
    receiver = asyncio.create_task(
        receive_commands(
            websocket,
            manager,
            room,
            mailbox,
            session.player_id,
        ),
        name=f"ws-receiver:{mailbox.id}",
    )
    mailbox_closed = asyncio.create_task(
        mailbox.closed.wait(),
        name=f"ws-mailbox-monitor:{mailbox.id}",
    )
    tasks = {sender, receiver, mailbox_closed}
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await room.disconnect(mailbox.id)
        with suppress(RuntimeError):
            await websocket.close()


async def send_mailbox_events(
    websocket: WebSocket,
    mailbox: ConnectionMailbox,
) -> None:
    while True:
        event = await mailbox.queue.get()
        await websocket.send_json(event_json(event))


async def receive_commands(
    websocket: WebSocket,
    manager: RoomManager,
    room: Room,
    mailbox: ConnectionMailbox,
    player_id: str,
) -> None:
    while True:
        command: ClientCommand | None = None
        try:
            raw_command = await websocket.receive_json()
            command = ClientCommand.model_validate(raw_command)
            if command.room_id != room.id:
                raise DomainError(
                    ErrorCode.SESSION_INVALID,
                    "命令中的房间与当前连接不一致。",
                    status_code=401,
                )
            _, command_session = await manager.authenticate(
                room.id,
                command.session_token.get_secret_value(),
            )
            if command_session.player_id != player_id:
                raise DomainError(
                    ErrorCode.SESSION_INVALID,
                    "命令会话与当前连接的玩家不一致。",
                    status_code=401,
                )
            outcome = await room.execute_command(player_id, command)
        except WebSocketDisconnect:
            return
        except (ValidationError, ValueError) as exc:
            details = (
                {"errors": public_validation_errors(exc.errors())}
                if isinstance(exc, ValidationError)
                else {"reason": str(exc)}
            )
            await send_rejection(
                websocket,
                room_id=room.id,
                event_type=EventType.PROTOCOL_ERROR,
                code=ErrorCode.VALIDATION_ERROR,
                message="WebSocket 命令不符合协议。",
                event_id=room.event_sequence,
                details=details,
            )
            continue
        except DomainError as exc:
            command_id = command.command_id if command is not None else None
            await send_rejection(
                websocket,
                room_id=room.id,
                event_type=EventType.COMMAND_REJECTED,
                command_id=command_id,
                event_id=room.event_sequence,
                code=exc.code,
                message=exc.message,
                retryable=exc.retryable,
                details=exc.details,
            )
            continue

        if outcome.duplicate:
            for event in outcome.events:
                mailbox.offer(event)
        if outcome.close_connection:
            return
