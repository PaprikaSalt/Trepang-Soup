from typing import cast

from fastapi import Request

from app.rooms.manager import RoomManager


async def get_room_manager(request: Request) -> RoomManager:
    return cast(RoomManager, request.app.state.room_manager)
