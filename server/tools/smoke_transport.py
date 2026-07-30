"""Exercise the client-facing HTTP/WebSocket flow against a running server."""

import argparse
import asyncio
import json
import time
import uuid
from typing import Any

import httpx
from websockets.asyncio.client import ClientConnection, connect

PROTOCOL_VERSION = 1


def command(
    *,
    room_id: str,
    session_token: str,
    command_type: str,
    payload: dict[str, Any],
) -> str:
    return json.dumps(
        {
            "protocolVersion": PROTOCOL_VERSION,
            "commandId": f"cmd_{uuid.uuid4().hex}",
            "type": command_type,
            "roomId": room_id,
            "sessionToken": session_token,
            "clientTime": int(time.time() * 1000),
            "payload": payload,
        },
        ensure_ascii=False,
    )


async def receive_until(
    websocket: ClientConnection,
    target_type: str,
    received: list[dict[str, Any]],
) -> dict[str, Any]:
    while True:
        raw = await asyncio.wait_for(websocket.recv(), timeout=5)
        event = json.loads(raw)
        if not isinstance(event, dict):
            raise TypeError("server event must be a JSON object")
        received.append(event)
        if event.get("type") == target_type:
            return event


async def run(base_url: str) -> None:
    headers = {"X-Protocol-Version": str(PROTOCOL_VERSION)}
    async with httpx.AsyncClient(
        base_url=base_url,
        timeout=5,
        trust_env=False,
    ) as client:
        health = await client.get("/health")
        health.raise_for_status()
        created = await client.post(
            "/api/v1/rooms",
            headers=headers,
            json={
                "nickname": "传输冒烟测试",
                "source": "ai",
                "difficulty": "beginner",
                "style": "classic_mystery",
            },
        )
        created.raise_for_status()
        admission = created.json()

    room_id = admission["roomId"]
    session_token = admission["sessionToken"]
    ws_url = base_url.replace("http://", "ws://").replace("https://", "wss://")
    received: list[dict[str, Any]] = []
    async with connect(
        f"{ws_url}/api/v1/rooms/{room_id}/ws",
        proxy=None,
    ) as websocket:
        await websocket.send(
            command(
                room_id=room_id,
                session_token=session_token,
                command_type="session.hello",
                payload={"lastEventId": 0, "clientVersion": "smoke"},
            )
        )
        await receive_until(websocket, "room.snapshot", received)

        await websocket.send(
            command(
                room_id=room_id,
                session_token=session_token,
                command_type="room.start",
                payload={},
            )
        )
        await receive_until(websocket, "room.started", received)

        await websocket.send(
            command(
                room_id=room_id,
                session_token=session_token,
                command_type="discussion.send",
                payload={"content": "灯光看起来像是一种信号。"},
            )
        )
        await receive_until(websocket, "discussion.created", received)

        await websocket.send(
            command(
                room_id=room_id,
                session_token=session_token,
                command_type="question.submit",
                payload={
                    "clientQuestionId": f"local_{uuid.uuid4().hex}",
                    "content": "门缝里的灯光是在传递求救信号吗？",
                },
            )
        )
        await receive_until(websocket, "question.answered", received)

        before_settlement = json.dumps(received, ensure_ascii=False)
        if '"truth"' in before_settlement or '"keyFacts"' in before_settlement:
            raise AssertionError("truth leaked before game.settled")

        await websocket.send(
            command(
                room_id=room_id,
                session_token=session_token,
                command_type="conclusion.submit",
                payload={
                    "content": (
                        "室友被坏人挟持，用灯光闪烁求救。林夏故意假装钥匙丢了，骗过屋里的人后报警。"
                    )
                },
            )
        )
        settled = await receive_until(websocket, "game.settled", received)
        if not settled["payload"].get("truth"):
            raise AssertionError("game.settled did not include the truth")

    event_types = [str(event["type"]) for event in received]
    print(
        json.dumps(
            {
                "status": "ok",
                "health": health.json(),
                "roomId": room_id,
                "events": event_types,
            },
            ensure_ascii=False,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    args = parser.parse_args()
    asyncio.run(run(args.base_url))


if __name__ == "__main__":
    main()
