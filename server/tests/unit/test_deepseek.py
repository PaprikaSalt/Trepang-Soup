import json
from typing import Any

import httpx
import pytest
from app.ai.deepseek import AIServiceError, DeepSeekService
from app.config import Settings
from app.domain.models import (
    Difficulty,
    PuzzleStyle,
    RuntimePuzzle,
)


def settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "app_env": "test",
        "deepseek_api_key": "test-secret",
        "deepseek_retry_base_seconds": 0,
        **overrides,
    }
    return Settings(_env_file=None, **values)


def completion(content: dict[str, Any] | str, *, finish_reason: str = "stop") -> httpx.Response:
    serialized = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "finish_reason": finish_reason,
                    "message": {"content": serialized},
                }
            ]
        },
    )


def puzzle() -> RuntimePuzzle:
    return RuntimePuzzle(
        id="puzzle_test",
        title="门口的灯",
        surface="她站在门外说钥匙丢了，随后看见门缝里的灯光便离开并报警。",
        truth="室友被歹徒挟持，门缝灯光是求救信号。她假装丢钥匙避免惊动歹徒并报警。",
        key_facts=(
            "室友正被歹徒挟持",
            "门缝灯光是室友发出的求救信号",
            "她假装丢钥匙是为了避免惊动歹徒",
        ),
    )


async def test_retries_rate_limit_and_sends_current_model_payload() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(429, json={"error": {"message": "slow down"}})
        return completion(
            {
                "answerType": "yes",
                "answer": "是。灯光确实是人为发出的信号。",
                "confirmedFact": "门缝灯光是室友发出的求救信号",
                "newFactStrength": "small",
                "safetyFlags": [],
            }
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.deepseek.com",
    )
    service = DeepSeekService(settings(), client=client)

    answer = await service.answer_question(puzzle(), [], "灯光是求救信号吗？")

    assert answer.answer_type == "yes"
    assert len(requests) == 2
    payload = json.loads(requests[-1].content)
    assert payload["model"] == "deepseek-v4-flash"
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["thinking"] == {"type": "disabled"}
    assert requests[-1].headers["authorization"] == "Bearer test-secret"
    await client.aclose()


@pytest.mark.parametrize("failure", ["network", "server_error", "rate_limit"])
async def test_transient_failures_use_backoff_and_recover(failure: str) -> None:
    calls = 0
    delays: list[float] = []

    async def sleep(delay: float) -> None:
        delays.append(delay)

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            if failure == "network":
                raise httpx.ReadTimeout("timed out", request=request)
            return httpx.Response(500 if failure == "server_error" else 429)
        return completion({"content": "先关注门外那句话是说给谁听的。"})

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.deepseek.com",
    )
    service = DeepSeekService(
        settings(deepseek_retry_base_seconds=0.25),
        client=client,
        sleep=sleep,
    )

    assert await service.create_hint(puzzle(), [], 1)
    assert calls == 2
    assert delays == [0.25]
    await client.aclose()


async def test_authentication_failure_is_not_retried() -> None:
    calls = 0

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(401, json={"error": {"message": "invalid key"}})

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.deepseek.com",
    )
    service = DeepSeekService(settings(), client=client)

    with pytest.raises(AIServiceError) as failed:
        await service.create_hint(puzzle(), [], 1)
    assert failed.value.retryable is False
    assert calls == 1
    await client.aclose()


async def test_repairs_invalid_json_once_with_same_context() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return completion("not-json")
        return completion({"content": "注意她为什么必须让屋里的人相信自己进不去。"})

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.deepseek.com",
    )
    service = DeepSeekService(settings(), client=client)

    hint = await service.create_hint(puzzle(), [], 1)

    assert "相信自己进不去" in hint
    repair_payload = json.loads(requests[1].content)
    assert repair_payload["messages"][2] == {"role": "assistant", "content": "not-json"}
    assert "只修复" in repair_payload["messages"][3]["content"]
    await client.aclose()


async def test_generation_rejects_bad_review_then_generates_again() -> None:
    candidate_one = {
        "title": "第一个候选",
        "surface": "这是一个长度足够但质量审查将拒绝的海龟汤汤面，需要玩家继续提问。",
        "truth": (
            "这是一个长度绝对足够的完整汤底，但其中存在多个同等合理的解释，"
            "因此独立质量审查不会通过本候选题目。"
        ),
        "keyFacts": ["事实甲", "事实乙"],
        "assumptions": [],
        "contentWarnings": [],
        "difficultyRationale": "适合标准难度。",
    }
    candidate_two = {
        **candidate_one,
        "title": "第二个候选",
        "surface": "这是第二个长度足够并且能够通过质量审查的海龟汤汤面，需要逐步推理。",
        "truth": (
            "这是第二个长度绝对足够并且逻辑自洽的完整汤底，人物行为动机、"
            "时间顺序和关键因果关系都能够成立。"
        ),
    }
    responses = [
        completion(candidate_one),
        completion({"passed": False, "issues": ["存在两个同等合理答案"]}),
        completion(candidate_two),
        completion({"passed": True, "issues": []}),
    ]
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return responses.pop(0)

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.deepseek.com",
    )
    service = DeepSeekService(settings(), client=client)

    generated = await service.generate_puzzle(
        Difficulty.STANDARD,
        PuzzleStyle.CLASSIC_MYSTERY,
    )

    assert generated.title == "第二个候选"
    assert len(requests) == 4
    second_generation = json.loads(requests[2].content)
    assert "存在两个同等合理答案" in second_generation["messages"][1]["content"]
    await client.aclose()


async def test_conclusion_rejects_inconsistent_key_fact_coverage() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return completion(
            {
                "result": "correct",
                "matchedFacts": ["室友正被歹徒挟持"],
                "missingFacts": [],
                "feedback": "",
                "confidence": 0.99,
            }
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.deepseek.com",
    )
    service = DeepSeekService(settings(), client=client)

    with pytest.raises(AIServiceError, match="覆盖关系"):
        await service.evaluate_conclusion(puzzle(), "室友被歹徒挟持。")
    await client.aclose()
