import httpx
import pytest

from bts.api.app import create_app
from bts.config import Settings


@pytest.fixture
def app(monkeypatch):
    # Hermetic: ignore the local .env and the shell so tests never reach real services.
    live = (
        "BTS_FOUNDRY_ENDPOINT",
        "BTS_FOUNDRY_API_KEY",
        "BTS_COSMOS_ENDPOINT",
        "BTS_COSMOS_KEY",
        "BTS_SPEECH_KEY",
        "BTS_SPEECH_REGION",
    )
    for name in live:
        monkeypatch.delenv(name, raising=False)
    return create_app(Settings(_env_file=None))


@pytest.fixture
async def client(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
