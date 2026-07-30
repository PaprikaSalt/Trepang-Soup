from time import time
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app import APP_VERSION
from app.protocol.constants import PROTOCOL_VERSION

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    model_config = ConfigDict(serialize_by_alias=True)

    status: Literal["ok"] = "ok"
    version: str = APP_VERSION
    protocol_version: int = Field(default=PROTOCOL_VERSION, alias="protocolVersion")
    server_time: int = Field(alias="serverTime")


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(serverTime=int(time() * 1000))
