import asyncio
import json
from typing import Any

import pytest
from app.ai.host import DeterministicHostService, HostService
from app.config import Settings
from app.domain.errors import DomainError
from app.domain.models import (
    AnswerType,
    Difficulty,
    HostAnswer,
    PuzzleSource,
    PuzzleStyle,
    Question,
    RoomStage,
    RuntimePuzzle,
)
from app.protocol.constants import CommandType, EventType
from app.protocol.models import ClientCommand
from app.rooms.manager import RoomManager
from app.rooms.room import Room


def command(
    room: Room,
    command_id: str,
    command_type: CommandType,
    payload: dict[str, Any] | None = None,
) -> ClientCommand:
    return ClientCommand(
        protocol_version=1,
        command_id=command_id,
        type=command_type,
        room_id=room.id,
        session_token="test-session-token",
        client_time=1,
        payload=payload or {},
    )


async def create_room(host_service: HostService | None = None) -> tuple[Room, str]:
    manager = RoomManager(
        Settings(app_env="test", _env_file=None),
        host_service=host_service,
    )
    room, player, _, _ = await manager.create_room(
        nickname="海盐",
        source=PuzzleSource.AI,
        difficulty=Difficulty.BEGINNER,
        style=PuzzleStyle.CLASSIC_MYSTERY,
    )
    return room, player.id


async def start_room(room: Room, player_id: str) -> None:
    outcome = await room.execute_command(
        player_id,
        command(room, "cmd_start", CommandType.ROOM_START),
    )
    assert outcome.events[0].type is EventType.ROOM_STARTED


async def wait_for_background_jobs(room: Room) -> None:
    while room.background_tasks:
        await asyncio.gather(*tuple(room.background_tasks))


async def test_room_start_and_discussion_are_idempotent() -> None:
    room, player_id = await create_room()
    await start_room(room, player_id)
    discussion_command = command(
        room,
        "cmd_discussion",
        CommandType.DISCUSSION_SEND,
        {"content": "  灯光可能是信号。  "},
    )

    first = await room.execute_command(player_id, discussion_command)
    duplicate = await room.execute_command(player_id, discussion_command)

    assert first.duplicate is False
    assert duplicate.duplicate is True
    assert duplicate.events == first.events
    assert len(room.discussions) == 1
    assert room.discussions[0].content == "灯光可能是信号。"


async def test_playing_snapshot_never_contains_truth() -> None:
    room, player_id = await create_room()
    await start_room(room, player_id)

    snapshot = room.snapshot_payload(player_id)
    serialized = json.dumps(snapshot, ensure_ascii=False)

    assert snapshot["puzzleSurface"]["surface"] == room.puzzle.surface
    assert room.puzzle.truth not in serialized
    assert "keyFacts" not in serialized


async def test_question_worker_answers_queued_questions_in_order() -> None:
    room, player_id = await create_room()
    await start_room(room, player_id)

    await room.execute_command(
        player_id,
        command(
            room,
            "cmd_question_one",
            CommandType.QUESTION_SUBMIT,
            {
                "clientQuestionId": "local_question_one",
                "content": "门缝里的灯光是信号吗？",
            },
        ),
    )
    await room.execute_command(
        player_id,
        command(
            room,
            "cmd_question_two",
            CommandType.QUESTION_SUBMIT,
            {
                "clientQuestionId": "local_question_two",
                "content": "她是假装钥匙丢了吗？",
            },
        ),
    )
    assert room.question_worker_task is not None
    await room.question_worker_task

    assert [item.status for item in room.questions] == ["answered", "answered"]
    answered_events = [
        event for event in room.recent_events if event.type is EventType.QUESTION_ANSWERED
    ]
    assert [event.payload["question"]["id"] for event in answered_events] == [
        room.questions[0].id,
        room.questions[1].id,
    ]


class ConcurrencyRecordingHost(DeterministicHostService):
    def __init__(self) -> None:
        self.active_calls = 0
        self.max_active_calls = 0

    async def answer_question(
        self,
        puzzle: RuntimePuzzle,
        answered_questions: list[Question],
        content: str,
    ) -> HostAnswer:
        del puzzle, answered_questions, content
        self.active_calls += 1
        self.max_active_calls = max(self.max_active_calls, self.active_calls)
        try:
            await asyncio.sleep(0.01)
            return HostAnswer(AnswerType.YES, "是。")
        finally:
            self.active_calls -= 1


