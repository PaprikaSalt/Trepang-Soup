import asyncio
import json
from typing import Any

import pytest
from app.ai.deepseek import AIServiceError
from app.ai.host import DeterministicHostService, HostService
from app.config import Settings
from app.domain.errors import DomainError
from app.domain.models import (
    AnswerType,
    ConclusionResult,
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
        await asyncio.gather(*tuple(room.background_tasks), return_exceptions=True)


class SequencedPuzzleGenerator:
    def __init__(self, *, fail_on_call: int | None = None) -> None:
        self.calls: list[tuple[Difficulty, PuzzleStyle]] = []
        self.fail_on_call = fail_on_call

    async def generate_puzzle(
        self,
        difficulty: Difficulty,
        style: PuzzleStyle,
    ) -> RuntimePuzzle:
        self.calls.append((difficulty, style))
        if len(self.calls) == self.fail_on_call:
            raise AIServiceError("generation failed")
        number = len(self.calls)
        return RuntimePuzzle(
            id=f"puzzle_round_{number}",
            title=f"第 {number} 轮题目",
            surface=f"这是第 {number} 轮的测试汤面，用于验证续局时题目会被完整替换。",
            truth=f"这是第 {number} 轮的完整测试汤底，只能在本轮结算之后向玩家公开。",
            key_facts=(f"第 {number} 轮事实一", f"第 {number} 轮事实二"),
        )


class BlockingRematchGenerator(SequencedPuzzleGenerator):
    def __init__(self) -> None:
        super().__init__()
        self.rematch_started = asyncio.Event()
        self.release_rematch = asyncio.Event()

    async def generate_puzzle(
        self,
        difficulty: Difficulty,
        style: PuzzleStyle,
    ) -> RuntimePuzzle:
        if self.calls:
            self.rematch_started.set()
            await self.release_rematch.wait()
        return await super().generate_puzzle(difficulty, style)


class BlockingHintHost(DeterministicHostService):
    def __init__(self) -> None:
        self.hint_started = asyncio.Event()
        self.release_hint = asyncio.Event()

    async def create_hint(
        self,
        puzzle: RuntimePuzzle,
        answered_questions: list[Question],
        hint_count: int,
    ) -> str:
        del puzzle, answered_questions, hint_count
        self.hint_started.set()
        await self.release_hint.wait()
        return "这是一条来自上一轮的迟到提示。"


class CountingConclusionHost(DeterministicHostService):
    def __init__(self) -> None:
        self.conclusion_calls = 0

    async def evaluate_conclusion(
        self,
        puzzle: RuntimePuzzle,
        content: str,
    ) -> ConclusionResult:
        self.conclusion_calls += 1
        return await super().evaluate_conclusion(puzzle, content)


async def create_multiplayer_room(
    generator: SequencedPuzzleGenerator,
) -> tuple[RoomManager, Room, str, str]:
    manager = RoomManager(
        Settings(app_env="test", _env_file=None),
        puzzle_generator=generator,
    )
    room, host, _, _ = await manager.create_room(
        nickname="海盐",
        source=PuzzleSource.AI,
        difficulty=Difficulty.BEGINNER,
        style=PuzzleStyle.CLASSIC_MYSTERY,
    )
    _, guest, _, _ = await manager.join_room(
        invite_code=room.invite_code,
        nickname="小七",
        client_instance_id="client-rematch-guest",
    )
    await start_room(room, host.id)
    return manager, room, host.id, guest.id


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


async def test_conclusion_core_gate_and_detail_confirmation_use_one_evaluation() -> None:
    host_service = CountingConclusionHost()
    room, player_id = await create_room(host_service)
    await start_room(room, player_id)

    await room.execute_command(
        player_id,
        command(
            room,
            "cmd_missing_core",
            CommandType.CONCLUSION_SUBMIT,
            {"content": "灯光是室友发出的信号，她还假装丢了钥匙。"},
        ),
    )
    await wait_for_background_jobs(room)
    rejected = room.processed_command_events["cmd_missing_core"][-1]
    assert rejected.type is EventType.CONCLUSION_REJECTED
    assert "最核心的冲突" in rejected.payload["feedback"]
    assert room.stage.value == "playing"

    content = "室友被歹徒挟持，正处于危险中。"
    await room.execute_command(
        player_id,
        command(
            room,
            "cmd_many_details",
            CommandType.CONCLUSION_SUBMIT,
            {"content": content},
        ),
    )
    await wait_for_background_jobs(room)
    confirmation = room.processed_command_events["cmd_many_details"][-1]
    assert confirmation.type is EventType.CONCLUSION_CONFIRMATION_REQUIRED
    assert confirmation.payload["missingDetailCount"] == 2
    assert confirmation.payload["scorePenalty"] == 12
    assert room.stage.value == "playing"

    await room.execute_command(
        player_id,
        command(
            room,
            "cmd_accept_detail_penalty",
            CommandType.CONCLUSION_SUBMIT,
            {"content": content, "acceptDetailPenalty": True},
        ),
    )
    await wait_for_background_jobs(room)

    assert host_service.conclusion_calls == 2
    assert room.stage is RoomStage.SETTLEMENT
    assert room.settlement is not None
    assert room.settlement["score"] == 80
    assert room.settlement["missingDetailCount"] == 2
    assert room.settlement["detailPenalty"] == 12


async def test_settlement_uses_round_contributions_and_publishes_three_awards() -> None:
    generator = SequencedPuzzleGenerator()
    manager, room, host_id, guest_id = await create_multiplayer_room(generator)
    try:
        await room.execute_command(
            guest_id,
            command(
                room,
                "cmd_guest_key_question",
                CommandType.QUESTION_SUBMIT,
                {
                    "clientQuestionId": "local_guest_key_question",
                    "content": "灯光是在主动传递求救信号吗？",
                },
            ),
        )
        await wait_for_background_jobs(room)
        await room.execute_command(
            host_id,
            command(room, "cmd_review_awards", CommandType.CONCLUSION_GIVE_UP),
        )
        await wait_for_background_jobs(room)

        assert room.settlement is not None
        assert [award["title"] for award in room.settlement["awards"]] == [
            "MVP 玩家",
            "最佳带偏奖",
            "最有价值问题",
        ]
        assert room.settlement["awards"][0]["recipientPlayerId"] == guest_id
    finally:
        await manager.shutdown()


async def test_unanimous_rematch_restarts_same_room_with_clean_round_state() -> None:
    generator = SequencedPuzzleGenerator()
    manager, room, host_id, guest_id = await create_multiplayer_room(generator)
    original_room_id = room.id
    original_invite_code = room.invite_code
    original_player_ids = set(room.players)
    try:
        await room.execute_command(
            host_id,
            command(
                room,
                "cmd_old_discussion",
                CommandType.DISCUSSION_SEND,
                {"content": "这是上一轮讨论。"},
            ),
        )
        await room.execute_command(
            host_id,
            command(
                room,
                "cmd_old_question",
                CommandType.QUESTION_SUBMIT,
                {
                    "clientQuestionId": "local_old_question",
                    "content": "灯光是信号吗？",
                },
            ),
        )
        await room.execute_command(
            host_id,
            command(room, "cmd_old_hint", CommandType.HINT_REQUEST),
        )
        await wait_for_background_jobs(room)

        settled = await room.execute_command(
            host_id,
            command(room, "cmd_settle_round_one", CommandType.CONCLUSION_GIVE_UP),
        )
        await wait_for_background_jobs(room)
        assert [event.type for event in settled.events] == [
            EventType.CONCLUSION_THINKING,
        ]
        settlement_events = room.processed_command_events["cmd_settle_round_one"]
        assert [event.type for event in settlement_events] == [
            EventType.CONCLUSION_THINKING,
            EventType.GAME_SETTLED,
            EventType.REMATCH_UPDATED,
        ]
        assert settlement_events[-1].payload == {
            "status": "voting",
            "eligiblePlayerIds": [host_id, guest_id],
            "acceptedPlayerIds": [],
        }
        snapshot = room.snapshot_payload(host_id)
        assert snapshot["room"]["roundNumber"] == 1
        assert snapshot["rematch"] == settlement_events[-1].payload

        host_vote = command(
            room,
            "cmd_rematch_host",
            CommandType.REMATCH_VOTE,
            {"agree": True},
        )
        first_vote = await room.execute_command(host_id, host_vote)
        duplicate_vote = await room.execute_command(host_id, host_vote)
        assert [event.type for event in first_vote.events] == [EventType.REMATCH_UPDATED]
        assert duplicate_vote.duplicate is True
        assert len(generator.calls) == 1

        final_vote = await room.execute_command(
            guest_id,
            command(
                room,
                "cmd_rematch_guest",
                CommandType.REMATCH_VOTE,
                {"agree": True},
            ),
        )
        assert [event.type for event in final_vote.events] == [
            EventType.REMATCH_UPDATED,
            EventType.REMATCH_GENERATING,
        ]
        await wait_for_background_jobs(room)

        assert room.id == original_room_id
        assert room.invite_code == original_invite_code
        assert set(room.players) == original_player_ids
        assert room.stage is RoomStage.PLAYING
        assert room.round_number == 2
        assert room.puzzle.id == "puzzle_round_2"
        assert len(generator.calls) == 2
        assert room.questions == []
        assert room.discussions == []
        assert room.hint_count == 0
        assert room.settlement is None
        restarted_snapshot = room.snapshot_payload(host_id)
        assert "settlement" not in restarted_snapshot
        assert "rematch" not in restarted_snapshot
        assert [item["type"] for item in restarted_snapshot["timeline"]] == [
            EventType.ROOM_RESTARTED
        ]
    finally:
        await manager.shutdown()


async def test_rematch_vote_can_be_withdrawn_and_membership_updates_eligibility() -> None:
    generator = SequencedPuzzleGenerator()
    manager, room, host_id, guest_id = await create_multiplayer_room(generator)
    try:
        await room.execute_command(
            host_id,
            command(room, "cmd_settle_members", CommandType.CONCLUSION_GIVE_UP),
        )
        await wait_for_background_jobs(room)
        await room.execute_command(
            host_id,
            command(
                room,
                "cmd_vote_then_withdraw",
                CommandType.REMATCH_VOTE,
                {"agree": True},
            ),
        )
        withdrawn = await room.execute_command(
            host_id,
            command(
                room,
                "cmd_withdraw_vote",
                CommandType.REMATCH_VOTE,
                {"agree": False},
            ),
        )
        assert withdrawn.events[0].payload["acceptedPlayerIds"] == []

        await room.execute_command(
            host_id,
            command(
                room,
                "cmd_vote_after_withdraw",
                CommandType.REMATCH_VOTE,
                {"agree": True},
            ),
        )
        _, late_player, _, _ = await manager.join_room(
            invite_code=room.invite_code,
            nickname="迟到玩家",
            client_instance_id="client-rematch-late-player",
        )
        assert room._rematch_payload() == {
            "status": "voting",
            "eligiblePlayerIds": [host_id, guest_id, late_player.id],
            "acceptedPlayerIds": [host_id],
        }

        left = await room.execute_command(
            late_player.id,
            command(room, "cmd_late_leave", CommandType.ROOM_LEAVE),
        )
        assert [event.type for event in left.events] == [
            EventType.PLAYER_LEFT,
            EventType.REMATCH_UPDATED,
        ]
        assert left.events[-1].payload["eligiblePlayerIds"] == [host_id, guest_id]

        await room.execute_command(
            guest_id,
            command(
                room,
                "cmd_vote_after_leave",
                CommandType.REMATCH_VOTE,
                {"agree": True},
            ),
        )
        await wait_for_background_jobs(room)
        assert room.stage is RoomStage.PLAYING
        assert room.round_number == 2
    finally:
        await manager.shutdown()


async def test_rematch_failure_returns_to_empty_vote_and_is_idempotent() -> None:
    generator = SequencedPuzzleGenerator(fail_on_call=2)
    manager = RoomManager(
        Settings(app_env="test", _env_file=None),
        puzzle_generator=generator,
    )
    room, host, _, _ = await manager.create_room(
        nickname="海盐",
        source=PuzzleSource.AI,
        difficulty=Difficulty.HARD,
        style=PuzzleStyle.DARK_THRILLER,
    )
    try:
        await start_room(room, host.id)
        await room.execute_command(
            host.id,
            command(room, "cmd_settle_before_failure", CommandType.CONCLUSION_GIVE_UP),
        )
        await wait_for_background_jobs(room)
        original_settlement = room.settlement
        vote = command(
            room,
            "cmd_rematch_failure",
            CommandType.REMATCH_VOTE,
            {"agree": True},
        )
        await room.execute_command(host.id, vote)
        await wait_for_background_jobs(room)

        assert room.stage is RoomStage.SETTLEMENT
        assert room.settlement is original_settlement
        assert room.puzzle.id == "puzzle_round_1"
        assert room._rematch_payload() == {
            "status": "voting",
            "eligiblePlayerIds": [host.id],
            "acceptedPlayerIds": [],
        }
        failed = next(
            event for event in room.recent_events if event.type is EventType.REMATCH_FAILED
        )
        assert failed.payload["error"]["code"] == "AI_TEMPORARILY_UNAVAILABLE"

        duplicate = await room.execute_command(host.id, vote)
        assert duplicate.duplicate is True
        assert [event.type for event in duplicate.events] == [
            EventType.REMATCH_UPDATED,
            EventType.REMATCH_GENERATING,
            EventType.REMATCH_FAILED,
        ]
        assert len(generator.calls) == 2
    finally:
        await manager.shutdown()


async def test_generating_rejects_admission_and_close_discards_late_result() -> None:
    generator = BlockingRematchGenerator()
    manager = RoomManager(
        Settings(app_env="test", _env_file=None),
        puzzle_generator=generator,
    )
    room, host, _, _ = await manager.create_room(
        nickname="海盐",
        source=PuzzleSource.AI,
        difficulty=Difficulty.BEGINNER,
        style=PuzzleStyle.CLASSIC_MYSTERY,
    )
    try:
        await start_room(room, host.id)
        await room.execute_command(
            host.id,
            command(room, "cmd_settle_before_block", CommandType.CONCLUSION_GIVE_UP),
        )
        await wait_for_background_jobs(room)
        await room.execute_command(
            host.id,
            command(
                room,
                "cmd_start_blocked_rematch",
                CommandType.REMATCH_VOTE,
                {"agree": True},
            ),
        )
        await generator.rematch_started.wait()

        generating_snapshot = room.snapshot_payload(host.id)
        assert generating_snapshot["rematch"]["status"] == "generating"
        assert "settlement" in generating_snapshot

        with pytest.raises(DomainError) as frozen_vote:
            await room.execute_command(
                host.id,
                command(
                    room,
                    "cmd_vote_while_generating",
                    CommandType.REMATCH_VOTE,
                    {"agree": False},
                ),
            )
        assert frozen_vote.value.code == "REMATCH_IN_PROGRESS"

        with pytest.raises(DomainError) as failed_join:
            await manager.join_room(
                invite_code=room.invite_code,
                nickname="生成中加入",
                client_instance_id="client-generating-join",
            )
        assert failed_join.value.code == "REMATCH_IN_PROGRESS"

        await room.execute_command(
            host.id,
            command(room, "cmd_close_during_rematch", CommandType.ROOM_CLOSE),
        )
        generator.release_rematch.set()
        await wait_for_background_jobs(room)
        assert room.stage is RoomStage.CLOSED
        assert room.round_number == 1
        assert not any(event.type is EventType.ROOM_RESTARTED for event in room.recent_events)
    finally:
        generator.release_rematch.set()
        await manager.shutdown()


async def test_player_leave_during_generation_does_not_cancel_rematch() -> None:
    generator = BlockingRematchGenerator()
    manager, room, host_id, guest_id = await create_multiplayer_room(generator)
    try:
        await room.execute_command(
            host_id,
            command(room, "cmd_settle_before_leave", CommandType.CONCLUSION_GIVE_UP),
        )
        await wait_for_background_jobs(room)
        await room.execute_command(
            host_id,
            command(
                room,
                "cmd_host_vote_before_leave",
                CommandType.REMATCH_VOTE,
                {"agree": True},
            ),
        )
        await room.execute_command(
            guest_id,
            command(
                room,
                "cmd_guest_vote_before_leave",
                CommandType.REMATCH_VOTE,
                {"agree": True},
            ),
        )
        await generator.rematch_started.wait()

        await room.execute_command(
            guest_id,
            command(room, "cmd_leave_while_generating", CommandType.ROOM_LEAVE),
        )
        generator.release_rematch.set()
        await wait_for_background_jobs(room)

        assert room.stage is RoomStage.PLAYING
        assert room.round_number == 2
        assert set(room.players) == {host_id}
    finally:
        generator.release_rematch.set()
        await manager.shutdown()


async def test_slow_hint_from_previous_round_cannot_pollute_restarted_round() -> None:
    generator = SequencedPuzzleGenerator()
    host_service = BlockingHintHost()
    manager = RoomManager(
        Settings(app_env="test", _env_file=None),
        host_service=host_service,
        puzzle_generator=generator,
    )
    room, host, _, _ = await manager.create_room(
        nickname="海盐",
        source=PuzzleSource.AI,
        difficulty=Difficulty.BEGINNER,
        style=PuzzleStyle.CLASSIC_MYSTERY,
    )
    try:
        await start_room(room, host.id)
        await room.execute_command(
            host.id,
            command(room, "cmd_slow_old_hint", CommandType.HINT_REQUEST),
        )
        await host_service.hint_started.wait()
        await room.execute_command(
            host.id,
            command(room, "cmd_settle_with_slow_hint", CommandType.CONCLUSION_GIVE_UP),
        )
        # The intentionally blocked hint remains active, so wait only for settlement.
        while room.stage is RoomStage.PLAYING:
            await asyncio.sleep(0)
        await room.execute_command(
            host.id,
            command(
                room,
                "cmd_rematch_with_slow_hint",
                CommandType.REMATCH_VOTE,
                {"agree": True},
            ),
        )
        for _ in range(20):
            if room.round_number == 2:
                break
            await asyncio.sleep(0)
        assert room.round_number == 2

        host_service.release_hint.set()
        await wait_for_background_jobs(room)
        restarted_event = next(
            event for event in room.recent_events if event.type is EventType.ROOM_RESTARTED
        )
        assert room.hint_count == 0
        assert not any(
            event.type is EventType.HINT_CREATED and event.event_id > restarted_event.event_id
            for event in room.recent_events
        )
    finally:
        host_service.release_hint.set()
        await manager.shutdown()
