"""Deterministic, incremental match statistics built from the event stream.

Nothing here calls a model. ``MatchState.ingest`` is O(1) per event for the full-match
counters; ``snapshot`` additionally aggregates the last five minutes from a small deque.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from pydantic import BaseModel

from bts.sim.models import Event, MatchMeta, clock_str

FINAL_THIRD_X = 200 / 3
WINDOW_S = 300.0
PRESSURE_WINDOW_S = 120.0
MOMENTUM_SCALE = 3.0
MOMENTUM_SMOOTHING = 0.3
DEFENSIVE_ACTIONS = {"pressure", "foul", "card"}


class TeamStats(BaseModel):
    passes: int = 0
    passes_completed: int = 0
    pass_accuracy: float = 0.0
    shots: int = 0
    shots_on_target: int = 0
    goals: int = 0
    xg: float = 0.0
    possession_seconds: float = 0.0
    possession_pct: float = 50.0
    pressures: int = 0
    tackles_won: int = 0
    fouls: int = 0
    final_third_entries: int = 0


class PlayerStats(BaseModel):
    player_id: str
    name: str
    team_id: str
    passes: int = 0
    passes_completed: int = 0
    shots: int = 0
    goals: int = 0
    xg: float = 0.0
    pressures: int = 0
    key_passes: int = 0


class StatsSnapshot(BaseModel):
    t: float
    clock: str
    score: tuple[int, int]
    home_id: str
    away_id: str
    team_names: dict[str, str]
    teams: dict[str, TeamStats]
    players: dict[str, PlayerStats]
    momentum: float
    pressure_index: dict[str, float]
    last5: dict[str, TeamStats]


def _clip(v: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _is_final_third_entry(e: Event) -> bool:
    if "final_third_entry" in e.tags:
        return True
    return (
        e.type in ("pass", "carry")
        and e.outcome == "success"
        and e.end is not None
        and e.start.x < FINAL_THIRD_X <= e.end.x
    )


def _threat(e: Event) -> float:
    """Observable attacking threat carried by one event."""
    value = 0.0
    if e.type == "shot":
        value += float(e.meta.get("xg", 0.0))
    if _is_final_third_entry(e):
        value += 0.05
    if e.type == "pressure":
        value += 0.02
    return value


@dataclass
class _TeamCounter:
    passes: int = 0
    passes_completed: int = 0
    shots: int = 0
    shots_on_target: int = 0
    goals: int = 0
    xg: float = 0.0
    pressures: int = 0
    tackles_won: int = 0
    fouls: int = 0
    final_third_entries: int = 0

    def add(self, e: Event) -> None:
        if e.type == "pass":
            self.passes += 1
            if e.outcome == "success":
                self.passes_completed += 1
        elif e.type == "shot":
            self.shots += 1
            self.xg += float(e.meta.get("xg", 0.0))
            if e.outcome in ("goal", "saved"):
                self.shots_on_target += 1
            if e.outcome == "goal":
                self.goals += 1
        elif e.type == "pressure":
            self.pressures += 1
        elif e.type == "duel" and e.subtype == "tackle" and e.outcome == "success":
            self.tackles_won += 1
        elif e.type == "foul":
            self.fouls += 1
        if _is_final_third_entry(e):
            self.final_third_entries += 1

    def to_stats(self, possession_seconds: float, total_possession: float) -> TeamStats:
        pct = 50.0 if total_possession <= 0 else 100.0 * possession_seconds / total_possession
        return TeamStats(
            passes=self.passes,
            passes_completed=self.passes_completed,
            pass_accuracy=(self.passes_completed / self.passes) if self.passes else 0.0,
            shots=self.shots,
            shots_on_target=self.shots_on_target,
            goals=self.goals,
            xg=round(self.xg, 3),
            possession_seconds=round(possession_seconds, 1),
            possession_pct=round(pct, 2),
            pressures=self.pressures,
            tackles_won=self.tackles_won,
            fouls=self.fouls,
            final_third_entries=self.final_third_entries,
        )


@dataclass
class _Possession:
    """Credits elapsed time to the side that had the ball at the previous event."""

    home_id: str
    away_id: str
    team: str | None = None
    t: float = 0.0
    seconds: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.seconds = {self.home_id: 0.0, self.away_id: 0.0}

    def _other(self, team_id: str) -> str:
        return self.away_id if team_id == self.home_id else self.home_id

    def observe(self, e: Event) -> None:
        if self.team is not None:
            self.seconds[self.team] += max(0.0, e.t - self.t)
        self.t = e.t
        if e.type in ("period_start", "period_end"):
            self.team = None
        elif e.type == "substitution":
            pass
        elif e.type in DEFENSIVE_ACTIONS or (e.type == "duel" and e.outcome != "success"):
            self.team = self._other(e.team_id)
        else:
            self.team = e.team_id


def aggregate(meta: MatchMeta, events: list[Event]) -> dict[str, TeamStats]:
    """Team statistics over an arbitrary event list (used for rolling windows)."""
    home, away = meta.home.team_id, meta.away.team_id
    counters = {home: _TeamCounter(), away: _TeamCounter()}
    possession = _Possession(home, away)
    for e in events:
        possession.observe(e)
        if e.team_id in counters:
            counters[e.team_id].add(e)
    total = sum(possession.seconds.values())
    return {tid: counters[tid].to_stats(possession.seconds[tid], total) for tid in (home, away)}


class MatchState:
    def __init__(self, meta: MatchMeta) -> None:
        self.meta = meta
        self.home_id = meta.home.team_id
        self.away_id = meta.away.team_id
        self._counters = {self.home_id: _TeamCounter(), self.away_id: _TeamCounter()}
        self._possession = _Possession(self.home_id, self.away_id)
        self._players: dict[str, PlayerStats] = {}
        self._names = {p.player_id: p.name for t in (meta.home, meta.away) for p in t.players}
        self._window: deque[Event] = deque()
        self._recent: deque[Event] = deque(maxlen=64)
        self._score = {self.home_id: 0, self.away_id: 0}
        self._momentum = 0.0
        self._t = 0.0
        self._n = 0

    # ------------------------------------------------------------------ ingest
    def ingest(self, event: Event) -> None:
        self._n += 1
        self._t = event.t
        self._possession.observe(event)
        if event.team_id in self._counters:
            self._counters[event.team_id].add(event)
        if event.type == "shot" and event.outcome == "goal":
            self._score[event.team_id] += 1
        if event.player_id:
            self._add_player(event)
        self._window.append(event)
        self._recent.append(event)
        while self._window and self._window[0].t < event.t - WINDOW_S:
            self._window.popleft()
        self._update_momentum()

    def _player(self, player_id: str, team_id: str) -> PlayerStats:
        ps = self._players.get(player_id)
        if ps is None:
            ps = PlayerStats(
                player_id=player_id, name=self._names.get(player_id, player_id), team_id=team_id
            )
            self._players[player_id] = ps
        return ps

    def _add_player(self, e: Event) -> None:
        ps = self._player(e.player_id or "", e.team_id)
        if e.type == "pass":
            ps.passes += 1
            if e.outcome == "success":
                ps.passes_completed += 1
            if "key_pass" in e.tags or "assist" in e.tags:
                ps.key_passes += 1
        elif e.type == "shot":
            ps.shots += 1
            ps.xg = round(ps.xg + float(e.meta.get("xg", 0.0)), 3)
            if e.outcome == "goal":
                ps.goals += 1
        elif e.type == "pressure":
            ps.pressures += 1

    def _update_momentum(self) -> None:
        home = sum(_threat(e) for e in self._window if e.team_id == self.home_id)
        away = sum(_threat(e) for e in self._window if e.team_id == self.away_id)
        raw = _clip(MOMENTUM_SCALE * (home - away))
        self._momentum = _clip((1 - MOMENTUM_SMOOTHING) * self._momentum + MOMENTUM_SMOOTHING * raw)

    # ------------------------------------------------------------------ queries
    @property
    def clock(self) -> float:
        return self._t

    @property
    def score(self) -> tuple[int, int]:
        return self._score[self.home_id], self._score[self.away_id]

    def team(self, team_id: str) -> TeamStats:
        total = sum(self._possession.seconds.values())
        return self._counters[team_id].to_stats(self._possession.seconds[team_id], total)

    def player(self, player_id: str) -> PlayerStats:
        team_id = next(
            t.team_id for t in (self.meta.home, self.meta.away) if player_id.startswith(t.team_id)
        )
        return self._player(player_id, team_id)

    def recent_events(self, n: int = 12) -> list[Event]:
        return list(self._recent)[-n:]

    def pressure_index(self) -> dict[str, float]:
        cutoff = self._t - PRESSURE_WINDOW_S
        counts = {self.home_id: 0, self.away_id: 0}
        for e in self._window:
            if e.type == "pressure" and e.t >= cutoff and e.team_id in counts:
                counts[e.team_id] += 1
        return {tid: _clip(c / 10.0, 0.0, 1.0) for tid, c in counts.items()}

    def snapshot(self) -> StatsSnapshot:
        return StatsSnapshot(
            t=self._t,
            clock=clock_str(self._t),
            score=self.score,
            home_id=self.home_id,
            away_id=self.away_id,
            team_names={
                self.home_id: self.meta.home.short_name,
                self.away_id: self.meta.away.short_name,
            },
            teams={tid: self.team(tid) for tid in (self.home_id, self.away_id)},
            players={pid: ps.model_copy() for pid, ps in self._players.items()},
            momentum=round(self._momentum, 4),
            pressure_index=self.pressure_index(),
            last5=aggregate(self.meta, list(self._window)),
        )
