import re
from typing import Protocol

from app.domain.models import (
    AnswerType,
    ConclusionResult,
    Difficulty,
    Discussion,
    GameReview,
    GameReviewAward,
    HostAnswer,
    Player,
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

    async def review_game(
        self,
        puzzle: RuntimePuzzle,
        players: list[Player],
        questions: list[Question],
        discussions: list[Discussion],
        hint_count: int,
        gave_up: bool,
    ) -> GameReview: ...


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
        if not has_danger:
            return ConclusionResult(
                result="wrong",
                feedback="还没有解释故事最核心的冲突，暂时无法结束，请继续推理。",
            )
        missing_detail_count = 2 - sum((has_signal, has_pretend))
        return ConclusionResult(
            result="confirm" if missing_detail_count >= 2 else "correct",
            feedback=(
                "目前遗漏了较多的细节，会影响游戏评分，是否继续提交？"
                if missing_detail_count >= 2
                else ""
            ),
            missing_detail_count=missing_detail_count,
            detail_penalty=missing_detail_count * 6,
        )

    async def review_game(
        self,
        puzzle: RuntimePuzzle,
        players: list[Player],
        questions: list[Question],
        discussions: list[Discussion],
        hint_count: int,
        gave_up: bool,
    ) -> GameReview:
        del puzzle
        if not players:
            raise ValueError("game review requires at least one player")

        # Positive answers reward progress; irrelevant/no answers identify the funniest detour.
        progress_scores = {player.id: 0 for player in players}
        detour_scores = {player.id: 0 for player in players}
        for question in questions:
            if question.answer_type is AnswerType.YES:
                progress_scores[question.author_id] = progress_scores.get(question.author_id, 0) + 3
            elif question.answer_type is AnswerType.PARTIAL:
                progress_scores[question.author_id] = progress_scores.get(question.author_id, 0) + 2
            elif question.answer_type in {AnswerType.NO, AnswerType.IRRELEVANT}:
                detour_scores[question.author_id] = detour_scores.get(question.author_id, 0) + 1
        for discussion in discussions:
            progress_scores[discussion.author_id] = progress_scores.get(discussion.author_id, 0) + 1

        order = {player.id: index for index, player in enumerate(players)}
        mvp = max(players, key=lambda player: (progress_scores[player.id], -order[player.id]))
        detour = max(players, key=lambda player: (detour_scores[player.id], order[player.id]))
        valuable = max(
            (question for question in questions if question.answer_type is not None),
            key=lambda question: (
                3
                if question.answer_type is AnswerType.YES
                else 2
                if question.answer_type is AnswerType.PARTIAL
                else 1,
                -question.created_at,
            ),
            default=None,
        )
        valuable_player = (
            next((player for player in players if player.id == valuable.author_id), mvp)
            if valuable is not None
            else mvp
        )
        summary = (
            "大家在公布汤底前已经留下了清晰的推理轨迹，关键问题与讨论方向都被完整记录。"
            if gave_up
            else "大家把零散线索逐步连成了完整因果链，并在结案前抓住了决定性的异常行为。"
        )
        if hint_count:
            summary += f" 本局共使用 {hint_count} 次公共提示。"
        return GameReview(
            summary=summary,
            awards=(
                GameReviewAward(
                    title="MVP 玩家",
                    recipient_player_id=mvp.id,
                    reason="持续提出有效方向并推动了本局推理。",
                ),
                GameReviewAward(
                    title="最佳带偏奖",
                    recipient_player_id=detour.id,
                    reason=(
                        "贡献了本局最有戏剧性的错误方向。"
                        if detour_scores[detour.id]
                        else "本局几乎没有明显跑偏，只好把这份荣誉留给最会制造气氛的人。"
                    ),
                ),
                GameReviewAward(
                    title="最有价值问题",
                    recipient_player_id=valuable_player.id,
                    reason=(
                        f"“{valuable.content}”最有效地缩小了真相范围。"
                        if valuable is not None
                        else "本局没有正式问题，这个席位记录了最接近关键方向的参与者。"
                    ),
                ),
            ),
        )
