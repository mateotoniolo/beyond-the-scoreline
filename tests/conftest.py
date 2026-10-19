import httpx
import pytest

from bts.api.app import create_app
from bts.config import Settings


@pytest.fixture
def app():
    # Hermetic: ignore any local .env so tests never reach a real model endpoint.
    return create_app(Settings(_env_file=None))


@pytest.fixture
async def client(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
