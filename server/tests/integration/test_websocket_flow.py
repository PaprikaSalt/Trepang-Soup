import asyncio
from typing import Any, cast

from app.api.websocket import room_websocket
from app.config import Settings
from app.domain.models import Difficulty, PuzzleSource, PuzzleStyle, RoomStage
from app.main import create_app
from app.protocol.constants import CommandType
from app.protocol.models import ClientCommand
from app.rooms.manager import RoomManager
from fastapi import FastAPI, WebSocket
from starlette.websockets import WebSocketDisconnect


class FakeWebSocket:
    def __init__(self, app: FastAPI, incoming: list[dict[str, Any]]) -> None:
        self.app = app
        self.incoming = incoming
        self.sent: list[dict[str, Any]] = []
        self.accepted = False
        self.close_code: int | None = None

    async def accept(self) -> None:
        self.accepted = True

    async def receive_json(self) -> dict[str, Any]:
        if self.incoming:
            return self.incoming.pop(0)
        await asyncio.sleep(0.01)
        raise WebSocketDisconnect(code=1000)

    async def send_json(self, data: dict[str, Any]) -> None:
        self.sent.append(data)

    async def close(self, code: int = 1000) -> None:
        self.close_code = code


def wire_command(
    *,
    room_id: str,
    token: str,
    command_id: str,
    command_type: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "protocolVersion": 1,
        "commandId": command_id,
        "type": command_type,
        "roomId": room_id,
        "sessionToken": token,
        "clientTime": 1,
        "payload": payload,
    }


async def create_test_room() -> tuple[FastAPI, RoomManager, str, str, str]:
    application = create_app()
    manager = RoomManager(Settings(app_env="test", _env_file=None))
    application.state.room_manager = manager
    room, player, token, _ = await manager.create_room(
        nickname="海盐",
        source=PuzzleSource.AI,
        difficulty=Difficulty.BEGINNER,
        style=PuzzleStyle.CLASSIC_MYSTERY,
    )
    return application, manager, room.id, player.id, token


async def test_websocket_hello_snapshot_and_room_start() -> None:
    application, manager, room_id, _, token = await create_test_room()
    websocket = FakeWebSocket(
        application,
        [
            wire_command(
                room_id=room_id,
                token=token,
                command_id="cmd_hello",
                command_type="session.hello",
                payload={"lastEventId": 0, "clientVersion": "0.1.0"},
            ),
            wire_command(
                room_id=room_id,
                token=token,
                command_id="cmd_start",
                command_type="room.start",
                payload={},
            ),
        ],
    )

    await room_websocket(cast(WebSocket, websocket), room_id)

    event_types = [event["type"] for event in websocket.sent]
    assert websocket.accepted is True
    assert "room.snapshot" in event_types
    assert "room.started" in event_types
    snapshot = next(event for event in websocket.sent if event["type"] == "room.snapshot")
    assert "truth" not in str(snapshot)
    assert manager.rooms[room_id].stage is RoomStage.PLAYING


async def test_websocket_rejects_invalid_session() -> None:
    application, _, room_id, _, _ = await create_test_room()
    websocket = FakeWebSocket(
        application,
        [
            wire_command(
                room_id=room_id,
                token="invalid-token",
                command_id="cmd_hello",
                command_type="session.hello",
                payload={"lastEventId": 0, "clientVersion": "0.1.0"},
            )
        ],
    )

    await room_websocket(cast(WebSocket, websocket), room_id)

    assert websocket.sent[0]["type"] == "session.rejected"
    assert websocket.sent[0]["payload"]["error"]["code"] == "SESSION_INVALID"
    assert websocket.close_code == 4401


async def test_websocket_replays_events_after_last_event_id() -> None:
    application, manager, room_id, player_id, token = await create_test_room()
    room = manager.rooms[room_id]
    await room.execute_command(
        player_id,
        ClientCommand(
            protocol_version=1,
            command_id="cmd_start",
            type=CommandType.ROOM_START,
            room_id=room_id,
            session_token="unused-direct-token",
            client_time=1,
            payload={},
        ),
    )
    await room.execute_command(
        player_id,
        ClientCommand(
            protocol_version=1,
            command_id="cmd_discussion",
            type=CommandType.DISCUSSION_SEND,
            room_id=room_id,
            session_token="unused-direct-token",
            client_time=1,
            payload={"content": "我觉得灯光是信号。"},
        ),
    )
    websocket = FakeWebSocket(
        application,
        [
            wire_command(
                room_id=room_id,
                token=token,
                command_id="cmd_hello",
                command_type="session.hello",
                payload={"lastEventId": 1, "clientVersion": "0.1.0"},
            )
        ],
    )

    await room_websocket(cast(WebSocket, websocket), room_id)

    assert websocket.sent[0]["type"] == "discussion.created"
    assert all(event["type"] != "room.snapshot" for event in websocket.sent)


async def test_websocket_single_player_rematch_restarts_same_room() -> None:
    application, manager, room_id, _, token = await create_test_room()
    websocket = FakeWebSocket(
        application,
        [
            wire_command(
                room_id=room_id,
                token=token,
                command_id="cmd_hello_rematch",
                command_type="session.hello",
                payload={"lastEventId": 0, "clientVersion": "1.5.0"},
            ),
            wire_command(
                room_id=room_id,
                token=token,
                command_id="cmd_start_rematch",
                command_type="room.start",
                payload={},
            ),
            wire_command(
                room_id=room_id,
                token=token,
                command_id="cmd_settle_rematch",
                command_type="conclusion.give_up",
                payload={},
            ),
        ],
    )

    await room_websocket(cast(WebSocket, websocket), room_id)
    room = manager.rooms[room_id]
    while room.background_tasks:
        await asyncio.gather(*tuple(room.background_tasks))

    # A real client only exposes rematch voting after receiving game.settled.
    vote_websocket = FakeWebSocket(
        application,
        [
            wire_command(
                room_id=room_id,
                token=token,
                command_id="cmd_hello_vote",
                command_type="session.hello",
                payload={"lastEventId": room.event_sequence, "clientVersion": "1.5.0"},
            ),
            wire_command(
                room_id=room_id,
                token=token,
                command_id="cmd_vote_rematch",
                command_type="rematch.vote",
                payload={"agree": True},
            ),
        ],
    )
    await room_websocket(cast(WebSocket, vote_websocket), room_id)

    event_types = [event["type"] for event in websocket.sent + vote_websocket.sent]
    assert "game.settled" in event_types
    assert "rematch.updated" in event_types
    assert "rematch.generating" in event_types
    assert "room.restarted" in event_types
    assert manager.rooms[room_id].stage is RoomStage.PLAYING
    assert manager.rooms[room_id].round_number == 2
