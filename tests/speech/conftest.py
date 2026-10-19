import pytest

from bts.insights import templates
from bts.insights.schemas import Insight, Recap
from bts.sim.engine import simulate
from bts.speech.client import SpeechError
from tests.insights.conftest import run_detector


@pytest.fixture(scope="session")
def board():
    """Statistics and moments of seed 11 at full time."""
    return run_detector(simulate(11))


@pytest.fixture
def snap(board):
    return board[0]


@pytest.fixture
def moments(board):
    return board[1]


@pytest.fixture
def moment(moments):
    return next(m for m in moments if m.type == "goal")


@pytest.fixture
def insight_fan_es(moment, snap) -> Insight:
    return templates.render_insight(moment, snap, "fan", "es")


@pytest.fixture
def insights_three(moments, snap) -> list[Insight]:
    return [templates.render_insight(m, snap, "analyst", "en") for m in moments[:3]]


@pytest.fixture
def recap_en(snap, moments) -> Recap:
    return templates.render_recap(snap, moments, "analyst", "en")


class StubSpeech:
    """A synthesizer that records every SSML it receives and answers with fake MP3 bytes."""

    def __init__(self, fail: SpeechError | None = None) -> None:
        self.ssml: list[str] = []
        self.fail = fail

    async def synthesize(self, ssml: str) -> bytes:
        self.ssml.append(ssml)
        if self.fail is not None:
            raise self.fail
        return b"ID3" + str(len(self.ssml)).encode()
