from pathlib import Path

import pytest
from app.library.models import LibraryPuzzle
from app.library.repository import (
    PuzzleConflictError,
    PuzzleLibraryEmptyError,
    PuzzleNotFoundError,
    PuzzleRepository,
)


def database_url(path: Path) -> str:
    return f"sqlite+aiosqlite:///{path}"


async def add_puzzle(repository: PuzzleRepository, suffix: str) -> LibraryPuzzle:
    return await repository.create_puzzle(
        puzzle_id=f"puzzle_{suffix}",
        title=f"题目 {suffix}",
        surface=f"这是题目 {suffix} 的汤面，包含足够信息供玩家开始推理。",
        truth=f"这是题目 {suffix} 的完整汤底，解释了所有行为、动机和关键因果关系。",
        key_facts=(f"事实 {suffix}-1", f"事实 {suffix}-2"),
    )


async def test_crud_and_replace_import(tmp_path: Path) -> None:
    repository = PuzzleRepository(database_url(tmp_path / "library.db"), recent_window=10)
    await repository.initialize()
    try:
        created = await add_puzzle(repository, "one")
        assert created.active is True
        with pytest.raises(PuzzleConflictError):
            await add_puzzle(repository, "one")
        assert (await repository.get_puzzle(created.id)).title == created.title

        updated = await repository.update_puzzle(
            created.id,
            title="更新后的标题",
            surface=created.surface,
            truth=created.truth,
            key_facts=created.key_facts,
            active=False,
        )
        assert updated.title == "更新后的标题"
        assert updated.active is False

        replacement = LibraryPuzzle(
            id="puzzle_two",
            title="导入题目",
            surface="导入题目的汤面足够完整，可以用于私人题库房间。",
            truth="导入题目的汤底足够完整，可以解释人物的动机和全部异常行为。",
            key_facts=("导入事实一", "导入事实二"),
            active=True,
            created_at=100,
            updated_at=100,
        )
        assert await repository.import_puzzles([replacement], replace=True) == 1
        assert [item.id for item in await repository.list_puzzles()] == ["puzzle_two"]

        await repository.delete_puzzle("puzzle_two")
        with pytest.raises(PuzzleNotFoundError):
            await repository.get_puzzle("puzzle_two")
    finally:
        await repository.close()


async def test_selection_excludes_recent_distinct_puzzles(tmp_path: Path) -> None:
    repository = PuzzleRepository(
        database_url(tmp_path / "selection.db"),
        recent_window=2,
        chooser=lambda candidates: candidates[0],
    )
    await repository.initialize()
    try:
        await add_puzzle(repository, "a")
        await add_puzzle(repository, "b")
        await add_puzzle(repository, "c")

        selected = [await repository.select_puzzle() for _ in range(4)]

        assert [item.id for item in selected] == [
            "puzzle_a",
            "puzzle_b",
            "puzzle_c",
            "puzzle_a",
        ]
        assert await repository.selection_history() == [
            "puzzle_a",
            "puzzle_b",
            "puzzle_c",
            "puzzle_a",
        ]
    finally:
        await repository.close()


async def test_selection_rejects_empty_or_inactive_library(tmp_path: Path) -> None:
    repository = PuzzleRepository(database_url(tmp_path / "empty.db"), recent_window=10)
    await repository.initialize()
    try:
        puzzle = await add_puzzle(repository, "inactive")
        await repository.update_puzzle(
            puzzle.id,
            title=puzzle.title,
            surface=puzzle.surface,
            truth=puzzle.truth,
            key_facts=puzzle.key_facts,
            active=False,
        )
        with pytest.raises(PuzzleLibraryEmptyError):
            await repository.select_puzzle()
    finally:
        await repository.close()
