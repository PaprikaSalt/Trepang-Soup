import asyncio

import pytest
from app.ai.deepseek import AIServiceError
from app.config import Settings
from app.domain.errors import DomainError
from app.domain.models import Difficulty, PuzzleSource, PuzzleStyle, RuntimePuzzle
from app.protocol.constants import CommandType, EventType
from app.protocol.models import ClientCommand
from app.rooms.manager import RoomManager
from app.security.sessions import INVITE_ALPHABET, generate_invite_code


class RecordingPuzzleGenerator:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[tuple[Difficulty, PuzzleStyle]] = []
        self.fail = fail

    async def generate_puzzle(
        self,
        difficulty: Difficulty,
        style: PuzzleStyle,
    ) -> RuntimePuzzle:
        self.calls.append((difficulty, style))
        if self.fail:
            raise AIServiceError("generation failed")
        return RuntimePuzzle(
            id="puzzle_generated",
            title="生成题目",
            surface="这是通过注入的题目生成器生成的测试汤面，长度足够用于房间。",
            truth="这是通过注入的题目生成器生成的完整测试汤底，能够说明所有行为和因果关系。",
            key_facts=("生成事实一", "生成事实二"),
        )


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


async def test_ai_room_uses_generator_and_maps_generation_failure() -> None:
    generator = RecordingPuzzleGenerator()
    manager = RoomManager(
        Settings(app_env="test", _env_file=None),
        puzzle_generator=generator,
    )
    room, _, _, _ = await manager.create_room(
        nickname="房主",
        source=PuzzleSource.AI,
        difficulty=Difficulty.HARD,
        style=PuzzleStyle.DARK_THRILLER,
    )

    assert room.puzzle.id == "puzzle_generated"
    assert generator.calls == [(Difficulty.HARD, PuzzleStyle.DARK_THRILLER)]

    failing_manager = RoomManager(
        Settings(app_env="test", _env_file=None),
        puzzle_generator=RecordingPuzzleGenerator(fail=True),
    )
    with pytest.raises(DomainError) as failed:
        await failing_manager.create_room(
            nickname="房主",
            source=PuzzleSource.AI,
            difficulty=Difficulty.HARD,
            style=PuzzleStyle.DARK_THRILLER,
        )
    assert failed.value.code == "AI_TEMPORARILY_UNAVAILABLE"
    assert failed.value.retryable is True


async def test_deepseek_is_wired_when_api_key_is_configured() -> None:
    manager = RoomManager(
        Settings(
            app_env="test",
            deepseek_api_key="test-key",
            _env_file=None,
        )
    )
    try:
        assert id(manager.host_service) == id(manager.puzzle_generator)
        assert manager.host_service.__class__.__name__ == "DeepSeekService"
    finally:
        await manager.shutdown()


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


async def test_cleanup_removes_idle_room_invite_and_sessions() -> None:
    manager = RoomManager(
        Settings(
            app_env="test",
            room_idle_seconds=60,
            room_settlement_grace_seconds=5,
            _env_file=None,
        )
    )
    room, _, _, session = await manager.create_room(
        nickname="房主",
        source=PuzzleSource.AI,
        difficulty=Difficulty.BEGINNER,
        style=PuzzleStyle.CLASSIC_MYSTERY,
    )

    assert await manager.cleanup_once(current_time_ms=room.created_at + 59_999) == 0
    assert await manager.cleanup_once(current_time_ms=room.created_at + 60_000) == 1
    assert room.id not in manager.rooms
    assert room.invite_code not in manager.room_ids_by_invite
    assert session.token_hash not in manager.sessions


async def test_cleanup_waits_for_terminal_event_grace() -> None:
    manager = RoomManager(
        Settings(
            app_env="test",
            room_settlement_grace_seconds=5,
            _env_file=None,
        )
    )
    room, host, _, _ = await manager.create_room(
        nickname="房主",
        source=PuzzleSource.AI,
        difficulty=Difficulty.BEGINNER,
        style=PuzzleStyle.CLASSIC_MYSTERY,
    )
    await room.execute_command(
        host.id,
        ClientCommand(
            protocol_version=1,
            command_id="cmd_close",
            type=CommandType.ROOM_CLOSE,
            room_id=room.id,
            session_token="unused-direct-token",
            client_time=1,
            payload={},
        ),
    )
    assert room.closed_at is not None

    assert await manager.cleanup_once(current_time_ms=room.closed_at + 4_999) == 0
    assert await manager.cleanup_once(current_time_ms=room.closed_at + 5_000) == 1


async def test_cleanup_removes_settled_room_after_delivery_grace() -> None:
    manager = RoomManager(
        Settings(
            app_env="test",
            room_settlement_grace_seconds=2,
            _env_file=None,
        )
    )
    room, host, _, _ = await manager.create_room(
        nickname="房主",
        source=PuzzleSource.AI,
        difficulty=Difficulty.BEGINNER,
        style=PuzzleStyle.CLASSIC_MYSTERY,
    )
    for command_id, command_type in (
        ("cmd_start_settle", CommandType.ROOM_START),
        ("cmd_give_up", CommandType.CONCLUSION_GIVE_UP),
    ):
        await room.execute_command(
            host.id,
            ClientCommand(
                protocol_version=1,
                command_id=command_id,
                type=command_type,
                room_id=room.id,
                session_token="unused-direct-token",
                client_time=1,
                payload={},
            ),
        )
    assert room.settled_at is not None

    assert await manager.cleanup_once(current_time_ms=room.settled_at + 1_999) == 0
    assert await manager.cleanup_once(current_time_ms=room.settled_at + 2_000) == 1
