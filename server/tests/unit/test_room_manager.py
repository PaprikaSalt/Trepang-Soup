import asyncio

import pytest
from app.config import Settings
from app.domain.errors import DomainError
from app.domain.models import Difficulty, PuzzleSource, PuzzleStyle
from app.protocol.constants import CommandType, EventType
from app.protocol.models import ClientCommand
from app.rooms.manager import RoomManager
from app.security.sessions import INVITE_ALPHABET, generate_invite_code


async def test_room_capacity_is_enforced() -> None:
    manager = RoomManager(Settings(app_env="test", max_room_players=2, _env_file=None))
    room, _, _, _ = await manager.create_room(
        nickname="房主",
        source=PuzzleSource.AI,
        difficulty=Difficulty.BEGINNER,
        style=PuzzleStyle.CLASSIC_MYSTERY,
    )
    await manager.join_room(
        invite_code=room.invite_code,
        nickname="玩家一",
        client_instance_id="client-player-one",
    )

    with pytest.raises(DomainError, match="坐满"):
        await manager.join_room(
            invite_code=room.invite_code,
            nickname="玩家二",
            client_instance_id="client-player-two",
        )


def test_invite_code_uses_unambiguous_alphabet() -> None:
    for _ in range(100):
        code = generate_invite_code()
        assert len(code) == 6
        assert set(code) <= set(INVITE_ALPHABET)
        assert not set(code) & set("0O1I")


async def test_offline_host_transfers_to_earliest_online_player() -> None:
    manager = RoomManager(Settings(app_env="test", _env_file=None))
    room, host, _, _ = await manager.create_room(
        nickname="房主",
        source=PuzzleSource.AI,
        difficulty=Difficulty.BEGINNER,
        style=PuzzleStyle.CLASSIC_MYSTERY,
    )
    _, next_host, _, _ = await manager.join_room(
        invite_code=room.invite_code,
        nickname="玩家一",
        client_instance_id="client-player-one",
    )
    room.host_transfer_seconds = 0.01
    host_connection, _ = await room.connect(host.id, 0)
    next_connection, _ = await room.connect(next_host.id, 0)

    await room.disconnect(host_connection.id)
    await asyncio.sleep(0.03)

    assert room.host_player_id == next_host.id
    await room.disconnect(next_connection.id)
    if room.host_transfer_task is not None:
        room.host_transfer_task.cancel()


async def test_room_event_is_broadcast_to_two_connected_players() -> None:
    manager = RoomManager(Settings(app_env="test", _env_file=None))
    room, host, _, _ = await manager.create_room(
        nickname="房主",
        source=PuzzleSource.AI,
        difficulty=Difficulty.BEGINNER,
        style=PuzzleStyle.CLASSIC_MYSTERY,
    )
    _, guest, _, _ = await manager.join_room(
        invite_code=room.invite_code,
        nickname="玩家一",
        client_instance_id="client-player-one",
    )
    host_mailbox, _ = await room.connect(host.id, 0)
    guest_mailbox, _ = await room.connect(guest.id, 0)
    while not host_mailbox.queue.empty():
        host_mailbox.queue.get_nowait()
    while not guest_mailbox.queue.empty():
        guest_mailbox.queue.get_nowait()

    await room.execute_command(
        host.id,
        ClientCommand(
            protocol_version=1,
            command_id="cmd_start",
            type=CommandType.ROOM_START,
            room_id=room.id,
            session_token="unused-direct-token",
            client_time=1,
            payload={},
        ),
    )

    host_event = host_mailbox.queue.get_nowait()
    guest_event = guest_mailbox.queue.get_nowait()
    assert host_event.type is EventType.ROOM_STARTED
    assert guest_event == host_event
    await room.disconnect(host_mailbox.id)
    await room.disconnect(guest_mailbox.id)
    if room.host_transfer_task is not None:
        room.host_transfer_task.cancel()
