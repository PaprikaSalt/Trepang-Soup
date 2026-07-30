import re
from typing import Protocol

from app.domain.models import (
    AnswerType,
    ConclusionResult,
    Difficulty,
    HostAnswer,
    PuzzleStyle,
    Question,
    RuntimePuzzle,
)
from app.rooms.demo_puzzle import DEMO_PUZZLE


class HostService(Protocol):
    async def answer_question(
        self,
        puzzle: RuntimePuzzle,
        answered_questions: list[Question],
        content: str,
    ) -> HostAnswer: ...

    async def create_hint(
        self,
        puzzle: RuntimePuzzle,
        answered_questions: list[Question],
        hint_count: int,
    ) -> str: ...

    async def evaluate_conclusion(
        self,
        puzzle: RuntimePuzzle,
        content: str,
    ) -> ConclusionResult: ...


class PuzzleGenerator(Protocol):
    async def generate_puzzle(
        self,
        difficulty: Difficulty,
        style: PuzzleStyle,
    ) -> RuntimePuzzle: ...


class DeterministicPuzzleGenerator:
    async def generate_puzzle(
        self,
        difficulty: Difficulty,
        style: PuzzleStyle,
    ) -> RuntimePuzzle:
        del difficulty, style
        return DEMO_PUZZLE


class DeterministicHostService:
    """Development host used until the DeepSeek adapter is configured."""

    async def answer_question(
        self,
        puzzle: RuntimePuzzle,
        answered_questions: list[Question],
        content: str,
    ) -> HostAnswer:
        del puzzle, answered_questions
        normalized = re.sub(r"\s+", "", content)
        if re.search(r"灯|光|闪|信号", normalized):
            return HostAnswer(
                answer_type=AnswerType.YES,
                answer="是。灯光不是普通照明，它确实在传递信息。",
                confirmed_fact="灯光是主动产生的信号",
            )
        if re.search(r"室友.*危险|绑架|挟持|闯入|坏人", normalized):
            return HostAnswer(
                answer_type=AnswerType.PARTIAL,
                answer="基本正确。室友正处在危险中，而且屋内还有另一个人。",
            )
        if re.search(r"钥匙.*丢|假装|故意.*抱怨|骗|伪装", normalized):
            return HostAnswer(
                answer_type=AnswerType.YES,
                answer="是。她并没有真的丢钥匙，那句话是说给屋里的人听的。",
                confirmed_fact="抱怨钥匙丢了是在伪装",
            )
        if re.search(r"室友.*死|尸体|鬼|灵异", normalized):
            return HostAnswer(
                answer_type=AnswerType.NO,
                answer="否。室友还活着，也没有灵异因素。",
            )
        return HostAnswer(
            answer_type=AnswerType.IRRELEVANT,
            answer="无关。这个方向暂时不能解释她为什么故意不进门。",
        )

    async def create_hint(
        self,
        puzzle: RuntimePuzzle,
        answered_questions: list[Question],
        hint_count: int,
    ) -> str:
        del puzzle, answered_questions, hint_count
        return (
            "林夏并非粗心忘带钥匙。把门缝里的光当作一种交流方式，再想想室友为什么不能直接开口求救。"
        )

    async def evaluate_conclusion(
        self,
        puzzle: RuntimePuzzle,
        content: str,
    ) -> ConclusionResult:
        del puzzle
        normalized = re.sub(r"\s+", "", content)
        has_danger = bool(re.search(r"危险|挟持|绑架|闯入|歹徒|坏人", normalized))
        has_signal = bool(re.search(r"灯|闪|信号|求救", normalized))
        has_pretend = bool(re.search(r"假装|故意|骗|伪装|钥匙", normalized))
        matched = sum((has_danger, has_signal, has_pretend))
        if matched == 3:
            return ConclusionResult(result="correct")
        if matched >= 2:
            return ConclusionResult(
                result="close",
                feedback="你们已经非常接近，还缺少一个关键行为之间的因果连接。",
            )
        return ConclusionResult(
            result="wrong",
            feedback="这套解释还没有覆盖灯光和她故意不进门的原因。",
        )
