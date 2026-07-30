from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import Field, SecretStr

from app.api.dependencies import get_room_manager
from app.protocol.models import ProtocolModel
from app.rooms.manager import RoomManager

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


class ResumeSessionRequest(ProtocolModel):
    room_id: str = Field(min_length=6, max_length=80, pattern=r"^room_[A-Za-z0-9_-]+$")
    session_token: SecretStr
    last_event_id: int = Field(default=0, ge=0)


class ResumeSessionResponse(ProtocolModel):
    room_id: str
    player_id: str
    session_token: str
    expires_at: int
    snapshot_version: int


@router.post("/resume", response_model=ResumeSessionResponse)
async def resume_session(
    body: ResumeSessionRequest,
    manager: Annotated[RoomManager, Depends(get_room_manager)],
) -> ResumeSessionResponse:
    room, old_session, new_token, new_session = await manager.resume_session(
        body.room_id,
        body.session_token.get_secret_value(),
    )
    return ResumeSessionResponse(
        room_id=room.id,
        player_id=old_session.player_id,
        session_token=new_token,
        expires_at=new_session.expires_at,
        snapshot_version=room.event_sequence,
    )
