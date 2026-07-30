import asyncio
import json
from typing import Any

import httpx
from app.ai.deepseek import DeepSeekService
from app.config import Settings
from app.domain.models import RoomStage
from app.main import create_app
from app.protocol.constants import CommandType
from app.protocol.models import ClientCommand
from app.rooms.manager import RoomManager
from httpx import ASGITransport, AsyncClient


def completion(content: dict[str, Any]) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"content": json.dumps(content, ensure_ascii=False)},
                }
            ]
        },
    )


def command(
    room_id: str,
    command_id: str,
    command_type: CommandType,
    payload: dict[str, Any] | None = None,
) -> ClientCommand:
    return ClientCommand(
        protocol_version=1,
        command_id=command_id,
        type=command_type,
        room_id=room_id,
        session_token="unused-direct-token",
        client_time=1,
        payload=payload or {},
    )


async def drain_background_tasks(room_manager: RoomManager, room_id: str) -> None:
    room = room_manager.rooms[room_id]
    while room.background_tasks:
        await asyncio.gather(*tuple(room.background_tasks))


async def test_mocked_deepseek_drives_room_from_generation_to_settlement() -> None:
    key_facts = ["门缝灯光是求救信号", "她假装丢钥匙是为了安全报警"]
    responses = [
        completion(
            {
                "title": "门外的灯",
                "surface": "她站在门外说钥匙丢了，看到门缝里的灯光后却立刻离开并报警。",
                "truth": (
                    "室友被歹徒挟持，门缝灯光是约定的求救信号。"
                    "她假装丢钥匙骗过屋内歹徒，离开危险区域后报警。"
                ),
                "keyFacts": key_facts,
                "assumptions": [],
                "contentWarnings": [],
                "difficultyRationale": "两个异常行为需要被同一危险情境串联。",
            }
        ),
        completion({"passed": True, "issues": []}),
        completion(
            {
                "answerType": "yes",
                "answer": "是。灯光是有人主动发出的。",
                "confirmedFact": "门缝灯光是求救信号",
                "newFactStrength": "small",
                "safetyFlags": [],
            }
        ),
        completion({"content": "想想她为什么必须让屋内的人相信自己无法进门。"}),
        completion(
            {
                "result": "correct",
                "matchedFacts": key_facts,
                "missingFacts": [],
                "feedback": "",
                "confidence": 0.98,
            }
        ),
    ]

    async def handler(_: httpx.Request) -> httpx.Response:
        return responses.pop(0)

    mock_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.deepseek.com",
    )
    settings = Settings(
        app_env="test",
        deepseek_api_key="test-key",
        deepseek_retry_base_seconds=0,
        _env_file=None,
    )
    service = DeepSeekService(settings, client=mock_client)
    manager = RoomManager(
        settings,
        host_service=service,
        puzzle_generator=service,
    )
    application = create_app(Settings(app_env="test", _env_file=None))
    application.state.room_manager = manager
    try:
        async with AsyncClient(
            transport=ASGITransport(app=application),
            base_url="http://testserver",
        ) as client:
            created = await client.post(
                "/api/v1/rooms",
                headers={"X-Protocol-Version": "1"},
                json={
                    "nickname": "海盐",
                    "source": "ai",
                    "difficulty": "standard",
                    "style": "classic_mystery",
                },
            )
        assert created.status_code == 201
        room_id = created.json()["roomId"]
        room = manager.rooms[room_id]
        player_id = created.json()["playerId"]

        await room.execute_command(
            player_id,
            command(room_id, "cmd_start_ai", CommandType.ROOM_START),
        )
        await room.execute_command(
            player_id,
            command(
                room_id,
                "cmd_question_ai",
                CommandType.QUESTION_SUBMIT,
                {
                    "clientQuestionId": "local_ai_question",
                    "content": "灯光是主动发出的吗？",
                },
            ),
        )
        await drain_background_tasks(manager, room_id)
        assert room.questions[0].status == "answered"

        await room.execute_command(
            player_id,
            command(room_id, "cmd_hint_ai", CommandType.HINT_REQUEST),
        )
        await drain_background_tasks(manager, room_id)
        assert room.hint_count == 1

        await room.execute_command(
            player_id,
            command(
                room_id,
                "cmd_conclusion_ai",
                CommandType.CONCLUSION_SUBMIT,
                {"content": room.puzzle.truth},
            ),
        )
        await drain_background_tasks(manager, room_id)
        assert room.stage is RoomStage.SETTLEMENT
        assert responses == []
    finally:
        await manager.shutdown()
        await mock_client.aclose()
