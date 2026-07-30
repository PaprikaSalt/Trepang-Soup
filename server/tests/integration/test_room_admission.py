import asyncio
from typing import cast

from app.protocol.constants import PROTOCOL_VERSION
from httpx import AsyncClient

HEADERS = {"X-Protocol-Version": str(PROTOCOL_VERSION)}


async def create_room(
    client: AsyncClient,
    *,
    nickname: str = "海盐",
) -> dict[str, object]:
    response = await client.post(
        "/api/v1/rooms",
        headers=HEADERS,
        json={
            "nickname": nickname,
            "source": "ai",
            "difficulty": "beginner",
            "style": "classic_mystery",
        },
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, object], response.json())


async def test_create_and_join_room(client: AsyncClient) -> None:
    created = await create_room(client)

    assert str(created["roomId"]).startswith("room_")
    assert str(created["playerId"]).startswith("player_")
    assert len(str(created["inviteCode"])) == 6
    assert len(str(created["sessionToken"])) >= 32

    response = await client.post(
        "/api/v1/rooms/join",
        headers=HEADERS,
        json={
            "inviteCode": created["inviteCode"],
            "nickname": "小七",
            "clientInstanceId": "client-installation-seven",
        },
    )

    assert response.status_code == 200
    joined = response.json()
    assert joined["roomId"] == created["roomId"]
    assert joined["inviteCode"] == created["inviteCode"]
    assert joined["playerId"] != created["playerId"]
    assert joined["sessionToken"] != created["sessionToken"]


async def test_join_rejects_unicode_equivalent_nickname(client: AsyncClient) -> None:
    created = await create_room(client, nickname="\uff21lice")

    response = await client.post(
        "/api/v1/rooms/join",
        headers=HEADERS,
        json={
            "inviteCode": created["inviteCode"],
            "nickname": "alice",
            "clientInstanceId": "client-installation-alice",
        },
    )

    assert response.status_code == 409
    assert response.json()["code"] == "NICKNAME_TAKEN"


async def test_join_rejects_unknown_invite_code(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/rooms/join",
        headers=HEADERS,
        json={
            "inviteCode": "ZZZZZZ",
            "nickname": "小七",
            "clientInstanceId": "client-installation-seven",
        },
    )

    assert response.status_code == 404
    assert response.json()["code"] == "ROOM_NOT_FOUND"


async def test_resume_rotates_session_token(client: AsyncClient) -> None:
    created = await create_room(client)
    old_token = created["sessionToken"]
    payload = {
        "roomId": created["roomId"],
        "sessionToken": old_token,
        "lastEventId": 0,
    }

    response = await client.post(
        "/api/v1/sessions/resume",
        headers=HEADERS,
        json=payload,
    )

    assert response.status_code == 200
    resumed = response.json()
    assert resumed["roomId"] == created["roomId"]
    assert resumed["playerId"] == created["playerId"]
    assert resumed["sessionToken"] != old_token
    assert resumed["snapshotVersion"] == 0

    reused = await client.post(
        "/api/v1/sessions/resume",
        headers=HEADERS,
        json=payload,
    )
    assert reused.status_code == 401
    assert reused.json()["code"] == "SESSION_INVALID"


async def test_concurrent_resume_only_rotates_token_once(client: AsyncClient) -> None:
    created = await create_room(client)
    payload = {
        "roomId": created["roomId"],
        "sessionToken": created["sessionToken"],
        "lastEventId": 0,
    }

    first, second = await asyncio.gather(
        client.post("/api/v1/sessions/resume", headers=HEADERS, json=payload),
        client.post("/api/v1/sessions/resume", headers=HEADERS, json=payload),
    )

    assert sorted((first.status_code, second.status_code)) == [200, 401]


async def test_create_validates_ai_options(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/rooms",
        headers=HEADERS,
        json={
            "nickname": "海盐",
            "source": "ai",
            "difficulty": None,
            "style": None,
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
