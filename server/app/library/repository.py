import asyncio
import json
import secrets
from collections.abc import Callable, Sequence
from pathlib import Path
from time import time
from typing import Any

import aiosqlite
from sqlalchemy.engine import make_url

from app.config import SERVER_ROOT
from app.library.models import LibraryPuzzle

PuzzleChooser = Callable[[Sequence[LibraryPuzzle]], LibraryPuzzle]


class PuzzleRepositoryError(RuntimeError):
    pass


class PuzzleNotFoundError(PuzzleRepositoryError):
    pass


class PuzzleConflictError(PuzzleRepositoryError):
    pass


class PuzzleLibraryEmptyError(PuzzleRepositoryError):
    pass


def now_ms() -> int:
    return int(time() * 1000)


def sqlite_path(database_url: str) -> Path:
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite" or not url.database:
        raise ValueError("DATABASE_URL must point to a SQLite database")
    if url.database == ":memory:":
        return Path(":memory:")
    path = Path(url.database)
    return path if path.is_absolute() else (SERVER_ROOT / path).resolve()


class PuzzleRepository:
    def __init__(
        self,
        database_url: str,
        *,
        recent_window: int,
        chooser: PuzzleChooser = secrets.choice,
    ) -> None:
        self.path = sqlite_path(database_url)
        self.recent_window = recent_window
        self._chooser = chooser
        self._connection: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        async with self._lock:
            if self._connection is not None:
                return
            if self.path != Path(":memory:"):
                self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = await aiosqlite.connect(str(self.path))
            connection.row_factory = aiosqlite.Row
            await connection.execute("PRAGMA foreign_keys = ON")
            if self.path != Path(":memory:"):
                await connection.execute("PRAGMA journal_mode = WAL")
            await connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS puzzles (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    surface TEXT NOT NULL,
                    truth TEXT NOT NULL,
                    key_facts_json TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS puzzle_selections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    puzzle_id TEXT NOT NULL,
                    selected_at INTEGER NOT NULL,
                    FOREIGN KEY (puzzle_id) REFERENCES puzzles(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_puzzle_selections_recent
                ON puzzle_selections(id DESC);
                """
            )
            await connection.commit()
            self._connection = connection

    async def close(self) -> None:
        async with self._lock:
            if self._connection is None:
                return
            await self._connection.close()
            self._connection = None

    async def list_puzzles(self) -> list[LibraryPuzzle]:
        async with self._lock:
            connection = self._require_connection()
            cursor = await connection.execute(
                """
                SELECT id, title, surface, truth, key_facts_json, active, created_at, updated_at
                FROM puzzles
                ORDER BY updated_at DESC, id ASC
                """
            )
            rows = await cursor.fetchall()
            await cursor.close()
            return [self._from_row(row) for row in rows]

    async def get_puzzle(self, puzzle_id: str) -> LibraryPuzzle:
        async with self._lock:
            connection = self._require_connection()
            row = await self._fetch_one(
                connection,
                """
                SELECT id, title, surface, truth, key_facts_json, active, created_at, updated_at
                FROM puzzles WHERE id = ?
                """,
                (puzzle_id,),
            )
            if row is None:
                raise PuzzleNotFoundError(puzzle_id)
            return self._from_row(row)

    async def create_puzzle(
        self,
        *,
        puzzle_id: str,
        title: str,
        surface: str,
        truth: str,
        key_facts: Sequence[str],
        active: bool = True,
    ) -> LibraryPuzzle:
        timestamp = now_ms()
        async with self._lock:
            connection = self._require_connection()
            try:
                await connection.execute(
                    """
                    INSERT INTO puzzles (
                        id, title, surface, truth, key_facts_json, active, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        puzzle_id,
                        title,
                        surface,
                        truth,
                        json.dumps(list(key_facts), ensure_ascii=False),
                        int(active),
                        timestamp,
                        timestamp,
                    ),
                )
                await connection.commit()
            except aiosqlite.IntegrityError as exc:
                await connection.rollback()
                raise PuzzleConflictError(puzzle_id) from exc
        return await self.get_puzzle(puzzle_id)

    async def update_puzzle(
        self,
        puzzle_id: str,
        *,
        title: str,
        surface: str,
        truth: str,
        key_facts: Sequence[str],
        active: bool,
    ) -> LibraryPuzzle:
        async with self._lock:
            connection = self._require_connection()
            cursor = await connection.execute(
                """
                UPDATE puzzles
                SET title = ?, surface = ?, truth = ?, key_facts_json = ?,
                    active = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    title,
                    surface,
                    truth,
                    json.dumps(list(key_facts), ensure_ascii=False),
                    int(active),
                    now_ms(),
                    puzzle_id,
                ),
            )
            await connection.commit()
            changed = cursor.rowcount
            await cursor.close()
            if changed == 0:
                raise PuzzleNotFoundError(puzzle_id)
        return await self.get_puzzle(puzzle_id)

    async def delete_puzzle(self, puzzle_id: str) -> None:
        async with self._lock:
            connection = self._require_connection()
            cursor = await connection.execute("DELETE FROM puzzles WHERE id = ?", (puzzle_id,))
            await connection.commit()
            changed = cursor.rowcount
            await cursor.close()
            if changed == 0:
                raise PuzzleNotFoundError(puzzle_id)

    async def import_puzzles(
        self,
        puzzles: Sequence[LibraryPuzzle],
        *,
        replace: bool,
    ) -> int:
        async with self._lock:
            connection = self._require_connection()
            if replace:
                await connection.execute("DELETE FROM puzzles")
            try:
                for puzzle in puzzles:
                    await connection.execute(
                        """
                        INSERT INTO puzzles (
                            id, title, surface, truth, key_facts_json, active,
                            created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(id) DO UPDATE SET
                            title = excluded.title,
                            surface = excluded.surface,
                            truth = excluded.truth,
                            key_facts_json = excluded.key_facts_json,
                            active = excluded.active,
                            updated_at = excluded.updated_at
                        """,
                        (
                            puzzle.id,
                            puzzle.title,
                            puzzle.surface,
                            puzzle.truth,
                            json.dumps(list(puzzle.key_facts), ensure_ascii=False),
                            int(puzzle.active),
                            puzzle.created_at,
                            puzzle.updated_at,
                        ),
                    )
                await connection.commit()
                return len(puzzles)
            except Exception:
                await connection.rollback()
                raise

    async def select_puzzle(self) -> LibraryPuzzle:
        async with self._lock:
            connection = self._require_connection()
            recent_ids = await self._recent_distinct_ids(connection)
            cursor = await connection.execute(
                """
                SELECT p.id, p.title, p.surface, p.truth, p.key_facts_json,
                       p.active, p.created_at, p.updated_at,
                       MAX(s.id) AS last_selection_id
                FROM puzzles AS p
                LEFT JOIN puzzle_selections AS s ON s.puzzle_id = p.id
                WHERE p.active = 1
                GROUP BY p.id
                ORDER BY last_selection_id ASC, p.created_at ASC, p.id ASC
                """
            )
            rows = await cursor.fetchall()
            await cursor.close()
            if not rows:
                raise PuzzleLibraryEmptyError("private puzzle library has no active puzzles")
            puzzles = [self._from_row(row) for row in rows]
            candidates = [puzzle for puzzle in puzzles if puzzle.id not in recent_ids]
            selected = self._chooser(candidates) if candidates else puzzles[0]
            await connection.execute(
                "INSERT INTO puzzle_selections (puzzle_id, selected_at) VALUES (?, ?)",
                (selected.id, now_ms()),
            )
            keep_count = max(50, self.recent_window * 4)
            await connection.execute(
                """
                DELETE FROM puzzle_selections
                WHERE id NOT IN (
                    SELECT id FROM puzzle_selections ORDER BY id DESC LIMIT ?
                )
                """,
                (keep_count,),
            )
            await connection.commit()
            return selected

    async def selection_history(self) -> list[str]:
        async with self._lock:
            connection = self._require_connection()
            cursor = await connection.execute(
                "SELECT puzzle_id FROM puzzle_selections ORDER BY id ASC"
            )
            rows = await cursor.fetchall()
            await cursor.close()
            return [str(row["puzzle_id"]) for row in rows]

    async def _recent_distinct_ids(self, connection: aiosqlite.Connection) -> set[str]:
        if self.recent_window == 0:
            return set()
        cursor = await connection.execute(
            """
            SELECT puzzle_id
            FROM puzzle_selections
            GROUP BY puzzle_id
            ORDER BY MAX(id) DESC
            LIMIT ?
            """,
            (self.recent_window,),
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return {str(row["puzzle_id"]) for row in rows}

    def _require_connection(self) -> aiosqlite.Connection:
        if self._connection is None:
            raise RuntimeError("PuzzleRepository.initialize() must be called first")
        return self._connection

    @staticmethod
    async def _fetch_one(
        connection: aiosqlite.Connection,
        query: str,
        parameters: tuple[Any, ...],
    ) -> aiosqlite.Row | None:
        cursor = await connection.execute(query, parameters)
        row = await cursor.fetchone()
        await cursor.close()
        return row

    @staticmethod
    def _from_row(row: aiosqlite.Row) -> LibraryPuzzle:
        facts = json.loads(str(row["key_facts_json"]))
        if not isinstance(facts, list) or not all(isinstance(item, str) for item in facts):
            raise PuzzleRepositoryError("stored key_facts_json is invalid")
        return LibraryPuzzle(
            id=str(row["id"]),
            title=str(row["title"]),
            surface=str(row["surface"]),
            truth=str(row["truth"]),
            key_facts=tuple(facts),
            active=bool(row["active"]),
            created_at=int(row["created_at"]),
            updated_at=int(row["updated_at"]),
        )
