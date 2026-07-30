from enum import StrEnum
from typing import Final, Literal

type ProtocolVersion = Literal[1]
PROTOCOL_VERSION: Final[ProtocolVersion] = 1
PROTOCOL_VERSION_HEADER = "X-Protocol-Version"


class CommandType(StrEnum):
    SESSION_HELLO = "session.hello"
    ROOM_START = "room.start"
    ROOM_CLOSE = "room.close"
    ROOM_KICK = "room.kick"
    ROOM_LEAVE = "room.leave"
    DISCUSSION_SEND = "discussion.send"
    QUESTION_SUBMIT = "question.submit"
    QUESTION_CANCEL = "question.cancel"
    HINT_REQUEST = "hint.request"
    CONCLUSION_BEGIN = "conclusion.begin"
    CONCLUSION_SUBMIT = "conclusion.submit"
    CONCLUSION_GIVE_UP = "conclusion.give_up"


class EventType(StrEnum):
    PROTOCOL_ERROR = "protocol.error"
    COMMAND_REJECTED = "command.rejected"
    SESSION_REJECTED = "session.rejected"
    ROOM_SNAPSHOT = "room.snapshot"
    ROOM_STARTED = "room.started"
    ROOM_CLOSED = "room.closed"
    ROOM_HOST_CHANGED = "room.host_changed"
    PLAYER_JOINED = "player.joined"
    PLAYER_LEFT = "player.left"
    PLAYER_ONLINE_CHANGED = "player.online_changed"
    PLAYER_KICKED = "player.kicked"
    DISCUSSION_CREATED = "discussion.created"
    QUESTION_QUEUED = "question.queued"
    QUESTION_CANCELLED = "question.cancelled"
    QUESTION_THINKING = "question.thinking"
    QUESTION_ANSWERED = "question.answered"
    QUESTION_FAILED = "question.failed"
    HINT_THINKING = "hint.thinking"
    HINT_CREATED = "hint.created"
    HINT_FAILED = "hint.failed"
    CONCLUSION_THINKING = "conclusion.thinking"
    CONCLUSION_CLOSE = "conclusion.close"
    CONCLUSION_REJECTED = "conclusion.rejected"
    GAME_SETTLED = "game.settled"


class ErrorCode(StrEnum):
    PROTOCOL_VERSION_UNSUPPORTED = "PROTOCOL_VERSION_UNSUPPORTED"
    SESSION_INVALID = "SESSION_INVALID"
    ROOM_NOT_FOUND = "ROOM_NOT_FOUND"
    ROOM_FULL = "ROOM_FULL"
    NICKNAME_TAKEN = "NICKNAME_TAKEN"
    ROOM_CLOSING = "ROOM_CLOSING"
    NOT_HOST = "NOT_HOST"
    INVALID_ROOM_STAGE = "INVALID_ROOM_STAGE"
    QUESTION_NOT_FOUND = "QUESTION_NOT_FOUND"
    QUESTION_ALREADY_PROCESSING = "QUESTION_ALREADY_PROCESSING"
    AI_TEMPORARILY_UNAVAILABLE = "AI_TEMPORARILY_UNAVAILABLE"
    PUZZLE_LIBRARY_EMPTY = "PUZZLE_LIBRARY_EMPTY"
    PUZZLE_NOT_FOUND = "PUZZLE_NOT_FOUND"
    PUZZLE_CONFLICT = "PUZZLE_CONFLICT"
    ADMIN_AUTH_DISABLED = "ADMIN_AUTH_DISABLED"
    ADMIN_AUTH_INVALID = "ADMIN_AUTH_INVALID"
    ADMIN_AUTH_REQUIRED = "ADMIN_AUTH_REQUIRED"
    ADMIN_RATE_LIMITED = "ADMIN_RATE_LIMITED"
    RATE_LIMITED = "RATE_LIMITED"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"
