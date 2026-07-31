from collections.abc import AsyncIterator

import pytest
from app.config import Settings
from app.main import create_app
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=create_app(Settings(app_env="test", _env_file=None)))
    async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        yield test_client
