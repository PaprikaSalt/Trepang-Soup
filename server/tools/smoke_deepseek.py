"""Exercise real DeepSeek generation, answer, hint, and conclusion JSON flows."""

import argparse
import asyncio
import json

from app.ai.deepseek import DeepSeekService
from app.config import Settings
from app.domain.models import Difficulty, PuzzleStyle


async def run(difficulty: Difficulty, style: PuzzleStyle) -> None:
    settings = Settings()
    if not settings.deepseek_api_key.get_secret_value():
        raise SystemExit("DEEPSEEK_API_KEY is not configured in server/.env")
    service = DeepSeekService(settings)
    try:
        puzzle = await service.generate_puzzle(difficulty, style)
        answer = await service.answer_question(
            puzzle,
            [],
            "汤面中最异常的行为是当事人有意做出的吗？",
        )
        hint = await service.create_hint(puzzle, [], 1)
        conclusion = await service.evaluate_conclusion(puzzle, puzzle.truth)
        if conclusion.result != "correct":
            raise AssertionError("the complete truth was not accepted as a correct conclusion")
    finally:
        await service.aclose()

    print(
        json.dumps(
            {
                "status": "ok",
                "model": settings.deepseek_model,
                "puzzleId": puzzle.id,
                "keyFactCount": len(puzzle.key_facts),
                "answerType": answer.answer_type,
                "hintLength": len(hint),
                "conclusion": conclusion.result,
            },
            ensure_ascii=False,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--difficulty",
        choices=[item.value for item in Difficulty],
        default=Difficulty.STANDARD,
    )
    parser.add_argument(
        "--style",
        choices=[item.value for item in PuzzleStyle],
        default=PuzzleStyle.CLASSIC_MYSTERY,
    )
    args = parser.parse_args()
    asyncio.run(run(Difficulty(args.difficulty), PuzzleStyle(args.style)))


if __name__ == "__main__":
    main()
