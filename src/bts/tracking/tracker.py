"""Per-frame positions of the players and the ball, integrated from the event list.

No model and no randomness: the same events always give the same frames. Each frame every
player on the pitch moves toward a target (the next event they take part in, the ball they
are carrying, the spot they just acted at, or their formation home shifted with possession)
at no more than ``MAX_SPEED_MS``, which is what keeps the dots from teleporting. Frames are
integrated in order and cached compactly, so a window late in the match costs one pass over
the earlier frames once.
"""

from __future__ import annotations

import math
import threading
from array import array
from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import BaseModel

from bts.sim.engine import PITCH_X_M, PITCH_Y_M, MatchSimulator
from bts.sim.models import Event, MatchMeta
from bts.tracking.ball import BallPath, travel_seconds
from bts.tracking.formation import formation_target, lineup_slots, to_team_frame
from bts.tracking.possession import ON_BALL, XY, Placed, place_events

FPS = 4
MAX_FRAMES = 600
MAX_SPEED_MS = 9.0
LOOKAHEAD_S = 8.0
HOLD_S = 2.0
ENTRY_XY: XY = (50.0, 0.0)
_SAME_SPOT = 0.5  # units: the previous ball position counts as this event's start
# The ball crosses the line on its own; the player it names stays where the pass left.
_NO_PLAYER_ANCHOR = frozenset({"ball_out"})
_OUTPUT_DECIMALS = 2


class Frame(BaseModel):
    t: float
    ball: tuple[float, float]
    players: dict[str, tuple[float, float]]


@dataclass(frozen=True)
class _Anchor:
    t_from: float  # be at xy by then
    t_to: float  # the event's own time
    xy: XY
    carry_from: float | None  # a carry: follow the ball from here until t_to


