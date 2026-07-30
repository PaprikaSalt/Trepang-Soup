import asyncio
import logging
from time import time

from app.ai.deepseek import AIServiceError, DeepSeekService
from app.ai.host import (
    DeterministicHostService,
    DeterministicPuzzleGenerator,
    HostService,
    PuzzleGenerator,
)
from app.config import Settings
from app.domain.errors import DomainError
from app.domain.models import (
    Difficulty,
    Player,
    PuzzleSource,
    PuzzleStyle,
    Session,
)
from app.library.repository import PuzzleLibraryEmptyError, PuzzleRepository
from app.protocol.constants import ErrorCode, EventType
from app.rooms.room import Room
from app.security.sessions import (
    generate_id,
    generate_invite_code,
    generate_session_token,
    hash_session_token,
    normalize_nickname,
)

logger = logging.getLogger(__name__)


def now_ms() -> int:
    return int(time() * 1000)


class RoomManager:
    def __init__(
        self,
        settings: Settings,
        host_service: HostService | None = None,
        puzzle_generator: PuzzleGenerator | None = None,
        puzzle_repository: PuzzleRepository | None = None,
    ) -> None:
        self.settings = settings
        self._owned_ai_service: DeepSeekService | None = None
        if host_service is None and puzzle_generator is None:
            if settings.deepseek_api_key.get_secret_value():
                deepseek = DeepSeekService(settings)
                self._owned_ai_service = deepseek
                host_service = deepseek
                puzzle_generator = deepseek
            else:
                host_service = DeterministicHostService()
                puzzle_generator = DeterministicPuzzleGenerator()
        self.host_service = host_service or DeterministicHostService()
        self.puzzle_generator = puzzle_generator or DeterministicPuzzleGenerator()
        self.puzzle_repository = puzzle_repository
        self.rooms: dict[str, Room] = {}
        self.room_ids_by_invite: dict[str, str] = {}
        self.sessions: dict[str, Session] = {}
        self.lock = asyncio.Lock()
        self.cleanup_task: asyncio.Task[None] | None = None

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
        if source is PuzzleSource.AI:
            if difficulty is None or style is None:
                raise DomainError(
                    ErrorCode.VALIDATION_ERROR,
                    "AI 房间必须指定难度和风格。",
                    status_code=422,
                )
            try:
                puzzle = await self.puzzle_generator.generate_puzzle(difficulty, style)
            except AIServiceError as exc:
                raise DomainError(
                    ErrorCode.AI_TEMPORARILY_UNAVAILABLE,
                    "主持人暂时无法生成新题目，请稍后重试。",
                    status_code=503,
                    retryable=exc.retryable,
                ) from exc
        else:
            if self.puzzle_repository is None:
                raise DomainError(
                    ErrorCode.PUZZLE_LIBRARY_EMPTY,
                    "服务端尚未启用私人题库。",
                    status_code=503,
                )
            try:
                puzzle = (await self.puzzle_repository.select_puzzle()).to_runtime()
            except PuzzleLibraryEmptyError as exc:
                raise DomainError(
                    ErrorCode.PUZZLE_LIBRARY_EMPTY,
                    "私人题库中没有可用题目。",
                    status_code=409,
                ) from exc
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
                puzzle=puzzle,
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
        if self.cleanup_task is not None:
            self.cleanup_task.cancel()
            await asyncio.gather(self.cleanup_task, return_exceptions=True)
            self.cleanup_task = None
        rooms = tuple(self.rooms.values())
        if rooms:
            await asyncio.gather(*(room.shutdown() for room in rooms))
        self.rooms.clear()
        self.room_ids_by_invite.clear()
        self.sessions.clear()
        if self._owned_ai_service is not None:
            await self._owned_ai_service.aclose()

    def start(self) -> None:
        if self.cleanup_task is not None and not self.cleanup_task.done():
            return
        self.cleanup_task = asyncio.create_task(
            self._cleanup_loop(),
            name="room-cleanup",
        )

    async def cleanup_once(self, *, current_time_ms: int | None = None) -> int:
        current = current_time_ms if current_time_ms is not None else now_ms()
        async with self.lock:
            doomed_ids = [
                room_id
                for room_id, room in self.rooms.items()
                if room.cleanup_due(
                    current_time_ms=current,
                    idle_seconds=self.settings.room_idle_seconds,
                    terminal_grace_seconds=self.settings.room_settlement_grace_seconds,
                )
            ]
            doomed_rooms = [self.rooms.pop(room_id) for room_id in doomed_ids]
            for room in doomed_rooms:
                self.room_ids_by_invite.pop(room.invite_code, None)
            doomed_set = set(doomed_ids)
            self.sessions = {
                token_hash: session
                for token_hash, session in self.sessions.items()
                if session.room_id not in doomed_set
            }
        if doomed_rooms:
            await asyncio.gather(*(room.shutdown() for room in doomed_rooms))
        return len(doomed_rooms)

    async def _cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(self.settings.room_cleanup_interval_seconds)
            try:
                await self.cleanup_once()
            except Exception:
                logger.exception(
                    "room cleanup failed",
                    extra={"component": "room_manager", "error_code": "ROOM_CLEANUP_FAILED"},
                )

    @staticmethod
    def _validate_nickname(nickname: str) -> None:
        if not 1 <= len(nickname) <= 16:
            raise DomainError(
                ErrorCode.VALIDATION_ERROR,
                "昵称长度必须为 1 到 16 个字符。",
                status_code=422,
            )
