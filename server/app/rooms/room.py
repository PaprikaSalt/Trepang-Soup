import asyncio
from collections import deque
from dataclasses import dataclass
from time import time
from typing import Any

from pydantic import ValidationError

from app.ai.host import HostService
from app.domain.errors import DomainError
from app.domain.models import (
    Difficulty,
    Discussion,
    Player,
    PuzzleSource,
    PuzzleStyle,
    Question,
    QuestionStatus,
    RoomStage,
    RuntimePuzzle,
)
from app.protocol.constants import CommandType, ErrorCode, EventType
from app.protocol.models import ClientCommand, ServerEvent
from app.protocol.payloads import (
    ConclusionSubmitPayload,
    DiscussionSendPayload,
    EmptyPayload,
    PlayerTargetPayload,
    QuestionCancelPayload,
    QuestionSubmitPayload,
)
from app.protocol.validation import public_validation_errors
from app.rooms.mailbox import ConnectionMailbox
from app.security.sessions import generate_id

EVENT_CACHE_SIZE = 500


def now_ms() -> int:
    return int(time() * 1000)


@dataclass(frozen=True, slots=True)
class CommandOutcome:
    events: tuple[ServerEvent, ...]
    duplicate: bool = False
    close_connection: bool = False


class Room:
    def __init__(
        self,
        *,
        room_id: str,
        invite_code: str,
        source: PuzzleSource,
        difficulty: Difficulty | None,
        style: PuzzleStyle | None,
        host_player: Player,
        puzzle: RuntimePuzzle,
        host_service: HostService,
        host_transfer_seconds: float,
    ) -> None:
        self.id = room_id
        self.invite_code = invite_code
        self.stage = RoomStage.LOBBY
        self.source = source
        self.difficulty = difficulty
        self.style = style
        self.host_player_id = host_player.id
        self.players: dict[str, Player] = {host_player.id: host_player}
        self.puzzle = puzzle
        self.questions: list[Question] = []
        self.discussions: list[Discussion] = []
        self.hint_count = 0
        self.settlement: dict[str, Any] | None = None
        self.created_at = now_ms()
        self.last_activity_at = self.created_at
        self.started_at: int | None = None
        self.settled_at: int | None = None
        self.closed_at: int | None = None
        self.event_sequence = 0
        self.recent_events: deque[ServerEvent] = deque(maxlen=EVENT_CACHE_SIZE)
        self.processed_command_events: dict[str, tuple[ServerEvent, ...]] = {}
        self.connections: dict[str, ConnectionMailbox] = {}
        self.lock = asyncio.Lock()
        self.host_service = host_service
        self.host_transfer_seconds = host_transfer_seconds
        self.question_worker_task: asyncio.Task[None] | None = None
        self.conclusion_command_id: str | None = None
        self.host_transfer_task: asyncio.Task[None] | None = None
        self.background_tasks: set[asyncio.Task[None]] = set()

    def _new_event(
        self,
        event_type: EventType,
        payload: dict[str, Any],
        command_id: str | None = None,
    ) -> ServerEvent:
        self.event_sequence += 1
        event = ServerEvent(
            event_id=self.event_sequence,
            type=event_type,
            room_id=self.id,
            server_time=now_ms(),
            caused_by_command_id=command_id,
            payload=payload,
        )
        self.recent_events.append(event)
        return event

    def _remember_command(self, command_id: str, events: list[ServerEvent]) -> None:
        self.processed_command_events[command_id] = tuple(events)
        if len(self.processed_command_events) > EVENT_CACHE_SIZE:
            oldest = next(iter(self.processed_command_events))
            del self.processed_command_events[oldest]

    async def broadcast(self, *events: ServerEvent) -> None:
        if not events:
            return
        for mailbox in tuple(self.connections.values()):
            for event in events:
                if not mailbox.offer(event):
                    break

    async def shutdown(self) -> None:
        for mailbox in self.connections.values():
            mailbox.closed.set()
        tasks = tuple(self.background_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self.connections.clear()

    def player_public_dict(self, player: Player) -> dict[str, Any]:
        return {
            "id": player.id,
            "nickname": player.nickname,
            "online": player.online,
            "isHost": player.id == self.host_player_id,
            "joinedAt": player.joined_at,
        }

    def snapshot_payload(self, player_id: str) -> dict[str, Any]:
        player = self.players[player_id]
        snapshot: dict[str, Any] = {
            "room": {
                "roomId": self.id,
                "inviteCode": self.invite_code,
                "stage": self.stage,
                "hostPlayerId": self.host_player_id,
                "source": self.source,
                "difficulty": self.difficulty,
                "style": self.style,
                "hintCount": self.hint_count,
                "createdAt": self.created_at,
                "startedAt": self.started_at,
            },
            "self": {"playerId": player.id, "nickname": player.nickname},
            "players": [self.player_public_dict(item) for item in self.players.values()],
            "puzzleSurface": {
                "id": self.puzzle.id,
                "title": self.puzzle.title,
                "surface": self.puzzle.surface,
            }
            if self.stage is not RoomStage.LOBBY
            else None,
            "questions": [question.public_dict() for question in self.questions],
            "timeline": [
                {
                    "eventId": event.event_id,
                    "type": event.type,
                    "createdAt": event.server_time,
                    "payload": event.payload,
                }
                for event in self.recent_events
                if event.type
                in {
                    EventType.ROOM_STARTED,
                    EventType.QUESTION_ANSWERED,
                    EventType.HINT_CREATED,
                    EventType.CONCLUSION_CLOSE,
                    EventType.CONCLUSION_REJECTED,
                }
            ],
            "discussions": [item.public_dict() for item in self.discussions],
            "lastEventId": self.event_sequence,
        }
        if self.settlement is not None:
            snapshot["settlement"] = self.settlement
        return snapshot

    async def connect(
        self,
        player_id: str,
        last_event_id: int,
    ) -> tuple[ConnectionMailbox, list[ServerEvent]]:
        async with self.lock:
            self.last_activity_at = now_ms()
            player = self.require_player(player_id)
            connection = ConnectionMailbox(
                id=generate_id("connection"),
                player_id=player_id,
            )
            self.connections[connection.id] = connection
            was_offline = not player.online
            player.connection_count += 1
            player.online = True
            if player_id == self.host_player_id and self.host_transfer_task is not None:
                self.host_transfer_task.cancel()
                self.host_transfer_task = None

            initial: list[ServerEvent]
            cached_start = self.recent_events[0].event_id if self.recent_events else None
            can_replay = (
                last_event_id > 0
                and last_event_id <= self.event_sequence
                and cached_start is not None
                and last_event_id >= cached_start - 1
            )
            if can_replay:
                initial = [event for event in self.recent_events if event.event_id > last_event_id]
            else:
                initial = [
                    ServerEvent(
                        event_id=self.event_sequence,
                        type=EventType.ROOM_SNAPSHOT,
                        room_id=self.id,
                        server_time=now_ms(),
                        payload=self.snapshot_payload(player_id),
                    )
                ]

            online_event = (
                self._new_event(
                    EventType.PLAYER_ONLINE_CHANGED,
                    {"playerId": player_id, "online": True},
                )
                if was_offline
                else None
            )
        if online_event is not None:
            await self.broadcast(online_event)
        return connection, initial

    async def disconnect(self, connection_id: str) -> None:
        async with self.lock:
            self.last_activity_at = now_ms()
            connection = self.connections.pop(connection_id, None)
            if connection is None:
                return
            connection.closed.set()
            player = self.players.get(connection.player_id)
            if player is None:
                return
            player.connection_count = max(0, player.connection_count - 1)
            if player.connection_count > 0 or not player.online:
                return
            player.online = False
            event = self._new_event(
                EventType.PLAYER_ONLINE_CHANGED,
                {"playerId": player.id, "online": False},
            )
            should_schedule_host_transfer = player.id == self.host_player_id and any(
                item.id != player.id for item in self.players.values()
            )
        await self.broadcast(event)
        if should_schedule_host_transfer:
            self._schedule_host_transfer(player.id)

    def require_player(self, player_id: str) -> Player:
        player = self.players.get(player_id)
        if player is None:
            raise DomainError(
                ErrorCode.SESSION_INVALID,
                "玩家会话不属于这个房间。",
                status_code=401,
            )
        return player

    def require_host(self, player_id: str) -> None:
        if player_id != self.host_player_id:
            raise DomainError(ErrorCode.NOT_HOST, "只有房主可以执行这个操作。", status_code=403)

    def require_stage(self, expected: RoomStage) -> None:
        if self.stage is not expected:
            raise DomainError(
                ErrorCode.INVALID_ROOM_STAGE,
                "当前房间阶段不能执行这个操作。",
                status_code=409,
                details={"expected": expected, "actual": self.stage},
            )

    async def add_player(self, player: Player) -> ServerEvent:
        async with self.lock:
            if self.stage is RoomStage.CLOSED:
                raise DomainError(ErrorCode.ROOM_CLOSING, "房间正在关闭。", status_code=409)
            self.players[player.id] = player
            event = self._new_event(
                EventType.PLAYER_JOINED,
                {"player": self.player_public_dict(player)},
            )
        await self.broadcast(event)
        return event

    async def execute_command(
        self,
        player_id: str,
        command: ClientCommand,
    ) -> CommandOutcome:
        start_question_worker = False
        async_job: tuple[str, str] | None = None
        close_connection = False

        async with self.lock:
            self.last_activity_at = now_ms()
            self.require_player(player_id)
            duplicate_events = self.processed_command_events.get(command.command_id)
            if duplicate_events is not None:
                return CommandOutcome(events=duplicate_events, duplicate=True)

            events: list[ServerEvent] = []
            if command.type is CommandType.ROOM_START:
                self._parse_payload(EmptyPayload, command.payload)
                self.require_host(player_id)
                self.require_stage(RoomStage.LOBBY)
                self.stage = RoomStage.PLAYING
                self.started_at = now_ms()
                events.append(
                    self._new_event(
                        EventType.ROOM_STARTED,
                        {
                            "startedAt": self.started_at,
                            "puzzleSurface": {
                                "id": self.puzzle.id,
                                "title": self.puzzle.title,
                                "surface": self.puzzle.surface,
                            },
                        },
                        command.command_id,
                    )
                )
            elif command.type is CommandType.ROOM_CLOSE:
                self._parse_payload(EmptyPayload, command.payload)
                self.require_host(player_id)
                if self.stage is RoomStage.CLOSED:
                    raise DomainError(
                        ErrorCode.ROOM_CLOSING,
                        "房间已经关闭。",
                        status_code=409,
                    )
                self.stage = RoomStage.CLOSED
                self.closed_at = now_ms()
                if self.host_transfer_task is not None:
                    self.host_transfer_task.cancel()
                    self.host_transfer_task = None
                events.append(
                    self._new_event(
                        EventType.ROOM_CLOSED,
                        {"closedByPlayerId": player_id},
                        command.command_id,
                    )
                )
            elif command.type is CommandType.ROOM_LEAVE:
                self._parse_payload(EmptyPayload, command.payload)
                events.extend(self._remove_player(player_id, command.command_id))
                close_connection = True
            elif command.type is CommandType.ROOM_KICK:
                payload = self._parse_payload(PlayerTargetPayload, command.payload)
                self.require_host(player_id)
                if payload.player_id == player_id:
                    raise DomainError(
                        ErrorCode.VALIDATION_ERROR,
                        "房主不能把自己踢出房间。",
                        status_code=422,
                    )
                target = self.require_player(payload.player_id)
                del self.players[target.id]
                events.append(
                    self._new_event(
                        EventType.PLAYER_KICKED,
                        {"playerId": target.id, "playerName": target.nickname},
                        command.command_id,
                    )
                )
            elif command.type is CommandType.DISCUSSION_SEND:
                self.require_stage(RoomStage.PLAYING)
                payload = self._parse_payload(DiscussionSendPayload, command.payload)
                content = self._clean_content(payload.content)
                player = self.require_player(player_id)
                discussion = Discussion(
                    id=generate_id("discussion"),
                    author_id=player.id,
                    author_name=player.nickname,
                    content=content,
                    created_at=now_ms(),
                )
                self.discussions.append(discussion)
                events.append(
                    self._new_event(
                        EventType.DISCUSSION_CREATED,
                        {"discussion": discussion.public_dict()},
                        command.command_id,
                    )
                )
            elif command.type is CommandType.QUESTION_SUBMIT:
                self.require_stage(RoomStage.PLAYING)
                payload = self._parse_payload(QuestionSubmitPayload, command.payload)
                content = self._clean_content(payload.content)
                player = self.require_player(player_id)
                question = Question(
                    id=generate_id("question"),
                    author_id=player.id,
                    author_name=player.nickname,
                    content=content,
                    created_at=now_ms(),
                )
                self.questions.append(question)
                events.append(
                    self._new_event(
                        EventType.QUESTION_QUEUED,
                        {
                            "question": question.public_dict(),
                            "clientQuestionId": payload.client_question_id,
                        },
                        command.command_id,
                    )
                )
                start_question_worker = True
            elif command.type is CommandType.QUESTION_CANCEL:
                self.require_stage(RoomStage.PLAYING)
                payload = self._parse_payload(QuestionCancelPayload, command.payload)
                cancel_question = next(
                    (
                        item
                        for item in self.questions
                        if item.id == payload.question_id and item.author_id == player_id
                    ),
                    None,
                )
                if cancel_question is None:
                    raise DomainError(
                        ErrorCode.QUESTION_NOT_FOUND,
                        "没有找到可以撤回的这个问题。",
                        status_code=404,
                    )
                if cancel_question.status is not QuestionStatus.QUEUED:
                    raise DomainError(
                        ErrorCode.QUESTION_ALREADY_PROCESSING,
                        "这个问题已经交给主持人，不能撤回。",
                        status_code=409,
                    )
                cancel_question.status = QuestionStatus.CANCELLED
                events.append(
                    self._new_event(
                        EventType.QUESTION_CANCELLED,
                        {"questionId": cancel_question.id},
                        command.command_id,
                    )
                )
            elif command.type is CommandType.HINT_REQUEST:
                self.require_stage(RoomStage.PLAYING)
                self._parse_payload(EmptyPayload, command.payload)
                player = self.require_player(player_id)
                events.append(
                    self._new_event(
                        EventType.HINT_THINKING,
                        {
                            "requestedByPlayerId": player.id,
                            "requestedByName": player.nickname,
                        },
                        command.command_id,
                    )
                )
                async_job = ("hint", command.command_id)
            elif command.type is CommandType.CONCLUSION_BEGIN:
                self.require_stage(RoomStage.PLAYING)
                self._parse_payload(EmptyPayload, command.payload)
                player = self.require_player(player_id)
                events.append(
                    self._new_event(
                        EventType.CONCLUSION_THINKING,
                        {
                            "playerId": player.id,
                            "playerName": player.nickname,
                            "phase": "drafting",
                        },
                        command.command_id,
                    )
                )
            elif command.type is CommandType.CONCLUSION_SUBMIT:
                self.require_stage(RoomStage.PLAYING)
                if self.conclusion_command_id is not None:
                    raise DomainError(
                        ErrorCode.RATE_LIMITED,
                        "主持人正在判断另一份结案推理。",
                        status_code=429,
                        retryable=True,
                    )
                payload = self._parse_payload(ConclusionSubmitPayload, command.payload)
                content = self._clean_content(payload.content)
                self.conclusion_command_id = command.command_id
                events.append(
                    self._new_event(
                        EventType.CONCLUSION_THINKING,
                        {"playerId": player_id, "phase": "evaluating"},
                        command.command_id,
                    )
                )
                async_job = ("conclusion", f"{command.command_id}\0{content}")
            elif command.type is CommandType.CONCLUSION_GIVE_UP:
                self.require_stage(RoomStage.PLAYING)
                self._parse_payload(EmptyPayload, command.payload)
                events.append(self._settle(command.command_id, gave_up=True))
            else:
                raise DomainError(
                    ErrorCode.VALIDATION_ERROR,
                    "这个命令不能在房间连接中执行。",
                    status_code=422,
                )

            self._remember_command(command.command_id, events)

        await self.broadcast(*events)
        if start_question_worker:
            self.ensure_question_worker()
        if async_job is not None:
            if async_job[0] == "hint":
                self._spawn(self._complete_hint(async_job[1]))
            else:
                command_id, content = async_job[1].split("\0", maxsplit=1)
                self._spawn(self._complete_conclusion(command_id, content))
        return CommandOutcome(
            events=tuple(events),
            close_connection=close_connection,
        )

    def ensure_question_worker(self) -> None:
        if self.question_worker_task is not None and not self.question_worker_task.done():
            return
        task = asyncio.create_task(
            self._question_worker(),
            name=f"question-worker:{self.id}",
        )
        self.question_worker_task = task
        self.background_tasks.add(task)
        task.add_done_callback(self.background_tasks.discard)

    async def _question_worker(self) -> None:
        while True:
            async with self.lock:
                question = next(
                    (item for item in self.questions if item.status is QuestionStatus.QUEUED),
                    None,
                )
                if question is None or self.stage is not RoomStage.PLAYING:
                    return
                question.status = QuestionStatus.THINKING
                thinking_event = self._new_event(
                    EventType.QUESTION_THINKING,
                    {"questionId": question.id},
                )
                answered_questions = [
                    item for item in self.questions if item.status is QuestionStatus.ANSWERED
                ]
            await self.broadcast(thinking_event)

            try:
                answer = await self.host_service.answer_question(
                    self.puzzle,
                    answered_questions,
                    question.content,
                )
            except Exception:
                async with self.lock:
                    question.status = QuestionStatus.FAILED
                    result_event = self._new_event(
                        EventType.QUESTION_FAILED,
                        {
                            "questionId": question.id,
                            "error": {
                                "code": ErrorCode.AI_TEMPORARILY_UNAVAILABLE,
                                "message": "主持人暂时走神了，请稍后再问。",
                                "retryable": True,
                                "details": {},
                            },
                        },
                    )
            else:
                async with self.lock:
                    if self.stage is not RoomStage.PLAYING:
                        question.status = QuestionStatus.FAILED
                        result_event = self._new_event(
                            EventType.QUESTION_FAILED,
                            {
                                "questionId": question.id,
                                "error": {
                                    "code": ErrorCode.INVALID_ROOM_STAGE,
                                    "message": "本局已经结束，问题不再继续处理。",
                                    "retryable": False,
                                    "details": {},
                                },
                            },
                        )
                    else:
                        question.status = QuestionStatus.ANSWERED
                        question.answer_type = answer.answer_type
                        question.answer = answer.answer
                        result_event = self._new_event(
                            EventType.QUESTION_ANSWERED,
                            {"question": question.public_dict()},
                        )
            await self.broadcast(result_event)

    async def _complete_hint(self, command_id: str) -> None:
        async with self.lock:
            answered_questions = [
                item for item in self.questions if item.status is QuestionStatus.ANSWERED
            ]
            next_hint_number = self.hint_count + 1
        try:
            content = await self.host_service.create_hint(
                self.puzzle,
                answered_questions,
                next_hint_number,
            )
        except Exception:
            async with self.lock:
                event = self._new_event(
                    EventType.HINT_FAILED,
                    {
                        "error": {
                            "code": ErrorCode.AI_TEMPORARILY_UNAVAILABLE,
                            "message": "主持人暂时无法整理提示。",
                            "retryable": True,
                            "details": {},
                        }
                    },
                    command_id,
                )
                self._append_command_event(command_id, event)
        else:
            async with self.lock:
                if self.stage is not RoomStage.PLAYING:
                    event = self._new_event(
                        EventType.HINT_FAILED,
                        {
                            "error": {
                                "code": ErrorCode.INVALID_ROOM_STAGE,
                                "message": "本局已经结束，不再生成提示。",
                                "retryable": False,
                                "details": {},
                            }
                        },
                        command_id,
                    )
                else:
                    self.hint_count += 1
                    thinking = self.processed_command_events[command_id][0]
                    event = self._new_event(
                        EventType.HINT_CREATED,
                        {
                            "hintNumber": self.hint_count,
                            "requestedByPlayerId": thinking.payload["requestedByPlayerId"],
                            "requestedByName": thinking.payload["requestedByName"],
                            "content": content,
                            "scorePenalty": 7,
                        },
                        command_id,
                    )
                self._append_command_event(command_id, event)
        await self.broadcast(event)

    async def _complete_conclusion(self, command_id: str, content: str) -> None:
        try:
            result = await self.host_service.evaluate_conclusion(self.puzzle, content)
        except Exception:
            async with self.lock:
                event = self._new_event(
                    EventType.CONCLUSION_REJECTED,
                    {
                        "feedback": "主持人暂时无法判断这份推理，请稍后重试。",
                        "retryable": True,
                    },
                    command_id,
                )
                self._append_command_event(command_id, event)
        else:
            async with self.lock:
                if self.stage is not RoomStage.PLAYING:
                    event = self._new_event(
                        EventType.CONCLUSION_REJECTED,
                        {
                            "feedback": "本局已经结束，这份推理不再重复结算。",
                            "retryable": False,
                        },
                        command_id,
                    )
                elif result.result == "correct":
                    event = self._settle(command_id, gave_up=False)
                elif result.result == "close":
                    event = self._new_event(
                        EventType.CONCLUSION_CLOSE,
                        {
                            "feedback": result.feedback,
                            "missingFacts": list(result.missing_facts),
                        },
                        command_id,
                    )
                else:
                    event = self._new_event(
                        EventType.CONCLUSION_REJECTED,
                        {"feedback": result.feedback, "retryable": False},
                        command_id,
                    )
                self._append_command_event(command_id, event)
        async with self.lock:
            if self.conclusion_command_id == command_id:
                self.conclusion_command_id = None
        await self.broadcast(event)

    def _settle(self, command_id: str, *, gave_up: bool) -> ServerEvent:
        self.stage = RoomStage.SETTLEMENT
        self.settled_at = now_ms()
        self.last_activity_at = self.settled_at
        score = max(30, (56 if gave_up else 92) - self.hint_count * 7)
        grade = "S" if score >= 90 else "A" if score >= 80 else "B" if score >= 70 else "C"
        host = self.players.get(self.host_player_id)
        recipient_name = host.nickname if host is not None else "本局玩家"
        recipient_id = host.id if host is not None else self.host_player_id
        self.settlement = {
            "truth": self.puzzle.truth,
            "keyFacts": list(self.puzzle.key_facts),
            "score": score,
            "grade": grade,
            "gaveUp": gave_up,
            "summary": (
                "你们已经看清灯光、伪装和报警之间的完整因果链。"
                if not gave_up
                else "你们已经摸到真相边缘，汤底现在完整公布。"
            ),
            "awards": [
                {
                    "title": "MVP 玩家",
                    "recipientPlayerId": recipient_id,
                    "recipientName": recipient_name,
                    "reason": "带领大家持续推进了本局推理。",
                }
            ],
            "endedAt": self.settled_at,
        }
        return self._new_event(
            EventType.GAME_SETTLED,
            self.settlement,
            command_id,
        )

    def _remove_player(self, player_id: str, command_id: str) -> list[ServerEvent]:
        player = self.require_player(player_id)
        del self.players[player_id]
        events = [
            self._new_event(
                EventType.PLAYER_LEFT,
                {"playerId": player.id, "playerName": player.nickname},
                command_id,
            )
        ]
        if not self.players:
            self.stage = RoomStage.CLOSED
            self.closed_at = now_ms()
            events.append(
                self._new_event(
                    EventType.ROOM_CLOSED,
                    {"reason": "empty"},
                    command_id,
                )
            )
        elif self.host_player_id == player_id:
            if self.host_transfer_task is not None:
                self.host_transfer_task.cancel()
                self.host_transfer_task = None
            new_host = min(self.players.values(), key=lambda item: item.joined_at)
            self.host_player_id = new_host.id
            events.append(
                self._new_event(
                    EventType.ROOM_HOST_CHANGED,
                    {
                        "hostPlayerId": new_host.id,
                        "hostPlayerName": new_host.nickname,
                    },
                    command_id,
                )
            )
        return events

    def cleanup_due(
        self,
        *,
        current_time_ms: int,
        idle_seconds: float,
        terminal_grace_seconds: float,
    ) -> bool:
        terminal_at = self.closed_at or self.settled_at
        if terminal_at is not None:
            return current_time_ms >= terminal_at + int(terminal_grace_seconds * 1000)
        all_offline = all(not player.online for player in self.players.values())
        return all_offline and current_time_ms >= self.last_activity_at + int(idle_seconds * 1000)

    def _schedule_host_transfer(self, disconnected_host_id: str) -> None:
        if self.host_transfer_task is not None and not self.host_transfer_task.done():
            return
        task = asyncio.create_task(
            self._transfer_host_after_delay(disconnected_host_id),
            name=f"host-transfer:{self.id}",
        )
        self.host_transfer_task = task
        self.background_tasks.add(task)
        task.add_done_callback(self.background_tasks.discard)

    async def _transfer_host_after_delay(self, disconnected_host_id: str) -> None:
        try:
            await asyncio.sleep(self.host_transfer_seconds)
            async with self.lock:
                current_host = self.players.get(disconnected_host_id)
                if (
                    self.host_player_id != disconnected_host_id
                    or current_host is None
                    or current_host.online
                    or self.stage is RoomStage.CLOSED
                ):
                    return
                online_candidates = [
                    player
                    for player in self.players.values()
                    if player.id != disconnected_host_id and player.online
                ]
                if not online_candidates:
                    return
                new_host = min(online_candidates, key=lambda item: item.joined_at)
                self.host_player_id = new_host.id
                event = self._new_event(
                    EventType.ROOM_HOST_CHANGED,
                    {
                        "hostPlayerId": new_host.id,
                        "hostPlayerName": new_host.nickname,
                    },
                )
            await self.broadcast(event)
        finally:
            if self.host_transfer_task is asyncio.current_task():
                self.host_transfer_task = None

    def _append_command_event(self, command_id: str, event: ServerEvent) -> None:
        previous = self.processed_command_events.get(command_id, ())
        self.processed_command_events[command_id] = (*previous, event)

    def _spawn(self, coroutine: Any) -> None:
        task = asyncio.create_task(coroutine)
        self.background_tasks.add(task)
        task.add_done_callback(self.background_tasks.discard)

    @staticmethod
    def _parse_payload(model: type[Any], payload: dict[str, Any]) -> Any:
        try:
            return model.model_validate(payload)
        except ValidationError as exc:
            raise DomainError(
                ErrorCode.VALIDATION_ERROR,
                "命令内容不符合协议。",
                status_code=422,
                details={"errors": public_validation_errors(exc.errors())},
            ) from exc

    @staticmethod
    def _clean_content(content: str) -> str:
        clean = content.strip()
        if not clean:
            raise DomainError(
                ErrorCode.VALIDATION_ERROR,
                "内容不能为空。",
                status_code=422,
            )
        return clean