class MatchTracker:
    def __init__(self, meta: MatchMeta, events: Sequence[Event], fps: int = FPS) -> None:
        self.meta = meta
        self.events = list(events)
        self.fps = fps
        self.end_t = self.events[-1].t if self.events else 0.0
        self._home_id = meta.home.team_id
        self._placed = place_events(meta, self.events)
        self._path = BallPath(self._placed)
        self._team_of = {p.player_id: t.team_id for t in (meta.home, meta.away) for p in t.players}
        self._keepers = {
            p.player_id for t in (meta.home, meta.away) for p in t.players if p.position == "GK"
        }
        self._slots: dict[str, XY] = {}
        self._roster: list[str] = []
        for team in (meta.home, meta.away):
            slots = lineup_slots(team)
            self._slots.update(slots)
            self._roster.extend(slots)
        self._anchors = self._build_anchors()
        # Integration state (frame k is at t = k / fps).
        self._pos: dict[str, list[float]] = {
            pid: list(to_team_frame(self._slots[pid], self._team_of[pid], self._home_id))
            for pid in self._roster
        }
        self._cursor: dict[str, int] = dict.fromkeys(self._anchors, 0)
        self._event_i = 0
        self._holder = self._home_id
        self._k = 0
        self._frames: list[array] = []
        self._rosters: list[tuple[str, ...]] = []
        self._roster_tuple: tuple[str, ...] = tuple(self._roster)
        self._lock = threading.Lock()

    @classmethod
    def for_match(cls, meta: MatchMeta) -> MatchTracker:
        """Replay the seed with a fresh simulator; identical events, nothing shared."""
        match = MatchSimulator(meta.seed, meta.home, meta.away).run()
        return cls(meta, match.events)

    # ------------------------------------------------------------------ queries
    def ball_at(self, t: float) -> XY:
        return self._path.at(t)

    def frames(self, from_t: float, to_t: float, limit: int = MAX_FRAMES) -> list[Frame]:
        """Frames on the ``1/fps`` grid with ``from_t <= t <= to_t``, at most ``limit``."""
        k0 = math.ceil(from_t * self.fps - 1e-9)
        k1 = math.floor(to_t * self.fps + 1e-9)
        k1 = min(k1, math.floor(self.end_t * self.fps + 1e-9), k0 + limit - 1)
        if k1 < k0 or k0 < 0:
            return []
        with self._lock:
            while self._k <= k1:
                self._integrate(self._k)
                self._k += 1
            out = []
            for k in range(k0, k1 + 1):
                data, roster = self._frames[k], self._rosters[k]
                players = {
                    pid: (round(data[3 + 2 * i], _OUTPUT_DECIMALS), round(data[4 + 2 * i], 2))
                    for i, pid in enumerate(roster)
                }
                ball = (round(data[1], _OUTPUT_DECIMALS), round(data[2], _OUTPUT_DECIMALS))
                out.append(Frame(t=k / self.fps, ball=ball, players=players))
        return out

    # ------------------------------------------------------------------ anchors
    def _build_anchors(self) -> dict[str, list[_Anchor]]:
        anchors: dict[str, list[_Anchor]] = {}
        prev: Placed | None = None
        last_t = 0.0
        for p in self._placed:
            if p.start is None:
                continue
            e = p.event
            travel = min(travel_seconds(p), max(0.0, e.t - last_t))
            leave = e.t - travel
            if e.player_id and e.type not in _NO_PLAYER_ANCHOR:
                t_from = leave if e.type in ON_BALL else e.t
                if prev is not None and prev.end_or_start is not None:
                    if math.dist(prev.end_or_start, p.start) <= _SAME_SPOT:
                        t_from = min(t_from, prev.event.t)
                carry_from = leave if e.type == "carry" and p.end is not None else None
                anchor = _Anchor(t_from, e.t, p.start, carry_from)
                anchors.setdefault(e.player_id, []).append(anchor)
            prev = p
            last_t = e.t
        return anchors

    def _target(self, pid: str, t: float, ball: XY) -> XY:
        anchors = self._anchors.get(pid)
        if anchors:
            cur = self._cursor[pid]
            while cur < len(anchors) and anchors[cur].t_to + HOLD_S < t:
                cur += 1
            self._cursor[pid] = cur
            if cur < len(anchors):
                a = anchors[cur]
                if a.t_to < t:  # holding the spot just acted at, unless the next is close
                    nxt = anchors[cur + 1] if cur + 1 < len(anchors) else None
                    if nxt is not None and nxt.t_from - t <= LOOKAHEAD_S:
                        a = nxt
                    else:
                        return a.xy
                if a.t_from - t <= LOOKAHEAD_S:
                    if a.carry_from is not None and a.carry_from <= t <= a.t_to:
                        return ball
                    return a.xy
        team = self._team_of[pid]
        ball_team = to_team_frame(ball, team, self._home_id)
        target = formation_target(
            self._slots[pid], pid in self._keepers, ball_team, self._holder == team
        )
        return to_team_frame(target, team, self._home_id)

    # ------------------------------------------------------------------ integration
    def _apply_events_until(self, t: float) -> None:
        placed = self._placed
        while self._event_i < len(placed) and placed[self._event_i].event.t <= t:
            p = placed[self._event_i]
            e = p.event
            if e.type == "substitution":
                out, inc = str(e.meta.get("player_out")), str(e.meta.get("player_in"))
                if out in self._pos and inc in self._team_of:
                    self._roster[self._roster.index(out)] = inc
                    self._slots[inc] = self._slots[out]
                    self._pos[inc] = list(ENTRY_XY)
                    del self._pos[out]
                    self._roster_tuple = tuple(self._roster)
            elif e.type == "card" and e.subtype == "red" and e.player_id in self._pos:
                self._roster.remove(e.player_id)
                del self._pos[e.player_id]
                self._roster_tuple = tuple(self._roster)
            self._holder = p.holder_after
            self._event_i += 1

    def _integrate(self, k: int) -> None:
        t = k / self.fps
        self._apply_events_until(t)
        ball = self._path.at(t)
        step = MAX_SPEED_MS / self.fps
        data = array("f", [t, ball[0], ball[1]])
        for pid in self._roster:
            pos = self._pos[pid]
            tx, ty = self._target(pid, t, ball)
            dx_m = (tx - pos[0]) * PITCH_X_M / 100
            dy_m = (ty - pos[1]) * PITCH_Y_M / 100
            dist = math.hypot(dx_m, dy_m)
            if dist <= step:
                pos[0], pos[1] = tx, ty
            else:
                f = step / dist
                pos[0] += (tx - pos[0]) * f
                pos[1] += (ty - pos[1]) * f
            data.append(pos[0])
            data.append(pos[1])
        self._frames.append(data)
        self._rosters.append(self._roster_tuple)
