"""One real round trip to Azure AI Speech; skipped without BTS_SPEECH_KEY and BTS_SPEECH_REGION."""

import pytest

from bts.config import Settings
from bts.speech.client import SpeechClient
from bts.speech.ssml import build_ssml

settings = Settings()  # reads .env on purpose: this test is meant to reach the service
pytestmark = pytest.mark.skipif(
    not (settings.speech_key and settings.speech_region), reason="BTS_SPEECH_KEY not set"
)


async def test_live_synthesis_returns_mp3():
    client = SpeechClient(
        settings.speech_key or "", settings.speech_region or "", endpoint=settings.speech_endpoint
    )
    try:
        audio = await client.synthesize(build_ssml(["Narration check."], "en", "analyst"))
    finally:
        await client.aclose()
    assert audio[:3] == b"ID3" or audio[:1] == b"\xff"
    assert len(audio) > 1000
