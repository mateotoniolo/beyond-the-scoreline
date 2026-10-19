import asyncio

from bts.speech.client import SpeechError
from bts.speech.narrator import Narrator
from tests.speech.conftest import StubSpeech


async def _match(client) -> str:
    return (await client.post("/api/matches", json={"seed": 11, "speed": 6000})).json()["match_id"]


async def _finished(client, mid: str) -> None:
    for _ in range(150):
        if (await client.get(f"/api/matches/{mid}")).json()["status"] == "finished":
            return
        await asyncio.sleep(0.2)
    raise AssertionError("match did not finish in time")


async def test_audio_returns_404_when_off(client, app):
    assert app.state.narrator is None  # no Speech settings in tests
    mid = await _match(client)
    for path in (f"/api/matches/{mid}/insights/goal-1/audio", f"/api/matches/{mid}/recap/audio"):
        r = await client.get(path)
        assert r.status_code == 404 and "narration is off" in r.json()["detail"], path


async def test_features_report_narration(client, app):
    assert (await client.get("/api/features")).json()["narration"] is False
    app.state.narrator = Narrator(StubSpeech())
    assert (await client.get("/api/features")).json()["narration"] is True


async def test_insight_audio_404_for_unknown_moment_and_unready_variant(client, app):
    stub = StubSpeech()
    app.state.narrator = Narrator(stub)
    mid = await _match(client)
    await _finished(client, mid)
    moment_id = (await client.get(f"/api/matches/{mid}/moments")).json()[0]["moment_id"]
    r = await client.get(f"/api/matches/{mid}/insights/nope/audio")
    assert r.status_code == 404 and "moment" in r.json()["detail"]
    # Nobody subscribed to fan/es, so that variant was never produced: a guard, not a wait.
    r = await client.get(f"/api/matches/{mid}/insights/{moment_id}/audio?profile=fan&lang=es")
    assert r.status_code == 404 and "not ready" in r.json()["detail"]
    assert stub.ssml == []
    assert (await client.get("/api/matches/nope/recap/audio")).status_code == 404


async def test_insight_audio_returns_cached_mp3(client, app):
    stub = StubSpeech()
    app.state.narrator = Narrator(stub)
    mid = await _match(client)
    await _finished(client, mid)
    insight = (await client.get(f"/api/matches/{mid}/insights?profile=analyst&lang=en")).json()[0]
    path = f"/api/matches/{mid}/insights/{insight['moment_id']}/audio?profile=analyst&lang=en"
    r = await client.get(path)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "audio/mpeg" and r.content.startswith(b"ID3")
    assert r.headers["cache-control"] == "private, max-age=86400"
    assert (await client.get(path)).content == r.content and len(stub.ssml) == 1
    assert "en-US-AndrewMultilingualNeural" in stub.ssml[0]
    assert insight["headline"].split()[0] in stub.ssml[0]


async def test_recap_audio_returns_mp3_in_the_requested_voice(client, app):
    stub = StubSpeech()
    app.state.narrator = Narrator(stub)
    mid = await _match(client)
    await _finished(client, mid)
    r = await client.get(f"/api/matches/{mid}/recap/audio?profile=fan&lang=es")
    assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg"
    assert "es-AR-ElenaNeural" in stub.ssml[0]
    recap = (await client.get(f"/api/matches/{mid}/recap?profile=fan&lang=es")).json()
    assert recap["title"].split()[0] in stub.ssml[0]
    again = await client.get(f"/api/matches/{mid}/recap/audio?profile=fan&lang=es")
    assert again.status_code == 200 and len(stub.ssml) == 1


async def test_audio_returns_503_when_speech_fails(client, app):
    app.state.narrator = Narrator(StubSpeech(fail=SpeechError("speech 429: busy")))
    mid = await _match(client)
    await _finished(client, mid)
    r = await client.get(f"/api/matches/{mid}/recap/audio")
    assert r.status_code == 503 and "429" in r.json()["detail"]
