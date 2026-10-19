"""A replay of seed 11 that satisfies the ``LiveMatch`` protocol and can advance on demand."""

from __future__ import annotations

import pytest

from bts.insights.schemas import Insight, Lang, Profile
from bts.sim.models import Event, Match, MatchMeta
from bts.stats.moments import KeyMomentDetector, Moment
from bts.stats.state import MatchState, StatsSnapshot


class ReplayMatch:
    def __init__(self, match: Match) -> None:
        self.match_id = f"{match.meta.seed}-replay"
        self.meta: MatchMeta = match.meta
        self.status = "running"
        self.events: list[Event] = []
        self.moments: list[Moment] = []
        self.insights: dict[tuple[str, Profile, Lang], Insight] = {}
        self._pending = list(match.events)
        self._state = MatchState(match.meta)
        self._detector = KeyMomentDetector()

    def advance(self, n: int) -> None:
        for event in self._pending[:n]:
            self._state.ingest(event)
            self.events.append(event)
            moment = self._detector.observe(event, self._state)
            if moment is not None:
                self.moments.append(moment)
        del self._pending[:n]
        if not self._pending:
            self.status = "finished"

    def advance_past_first_goal(self) -> None:
        while self._pending and not any(m.type == "goal" for m in self.moments):
            self.advance(1)
        self.advance(50)

    def snapshot(self) -> StatsSnapshot:
        return self._state.snapshot()

    def cached_insight(self, moment_id: str, profile: Profile, lang: Lang) -> Insight | None:
        return self.insights.get((moment_id, profile, lang))


@pytest.fixture
def live(match11) -> ReplayMatch:
    replay = ReplayMatch(match11)
    replay.advance_past_first_goal()
    return replay
