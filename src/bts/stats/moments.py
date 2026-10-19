"""Rule-based detection of key moments from the event stream and the match state."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from bts.sim.models import Event
from bts.stats.state import MatchState

MomentType = Literal[
    "goal", "big_chance", "momentum_shift", "pressure_spike", "milestone", "card", "period_end"
]


class Moment(BaseModel):
    moment_id: str
    type: MomentType
    t: float
    clock: str
    team_id: str | None
    player_id: str | None
    event_ids: list[int]
    facts: dict[str, float | int | str]
    severity: float


@dataclass(frozen=True)
class MomentThresholds:
    big_chance_xg: float = 0.30
    momentum_delta: float = 0.6
    momentum_window_s: float = 300.0
    momentum_min_abs: float = 0.35
    momentum_min_gap_s: float = 600.0
    pressure_count: int = 6
    pressure_window_s: float = 120.0
    possession_milestone_pct: float = 65.0
    possession_milestone_minutes: tuple[int, ...] = (30, 60)
    player_shots_milestone: int = 4
    player_passes_milestone: int = 60


class KeyMomentDetector:
    def __init__(self, thresholds: MomentThresholds | None = None) -> None:
        self.th = thresholds or MomentThresholds()
        self._momentum_history: deque[tuple[float, float]] = deque()
        self._pressures: dict[str, deque[tuple[float, int]]] = {}
        self._fired: set[tuple] = set()
        self._last_shift_t = -1e9

    def observe(self, event: Event, state: MatchState) -> Moment | None:
        """Return at most one moment for ``event`` (already ingested into ``state``)."""
        snap = state.snapshot()
        moment = (
            self._goal_or_chance(event, state)
            or self._card(event, state)
            or self._period_end(event, state)
            or self._pressure_spike(event, state)
            or self._momentum_shift(event, state, snap.momentum)
            or self._milestone(event, state)
        )
        self._momentum_history.append((event.t, snap.momentum))
        while (
            self._momentum_history
            and self._momentum_history[0][0] < event.t - self.th.momentum_window_s
        ):
            self._momentum_history.popleft()
        return moment

    # ------------------------------------------------------------------ rules
    def _make(self, type_: MomentType, e: Event, *, team_id, player_id, facts, severity) -> Moment:
        return Moment(
            moment_id=f"{type_}-{e.event_id}",
            type=type_,
            t=e.t,
            clock=e.clock,
            team_id=team_id,
            player_id=player_id,
            event_ids=[e.event_id],
            facts=facts,
            severity=severity,
        )

    def _goal_or_chance(self, e: Event, state: MatchState) -> Moment | None:
        if e.type != "shot":
            return None
        xg = float(e.meta.get("xg", 0.0))
        home, away = state.score
        if e.outcome == "goal":
            facts = {
                "xg": xg,
                "score_home": home,
                "score_away": away,
                "zone": str(e.meta.get("zone", "")),
            }
            return self._make(
                "goal", e, team_id=e.team_id, player_id=e.player_id, facts=facts, severity=1.0
            )
        if xg >= self.th.big_chance_xg:
            facts = {"xg": xg, "outcome": e.outcome or "", "zone": str(e.meta.get("zone", ""))}
            return self._make(
                "big_chance", e, team_id=e.team_id, player_id=e.player_id, facts=facts, severity=0.6
            )
        return None

    def _card(self, e: Event, state: MatchState) -> Moment | None:
        if e.type != "card":
            return None
        colour = e.subtype or "yellow"
        return self._make(
            "card",
            e,
            team_id=e.team_id,
            player_id=e.player_id,
            facts={"colour": colour, "fouls": state.team(e.team_id).fouls},
            severity=0.9 if colour == "red" else 0.3,
        )

    def _period_end(self, e: Event, state: MatchState) -> Moment | None:
        if e.type != "period_end":
            return None
        home, away = state.score
        return self._make(
            "period_end",
            e,
            team_id=None,
            player_id=None,
            facts={"period": e.period, "score_home": home, "score_away": away},
            severity=0.5,
        )

    def _pressure_spike(self, e: Event, state: MatchState) -> Moment | None:
        if e.type != "pressure":
            return None
        q = self._pressures.setdefault(e.team_id, deque())
        q.append((e.t, e.event_id))
        while q and q[0][0] < e.t - self.th.pressure_window_s:
            q.popleft()
        if len(q) < self.th.pressure_count:
            return None
        key = ("pressure_spike", e.team_id, round(e.t // self.th.pressure_window_s))
        if key in self._fired:
            return None
        self._fired.add(key)
        moment = self._make(
            "pressure_spike",
            e,
            team_id=e.team_id,
            player_id=None,
            facts={"count": len(q), "window_s": self.th.pressure_window_s},
            severity=0.5,
        )
        moment.event_ids = [eid for _, eid in q]
        q.clear()
        return moment

    def _momentum_shift(self, e: Event, state: MatchState, momentum: float) -> Moment | None:
        if not self._momentum_history or e.type in ("period_start", "period_end"):
            return None
        earliest_t, earliest_m = self._momentum_history[0]
        delta = momentum - earliest_m
        if (
            abs(delta) < self.th.momentum_delta
            or abs(momentum) < self.th.momentum_min_abs
            or e.t - self._last_shift_t < self.th.momentum_min_gap_s
        ):
            return None
        self._last_shift_t = e.t
        team_id = state.home_id if delta > 0 else state.away_id
        return self._make(
            "momentum_shift",
            e,
            team_id=team_id,
            player_id=None,
            facts={
                "momentum_before": round(earliest_m, 3),
                "momentum_now": round(momentum, 3),
                "since_t": earliest_t,
            },
            severity=min(1.0, abs(delta)),
        )

    def _milestone(self, e: Event, state: MatchState) -> Moment | None:
        minute = int(e.t // 60)
        for mark in self.th.possession_milestone_minutes:
            if minute >= mark:
                for tid in (state.home_id, state.away_id):
                    key = ("possession", tid, mark)
                    pct = state.team(tid).possession_pct
                    if key not in self._fired and pct >= self.th.possession_milestone_pct:
                        self._fired.add(key)
                        return self._make(
                            "milestone",
                            e,
                            team_id=tid,
                            player_id=None,
                            facts={"kind": "possession", "pct": pct, "minute": mark},
                            severity=0.4,
                        )
        if e.player_id and e.type in ("pass", "shot"):
            ps = state.player(e.player_id)
            if e.type == "shot" and ps.shots == self.th.player_shots_milestone:
                key = ("shots", e.player_id)
                if key not in self._fired:
                    self._fired.add(key)
                    return self._make(
                        "milestone",
                        e,
                        team_id=e.team_id,
                        player_id=e.player_id,
                        facts={"kind": "shots", "shots": ps.shots, "xg": ps.xg},
                        severity=0.3,
                    )
            if e.type == "pass" and ps.passes == self.th.player_passes_milestone:
                key = ("passes", e.player_id)
                if key not in self._fired:
                    self._fired.add(key)
                    return self._make(
                        "milestone",
                        e,
                        team_id=e.team_id,
                        player_id=e.player_id,
                        facts={
                            "kind": "passes",
                            "passes": ps.passes,
                            "completed": ps.passes_completed,
                        },
                        severity=0.3,
                    )
        return None
