import pytest

from bts.sim.engine import simulate
from bts.sim.models import Match
from bts.tracking.possession import Placed, place_events


@pytest.fixture(scope="session")
def match11() -> Match:
    return simulate(11)


@pytest.fixture(scope="session")
def placed11(match11) -> list[Placed]:
    return place_events(match11.meta, match11.events)
