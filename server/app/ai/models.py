from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from app.domain.models import AnswerType, ConclusionResult, HostAnswer, RuntimePuzzle
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
    answer: str = Field(min_length=1, max_length=120)
    confirmed_fact: str | None = Field(default=None, alias="confirmedFact", max_length=200)
    new_fact_strength: Literal["none", "small"] = Field(alias="newFactStrength")
    safety_flags: list[str] = Field(default_factory=list, alias="safetyFlags", max_length=8)

    @field_validator("answer")
    @classmethod
    def strip_answer(cls, value: str) -> str:
        return value.strip()

    @field_validator("confirmed_fact")
    @classmethod
    def normalize_confirmed_fact(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    def to_domain(self) -> HostAnswer:
        return HostAnswer(
            answer_type=self.answer_type,
            answer=self.answer,
            confirmed_fact=self.confirmed_fact,
        )


class HintOutput(AIModel):
    content: str = Field(min_length=1, max_length=300)


class ConclusionOutput(AIModel):
    result: Literal["correct", "close", "wrong"]
    matched_facts: list[str] = Field(default_factory=list, alias="matchedFacts")
    missing_facts: list[str] = Field(default_factory=list, alias="missingFacts")
    feedback: str = Field(default="", max_length=300)
    confidence: float = Field(ge=0, le=1)

    def to_domain(self) -> ConclusionResult:
        return ConclusionResult(
            result=self.result,
            feedback=self.feedback,
            missing_facts=tuple(self.missing_facts),
        )
