from dataclasses import dataclass

from app.domain.models import RuntimePuzzle


@dataclass(frozen=True, slots=True)
class LibraryPuzzle:
    id: str
    title: str
    surface: str
    truth: str
    key_facts: tuple[str, ...]
    active: bool
    created_at: int
    updated_at: int

    def to_runtime(self) -> RuntimePuzzle:
        return RuntimePuzzle(
            id=self.id,
            title=self.title,
            surface=self.surface,
            truth=self.truth,
            key_facts=self.key_facts,
        )
