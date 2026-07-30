from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import Field, model_validator

from app.api.dependencies import get_room_manager
from app.domain.models import Difficulty, PuzzleSource, PuzzleStyle
from app.protocol.models import ProtocolModel
from app.rooms.manager import RoomManager

router = APIRouter(prefix="/api/v1/rooms", tags=["rooms"])


class CreateRoomRequest(ProtocolModel):
    nickname: str = Field(min_length=1, max_length=32)
    source: PuzzleSource
    difficulty: Difficulty | None = Difficulty.BEGINNER
    style: PuzzleStyle | None = PuzzleStyle.CLASSIC_MYSTERY

    @model_validator(mode="after")
    def validate_ai_options(self) -> "CreateRoomRequest":
        if self.source is PuzzleSource.AI and (self.difficulty is None or self.style is None):
            raise ValueError("AI rooms require difficulty and style")
        return self


class JoinRoomRequest(ProtocolModel):
    invite_code: str = Field(min_length=6, max_length=6)
    nickname: str = Field(min_length=1, max_length=32)
    client_instance_id: str = Field(min_length=8, max_length=128)


class RoomAdmissionResponse(ProtocolModel):
    room_id: str
    invite_code: str
    player_id: str
    session_token: str
    expires_at: int


@router.post("", response_model=RoomAdmissionResponse, status_code=201)
async def create_room(
    body: CreateRoomRequest,
    manager: Annotated[RoomManager, Depends(get_room_manager)],
) -> RoomAdmissionResponse:
    room, player, token, session = await manager.create_room(
        nickname=body.nickname,
        source=body.source,
        difficulty=body.difficulty,
        style=body.style,
    )
    return RoomAdmissionResponse(
        room_id=room.id,
        invite_code=room.invite_code,
        player_id=player.id,
        session_token=token,
        expires_at=session.expires_at,
    )


@router.post("/join", response_model=RoomAdmissionResponse)
async def join_room(
    body: JoinRoomRequest,
    manager: Annotated[RoomManager, Depends(get_room_manager)],
) -> RoomAdmissionResponse:
    room, player, token, session = await manager.join_room(
        invite_code=body.invite_code,
        nickname=body.nickname,
        client_instance_id=body.client_instance_id,
    )
    return RoomAdmissionResponse(
        room_id=room.id,
        invite_code=room.invite_code,
        player_id=player.id,
        session_token=token,
        expires_at=session.expires_at,
    )
