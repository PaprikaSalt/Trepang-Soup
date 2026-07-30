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
        raw = await asyncio.wait_for(websocket.recv(), timeout=90)
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
        timeout=130,
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
        joined = await client.post(
            "/api/v1/rooms/join",
            headers=headers,
            json={
                "nickname": "第二客户端",
                "inviteCode": admission["inviteCode"],
                "clientInstanceId": f"smoke_{uuid.uuid4().hex}",
            },
        )
        joined.raise_for_status()
        guest_admission = joined.json()

    room_id = admission["roomId"]
    ws_url = base_url.replace("http://", "ws://").replace("https://", "wss://")
    host_received: list[dict[str, Any]] = []
    guest_received: list[dict[str, Any]] = []
    async with (
        connect(
            f"{ws_url}/api/v1/rooms/{room_id}/ws",
            proxy=None,
        ) as host_websocket,
        connect(
            f"{ws_url}/api/v1/rooms/{room_id}/ws",
            proxy=None,
        ) as guest_websocket,
    ):
        await host_websocket.send(
            command(
                room_id=room_id,
                session_token=admission["sessionToken"],
                command_type="session.hello",
                payload={"lastEventId": 0, "clientVersion": "smoke-host"},
            )
        )
        await guest_websocket.send(
            command(
                room_id=room_id,
                session_token=guest_admission["sessionToken"],
                command_type="session.hello",
                payload={"lastEventId": 0, "clientVersion": "smoke-guest"},
            )
        )
        host_snapshot = await receive_until(
            host_websocket,
            "room.snapshot",
            host_received,
        )
        guest_snapshot = await receive_until(
            guest_websocket,
            "room.snapshot",
            guest_received,
        )
        if len(host_snapshot["payload"]["players"]) != 2:
            raise AssertionError("host snapshot did not contain both players")
        if len(guest_snapshot["payload"]["players"]) != 2:
            raise AssertionError("guest snapshot did not contain both players")

        await host_websocket.send(
            command(
                room_id=room_id,
                session_token=admission["sessionToken"],
                command_type="room.start",
                payload={},
            )
        )
        await asyncio.gather(
            receive_until(host_websocket, "room.started", host_received),
            receive_until(guest_websocket, "room.started", guest_received),
        )

        await guest_websocket.send(
            command(
                room_id=room_id,
                session_token=guest_admission["sessionToken"],
                command_type="discussion.send",
                payload={"content": "第二客户端看到了一种可能的信号。"},
            )
        )
        await asyncio.gather(
            receive_until(host_websocket, "discussion.created", host_received),
            receive_until(guest_websocket, "discussion.created", guest_received),
        )

        await host_websocket.send(
            command(
                room_id=room_id,
                session_token=admission["sessionToken"],
                command_type="question.submit",
                payload={
                    "clientQuestionId": f"local_{uuid.uuid4().hex}",
                    "content": "这个异常行为是当事人有意做出的吗？",
                },
            )
        )
        await asyncio.gather(
            receive_until(host_websocket, "question.answered", host_received),
            receive_until(guest_websocket, "question.answered", guest_received),
        )

        await guest_websocket.send(
            command(
                room_id=room_id,
                session_token=guest_admission["sessionToken"],
                command_type="hint.request",
                payload={},
            )
        )
        await asyncio.gather(
            receive_until(host_websocket, "hint.created", host_received),
            receive_until(guest_websocket, "hint.created", guest_received),
        )

        before_settlement = json.dumps(
            [*host_received, *guest_received],
            ensure_ascii=False,
        )
        if '"truth"' in before_settlement or '"keyFacts"' in before_settlement:
            raise AssertionError("truth leaked before game.settled")

        await host_websocket.send(
            command(
                room_id=room_id,
                session_token=admission["sessionToken"],
                command_type="conclusion.give_up",
                payload={},
            )
        )
        settled_events = await asyncio.gather(
            receive_until(host_websocket, "game.settled", host_received),
            receive_until(guest_websocket, "game.settled", guest_received),
        )
        if any(not event["payload"].get("truth") for event in settled_events):
            raise AssertionError("game.settled did not include the truth")

    event_types = [str(event["type"]) for event in host_received]
    guest_event_types = [str(event["type"]) for event in guest_received]
    print(
        json.dumps(
            {
                "status": "ok",
                "health": health.json(),
                "roomId": room_id,
                "clients": 2,
                "hostEvents": event_types,
                "guestEvents": guest_event_types,
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
