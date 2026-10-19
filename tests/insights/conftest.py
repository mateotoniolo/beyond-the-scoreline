import pytest

from bts.sim.engine import simulate
from bts.sim.models import Match
from bts.stats.moments import KeyMomentDetector, Moment
from bts.stats.state import MatchState, StatsSnapshot


def run_detector(match: Match) -> tuple[StatsSnapshot, list[Moment]]:
    state = MatchState(match.meta)
    detector = KeyMomentDetector()
    moments: list[Moment] = []
    for e in match.events:
        state.ingest(e)
        m = detector.observe(e, state)
        if m is not None:
            moments.append(m)
    return state.snapshot(), moments


@pytest.fixture(scope="session")
def match11() -> Match:
    return simulate(11)


@pytest.fixture(scope="session")
def detected11(match11):
    return run_detector(match11)


@pytest.fixture
def moment(detected11):
    _, moments = detected11
    return next(m for m in moments if m.type == "goal")


@pytest.fixture
def snap(detected11):
    return detected11[0]


@pytest.fixture
def recent(match11):
    return match11.events[-12:]


@pytest.fixture
def goalless_snap(match11):
    return MatchState(match11.meta).snapshot()
