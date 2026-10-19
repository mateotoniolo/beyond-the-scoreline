import pytest

from bts.config import Settings
from bts.speech import make_narrator
from bts.speech.client import SpeechError
from bts.speech.narrator import Narrator
from tests.speech.conftest import StubSpeech


async def test_insight_audio_is_cached_per_match_and_insight(insight_fan_es):
    stub = StubSpeech()
    n = Narrator(stub)
    first = await n.narrate_insight("m1", insight_fan_es)
    assert first == await n.narrate_insight("m1", insight_fan_es)
    assert len(stub.ssml) == 1 and "es-AR-ElenaNeural" in stub.ssml[0]
    assert await n.narrate_insight("m2", insight_fan_es) != first
    assert len(stub.ssml) == 2 and n.cache_size == 2


async def test_recap_audio_is_keyed_by_its_text(recap_en):
    stub = StubSpeech()
    n = Narrator(stub)
    await n.narrate_recap("m1", recap_en)
    await n.narrate_recap("m1", recap_en)
    assert len(stub.ssml) == 1 and "en-US-AndrewMultilingualNeural" in stub.ssml[0]
    await n.narrate_recap("m1", recap_en.model_copy(update={"paragraphs": ["Different."]}))
    assert len(stub.ssml) == 2


async def test_characters_count_what_was_sent(insight_fan_es):
    n = Narrator(StubSpeech())
    await n.narrate_insight("m1", insight_fan_es)
    assert n.characters == len(insight_fan_es.headline) + len(insight_fan_es.why_it_matters)


async def test_failure_propagates_and_is_not_cached(insight_fan_es):
    stub = StubSpeech(fail=SpeechError("speech 429: busy"))
    n = Narrator(stub)
    with pytest.raises(SpeechError, match="429"):
        await n.narrate_insight("m1", insight_fan_es)
    assert n.cache_size == 0
    stub.fail = None
    assert await n.narrate_insight("m1", insight_fan_es)
    assert len(stub.ssml) == 2


async def test_cache_is_bounded_fifo(insights_three):
    stub = StubSpeech()
    n = Narrator(stub, cache_max=2)
    for insight in insights_three:
        await n.narrate_insight("m1", insight)
    await n.narrate_insight("m1", insights_three[0])  # evicted, synthesised again
    assert len(stub.ssml) == 4 and n.cache_size == 2


def test_make_narrator_follows_the_flag():
    assert make_narrator(Settings(_env_file=None)) is None
    on = make_narrator(Settings(_env_file=None, speech_key="k", speech_region="eastus2"))
    assert isinstance(on, Narrator)
    assert on.client.url == "https://eastus2.tts.speech.microsoft.com/cognitiveservices/v1"
    off = Settings(_env_file=None, speech_key="k", speech_region="eastus2", speech_enabled=False)
    assert make_narrator(off) is None
    assert make_narrator(Settings(_env_file=None, speech_enabled=True)) is None  # no key: off
