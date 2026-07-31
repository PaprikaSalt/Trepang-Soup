from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from app.domain.models import AnswerType, RuntimePuzzle
from app.security.sessions import generate_id


class AIModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class PuzzleGeneration(AIModel):
    title: str = Field(min_length=1, max_length=80)
    surface: str = Field(min_length=20, max_length=800)
    truth: str = Field(min_length=40, max_length=2_000)
    key_facts: list[str] = Field(alias="keyFacts", min_length=2, max_length=8)
    assumptions: list[str] = Field(default_factory=list, max_length=8)
    content_warnings: list[str] = Field(
        default_factory=list,
        alias="contentWarnings",
        max_length=8,
    )
    difficulty_rationale: str = Field(alias="difficultyRationale", min_length=1, max_length=300)

    @field_validator("title", "surface", "truth", "difficulty_rationale")
    @classmethod
    def strip_text(cls, value: str, info: ValidationInfo) -> str:
        cleaned = value.strip()
        minimums = {"title": 1, "surface": 20, "truth": 40, "difficulty_rationale": 1}
        minimum = minimums.get(info.field_name or "")
        if minimum is None:
            raise AssertionError("unexpected text field")
        if len(cleaned) < minimum:
            raise ValueError("text is too short after trimming")
        return cleaned

    @field_validator("key_facts", "assumptions", "content_warnings")
    @classmethod
    def strip_items(cls, value: list[str], info: ValidationInfo) -> list[str]:
        if any(not item.strip() for item in value):
            raise ValueError("items must not be blank")
        cleaned = [item.strip() for item in value]
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("items must be unique")
        if info.field_name == "key_facts" and len(cleaned) < 2:
            raise ValueError("at least two key facts are required")
        return cleaned

    def to_runtime(self) -> RuntimePuzzle:
        return RuntimePuzzle(
            id=generate_id("puzzle"),
            title=self.title,
            surface=self.surface,
            truth=self.truth,
            key_facts=tuple(self.key_facts),
        )


class PuzzleQualityReview(AIModel):
    passed: bool
    issues: list[str] = Field(default_factory=list, max_length=12)


class HostAnswerOutput(AIModel):
    answer_type: AnswerType = Field(alias="answerType")


class HintOutput(AIModel):
    content: str = Field(min_length=1, max_length=300)


class ConclusionOutput(AIModel):
    result: Literal["correct", "close", "wrong"]
    matched_facts: list[str] = Field(default_factory=list, alias="matchedFacts")
    missing_facts: list[str] = Field(default_factory=list, alias="missingFacts")


class PlayerAwardOutput(AIModel):
    player_id: str = Field(alias="playerId", min_length=1, max_length=80)
    reason: str = Field(min_length=4, max_length=180)


class QuestionAwardOutput(PlayerAwardOutput):
    question_id: str | None = Field(alias="questionId", max_length=80)


class GameReviewOutput(AIModel):
    summary: str = Field(min_length=8, max_length=300)
    mvp: PlayerAwardOutput
    best_misdirection: PlayerAwardOutput = Field(alias="bestMisdirection")
    most_valuable_question: QuestionAwardOutput = Field(alias="mostValuableQuestion")

    @field_validator("summary")
    @classmethod
    def strip_summary(cls, value: str) -> str:
        return value.strip()