async def test_concurrent_question_submissions_use_one_ai_call_at_a_time() -> None:
    host = ConcurrencyRecordingHost()
    room, player_id = await create_room(host)
    await start_room(room, player_id)

    await asyncio.gather(
        *(
            room.execute_command(
                player_id,
                command(
                    room,
                    f"cmd_question_{index}",
                    CommandType.QUESTION_SUBMIT,
                    {
                        "clientQuestionId": f"local_question_{index}",
                        "content": f"这是第 {index} 个问题吗？",
                    },
                ),
            )
            for index in range(5)
        )
    )
    assert room.question_worker_task is not None
    await room.question_worker_task

    assert host.max_active_calls == 1
    assert len(room.questions) == 5


class BlockingHost(DeterministicHostService):
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def answer_question(
        self,
        puzzle: RuntimePuzzle,
        answered_questions: list[Question],
        content: str,
    ) -> HostAnswer:
        del puzzle, answered_questions, content
        self.started.set()
        await self.release.wait()
        return HostAnswer(AnswerType.YES, "是。")


class FlakyHost(DeterministicHostService):
    def __init__(self) -> None:
        self.calls = 0

    async def answer_question(
        self,
        puzzle: RuntimePuzzle,
        answered_questions: list[Question],
        content: str,
    ) -> HostAnswer:
        del puzzle, answered_questions, content
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("temporary model failure")
        return HostAnswer(AnswerType.YES, "是。")


async def test_question_queue_continues_after_ai_failure() -> None:
    host = FlakyHost()
    room, player_id = await create_room(host)
    await start_room(room, player_id)
    for index in range(2):
        await room.execute_command(
            player_id,
            command(
                room,
                f"cmd_flaky_{index}",
                CommandType.QUESTION_SUBMIT,
                {
                    "clientQuestionId": f"local_flaky_{index}",
                    "content": f"第 {index} 个问题？",
                },
            ),
        )
    assert room.question_worker_task is not None
    await room.question_worker_task

    assert [item.status for item in room.questions] == ["failed", "answered"]
    assert host.calls == 2


async def test_only_queued_question_can_be_cancelled() -> None:
    host = BlockingHost()
    room, player_id = await create_room(host)
    await start_room(room, player_id)
    await room.execute_command(
        player_id,
        command(
            room,
            "cmd_question_thinking",
            CommandType.QUESTION_SUBMIT,
            {
                "clientQuestionId": "local_thinking",
                "content": "第一个问题？",
            },
        ),
    )
    await host.started.wait()
    await room.execute_command(
        player_id,
        command(
            room,
            "cmd_question_queued",
            CommandType.QUESTION_SUBMIT,
            {
                "clientQuestionId": "local_queued",
                "content": "第二个问题？",
            },
        ),
    )

    cancelled = await room.execute_command(
        player_id,
        command(
            room,
            "cmd_cancel_queued",
            CommandType.QUESTION_CANCEL,
            {"questionId": room.questions[1].id},
        ),
    )
    with pytest.raises(DomainError, match="不能撤回"):
        await room.execute_command(
            player_id,
            command(
                room,
                "cmd_cancel_thinking",
                CommandType.QUESTION_CANCEL,
                {"questionId": room.questions[0].id},
            ),
        )
    host.release.set()
    assert room.question_worker_task is not None
    await room.question_worker_task

    assert cancelled.events[0].type is EventType.QUESTION_CANCELLED
    assert room.questions[1].status == "cancelled"


async def test_hint_is_idempotent_and_penalty_applies_once() -> None:
    room, player_id = await create_room()
    await start_room(room, player_id)
    hint_command = command(room, "cmd_hint", CommandType.HINT_REQUEST)

    await room.execute_command(player_id, hint_command)
    await wait_for_background_jobs(room)
    duplicate = await room.execute_command(player_id, hint_command)

    assert room.hint_count == 1
    assert duplicate.duplicate is True
    assert [event.type for event in duplicate.events] == [
        EventType.HINT_THINKING,
        EventType.HINT_CREATED,
    ]


async def test_correct_conclusion_settles_and_reveals_truth() -> None:
    room, player_id = await create_room()
    await start_room(room, player_id)

    await room.execute_command(
        player_id,
        command(
            room,
            "cmd_conclusion",
            CommandType.CONCLUSION_SUBMIT,
            {
                "content": (
                    "室友被坏人挟持，用灯光闪烁求救。林夏故意假装钥匙丢了骗过屋里的人，然后报警。"
                )
            },
        ),
    )
    await wait_for_background_jobs(room)

    assert room.stage is RoomStage.SETTLEMENT
    settled = next(event for event in room.recent_events if event.type is EventType.GAME_SETTLED)
    assert settled.payload["truth"] == room.puzzle.truth
    assert room.snapshot_payload(player_id)["settlement"]["truth"] == room.puzzle.truth
