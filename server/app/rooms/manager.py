import asyncio
from time import time

from app.ai.host import DeterministicHostService, HostService
from app.config import Settings
from app.domain.errors import DomainError
from app.domain.models import (
    Difficulty,
    Player,
    PuzzleSource,
    PuzzleStyle,
    Session,
)
from app.protocol.constants import ErrorCode, EventType
from app.rooms.demo_puzzle import DEMO_PUZZLE
from app.rooms.room import Room
from app.security.sessions import (
    generate_id,
    generate_invite_code,
    generate_session_token,
    hash_session_token,
    normalize_nickname,
)


def now_ms() -> int:
    return int(time() * 1000)


class RoomManager:
    def __init__(
        self,
        settings: Settings,
        host_service: HostService | None = None,
    ) -> None:
        self.settings = settings
        self.host_service = host_service or DeterministicHostService()
        self.rooms: dict[str, Room] = {}
        self.room_ids_by_invite: dict[str, str] = {}
        self.sessions: dict[str, Session] = {}
        self.lock = asyncio.Lock()

    def _session_expiry(self) -> int:
        return now_ms() + self.settings.room_idle_seconds * 1000

    def _issue_session(
        self,
        room_id: str,
        player_id: str,
        client_instance_id: str | None = None,
    ) -> tuple[str, Session]:
        token = generate_session_token()
        session = Session(
            token_hash=hash_session_token(token),
            room_id=room_id,
            player_id=player_id,
            expires_at=self._session_expiry(),
            created_at=now_ms(),
            client_instance_id=client_instance_id,
        )
        self.sessions[session.token_hash] = session
        return token, session

    async def create_room(
        self,
        *,
        nickname: str,
        source: PuzzleSource,
        difficulty: Difficulty | None,
        style: PuzzleStyle | None,
    ) -> tuple[Room, Player, str, Session]:
        display_name, normalized_name = normalize_nickname(nickname)
        self._validate_nickname(display_name)
        async with self.lock:
            room_id = generate_id("room")
            invite_code = self._unique_invite_code()
            player = Player(
                id=generate_id("player"),
                nickname=display_name,
                normalized_nickname=normalized_name,
                joined_at=now_ms(),
            )
            room = Room(
                room_id=room_id,
                invite_code=invite_code,
                source=source,
                difficulty=difficulty if source is PuzzleSource.AI else None,
                style=style if source is PuzzleSource.AI else None,
                host_player=player,
                puzzle=DEMO_PUZZLE,
                host_service=self.host_service,
                host_transfer_seconds=self.settings.host_transfer_seconds,
            )
            self.rooms[room_id] = room
            self.room_ids_by_invite[invite_code] = room_id
            token, session = self._issue_session(room_id, player.id)
        return room, player, token, session

    async def join_room(
        self,
        *,
        invite_code: str,
        nickname: str,
        client_instance_id: str,
    ) -> tuple[Room, Player, str, Session]:
        display_name, normalized_name = normalize_nickname(nickname)
        self._validate_nickname(display_name)
        normalized_code = invite_code.strip().upper()
        async with self.lock:
            room_id = self.room_ids_by_invite.get(normalized_code)
            room = self.rooms.get(room_id) if room_id is not None else None
            if room is None:
                raise DomainError(
                    ErrorCode.ROOM_NOT_FOUND,
                    "没有找到这个房间。",
                    status_code=404,
                )
            async with room.lock:
                if len(room.players) >= self.settings.max_room_players:
                    raise DomainError(ErrorCode.ROOM_FULL, "房间已经坐满了。", status_code=409)
                if any(
                    item.normalized_nickname == normalized_name for item in room.players.values()
                ):
                    raise DomainError(
                        ErrorCode.NICKNAME_TAKEN,
                        "这个昵称已经有人使用。",
                        status_code=409,
                    )
                player = Player(
                    id=generate_id("player"),
                    nickname=display_name,
                    normalized_nickname=normalized_name,
                    joined_at=now_ms(),
                )
                room.players[player.id] = player
                event = room._new_event(
                    event_type=EventType.PLAYER_JOINED,
                    payload={"player": room.player_public_dict(player)},
                )
            token, session = self._issue_session(
                room.id,
                player.id,
                client_instance_id,
            )
        await room.broadcast(event)
        return room, player, token, session

    async def authenticate(self, room_id: str, token: str) -> tuple[Room, Session]:
        token_hash = hash_session_token(token)
        async with self.lock:
            session = self.sessions.get(token_hash)
            room = self.rooms.get(room_id)
            if (
                session is None
                or room is None
                or session.room_id != room_id
                or session.expires_at <= now_ms()
            ):
                if session is not None and session.expires_at <= now_ms():
                    self.sessions.pop(token_hash, None)
                raise DomainError(
                    ErrorCode.SESSION_INVALID,
                    "会话已失效，请重新加入房间。",
                    status_code=401,
                )
            room.require_player(session.player_id)
            return room, session

    async def resume_session(
        self,
        room_id: str,
        token: str,
    ) -> tuple[Room, Session, str, Session]:
        token_hash = hash_session_token(token)
        async with self.lock:
            old_session = self.sessions.get(token_hash)
            room = self.rooms.get(room_id)
            if (
                old_session is None
                or room is None
                or old_session.room_id != room_id
                or old_session.expires_at <= now_ms()
            ):
                if old_session is not None and old_session.expires_at <= now_ms():
                    self.sessions.pop(token_hash, None)
                raise DomainError(
                    ErrorCode.SESSION_INVALID,
                    "会话已失效，请重新加入房间。",
                    status_code=401,
                )
            room.require_player(old_session.player_id)
            self.sessions.pop(old_session.token_hash, None)
            new_token, new_session = self._issue_session(
                room_id,
                old_session.player_id,
                old_session.client_instance_id,
            )
        return room, old_session, new_token, new_session

    def _unique_invite_code(self) -> str:
        for _ in range(100):
            code = generate_invite_code()
            if code not in self.room_ids_by_invite:
                return code
        raise RuntimeError("failed to allocate a unique invite code")

    async def shutdown(self) -> None:
        rooms = tuple(self.rooms.values())
        if rooms:
            await asyncio.gather(*(room.shutdown() for room in rooms))

    @staticmethod
    def _validate_nickname(nickname: str) -> None:
        if not 1 <= len(nickname) <= 16:
            raise DomainError(
                ErrorCode.VALIDATION_ERROR,
                "昵称长度必须为 1 到 16 个字符。",
                status_code=422,
            )
