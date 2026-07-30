from pathlib import Path

from app.config import Settings
from app.main import create_app
from app.security.admin import (
    AdminChallenge,
    PasswordKdf,
    derive_challenge_response,
)
from httpx import ASGITransport, AsyncClient
from pwdlib import PasswordHash

PROTOCOL_HEADERS = {"X-Protocol-Version": "1"}


async def login(client: AsyncClient, password: str) -> str:
    challenge_response = await client.get(
        "/api/v1/admin/challenge",
        headers=PROTOCOL_HEADERS,
    )
    assert challenge_response.status_code == 200
    body = challenge_response.json()
    kdf = body["passwordKdf"]
    challenge = AdminChallenge(
        id=body["challengeId"],
        nonce=body["nonce"],
        issued_at=body["issuedAt"],
        expires_at=body["expiresAt"],
        kdf=PasswordKdf(
            salt=kdf["salt"],
            time_cost=kdf["timeCost"],
            memory_cost=kdf["memoryCost"],
            parallelism=kdf["parallelism"],
            hash_length=kdf["hashLength"],
        ),
    )
    response = derive_challenge_response(password, challenge)
    login_response = await client.post(
        "/api/v1/admin/login",
        headers=PROTOCOL_HEADERS,
        json={
            "challengeId": challenge.id,
            "timestamp": challenge.issued_at,
            "response": response,
        },
    )
    assert login_response.status_code == 200
    return str(login_response.json()["accessToken"])


async def test_admin_crud_export_import_and_library_room(tmp_path: Path) -> None:
    password = "a dedicated admin password"
    settings = Settings(
        app_env="test",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'admin.db'}",
        admin_password_hash=PasswordHash.recommended().hash(password),
        recent_puzzle_window=10,
        _env_file=None,
    )
    application = create_app(settings)
    await application.state.puzzle_repository.initialize()
    transport = ASGITransport(app=application)
    try:
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            unauthorized = await client.get(
                "/api/v1/admin/puzzles",
                headers=PROTOCOL_HEADERS,
            )
            assert unauthorized.status_code == 401

            token = await login(client, password)
            admin_headers = {
                **PROTOCOL_HEADERS,
                "Authorization": f"Bearer {token}",
            }
            puzzle_body = {
                "title": "最后一班电梯",
                "surface": "男人每天乘电梯回家，只有下雨天会直接到达自己的楼层。",
                "truth": (
                    "男人身材矮小，平时只能按到较低楼层再走楼梯。"
                    "下雨天能用手中的长雨伞按到高处按钮，所以能够直接回到自己的楼层。"
                ),
                "keyFacts": ["男人身材矮小", "雨伞帮助他按到高处按钮"],
                "active": True,
            }
            created = await client.post(
                "/api/v1/admin/puzzles",
                headers=admin_headers,
                json=puzzle_body,
            )
            assert created.status_code == 201
            puzzle_id = created.json()["id"]

            listed = await client.get("/api/v1/admin/puzzles", headers=admin_headers)
            assert listed.json()["total"] == 1
            assert listed.json()["items"][0]["truth"] == puzzle_body["truth"]

            room_response = await client.post(
                "/api/v1/rooms",
                headers=PROTOCOL_HEADERS,
                json={"nickname": "海盐", "source": "library"},
            )
            assert room_response.status_code == 201
            room_id = room_response.json()["roomId"]
            assert application.state.room_manager.rooms[room_id].puzzle.id == puzzle_id

            exported = await client.get(
                "/api/v1/admin/puzzles/export",
                headers=admin_headers,
            )
            assert exported.status_code == 200
            export_body = exported.json()
            assert export_body["schemaVersion"] == 1
            assert export_body["puzzles"][0]["id"] == puzzle_id

            deleted = await client.delete(
                f"/api/v1/admin/puzzles/{puzzle_id}",
                headers=admin_headers,
            )
            assert deleted.status_code == 204
            imported = await client.post(
                "/api/v1/admin/puzzles/import",
                headers=admin_headers,
                json={"mode": "replace", "puzzles": export_body["puzzles"]},
            )
            assert imported.status_code == 200
            assert imported.json() == {"imported": 1}
    finally:
        await application.state.room_manager.shutdown()
        await application.state.puzzle_repository.close()
