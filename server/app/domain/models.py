from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class RoomStage(StrEnum):
    LOBBY = "lobby"
    PLAYING = "playing"
    SETTLEMENT = "settlement"
    CLOSED = "closed"


class RematchStatus(StrEnum):
    VOTING = "voting"
    GENERATING = "generating"


class PuzzleSource(StrEnum):
    AI = "ai"
    LIBRARY = "library"


class Difficulty(StrEnum):
    BEGINNER = "beginner"
    STANDARD = "standard"
    HARD = "hard"


class PuzzleStyle(StrEnum):
    LIGHT_DAILY = "light_daily"
    CLASSIC_MYSTERY = "classic_mystery"
    DARK_THRILLER = "dark_thriller"
    ABSURD_HUMOR = "absurd_humor"


class QuestionStatus(StrEnum):
    QUEUED = "queued"
    THINKING = "thinking"
    ANSWERED = "answered"
    CANCELLED = "cancelled"
    FAILED = "failed"


class AnswerType(StrEnum):
    YES = "yes"
    NO = "no"
    IRRELEVANT = "irrelevant"
    PARTIAL = "partial"
    CANNOT_REVEAL = "cannot_reveal"


@dataclass(slots=True)
class Player:
    id: str
    nickname: str
    normalized_nickname: str
    joined_at: int
    online: bool = False
    connection_count: int = 0


@dataclass(frozen=True, slots=True)
class RuntimePuzzle:
    id: str
    title: str
    surface: str
    truth: str
    key_facts: tuple[str, ...]


@dataclass(slots=True)
class Question:
    id: str
    author_id: str
    author_name: str
    content: str
    created_at: int
    status: QuestionStatus = QuestionStatus.QUEUED
    answer_type: AnswerType | None = None
    answer: str | None = None

    def public_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "authorId": self.author_id,
            "authorName": self.author_name,
            "content": self.content,
            "createdAt": self.created_at,
            "status": self.status,
        }
        if self.answer_type is not None:
            result["answerType"] = self.answer_type
        if self.answer is not None:
            result["answer"] = self.answer
        return result


@dataclass(frozen=True, slots=True)
class Discussion:
    id: str
    author_id: str
    author_name: str
    content: str
    created_at: int

    def public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "authorId": self.author_id,
            "authorName": self.author_name,
            "content": self.content,
            "createdAt": self.created_at,
        }


@dataclass(slots=True)
class Session:
    token_hash: str
    room_id: str
    player_id: str
    expires_at: int
    created_at: int
    client_instance_id: str | None = None


@dataclass(frozen=True, slots=True)
class HostAnswer:
    answer_type: AnswerType
    answer: str
    confirmed_fact: str | None = None


@dataclass(frozen=True, slots=True)
class ConclusionResult:
    result: str
    feedback: str = ""
    missing_facts: tuple[str, ...] = field(default_factory=tuple)
    missing_detail_count: int = 0
    detail_penalty: int = 0


@dataclass(frozen=True, slots=True)
class GameReviewAward:
    title: str
    recipient_player_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class GameReview:
    summary: str
    awards: tuple[GameReviewAward, ...]
