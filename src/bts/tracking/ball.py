"""The ball's path: linear in time between the anchors the events pin.

An event's ``t`` is when its action ends (the simulator advances the clock before emitting a
pass, a carry or a shot), so the ball is at the event's ``end`` (or ``start`` without one)
exactly at ``t``. A pass or shot leaves ``start`` ``distance / speed`` earlier at the event's
own recorded speed, a carry at walking pace; when the next anchor is somewhere else (a kick-off
after a goal, a keeper's restart, a cleared ball) the ball rests, then moves so it arrives on
time at the bridge speed, or spans the whole gap when it is shorter.
"""

from __future__ import annotations

import math
from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass

from bts.sim.engine import PITCH_X_M, PITCH_Y_M
from bts.tracking.possession import XY, Placed

CARRY_SPEED_MS = 3.0
BRIDGE_SPEED_MS = 8.0
FALLBACK_SPEED_MS = 15.0
_SPEED_META = {"pass": "ball_speed", "shot": "shot_speed"}


def metres(a: XY, b: XY) -> float:
    return math.hypot((b[0] - a[0]) * PITCH_X_M / 100, (b[1] - a[1]) * PITCH_Y_M / 100)


def travel_seconds(placed: Placed) -> float:
    """How long the ball is in flight for this event; 0 when it does not move."""
    if placed.start is None or placed.end is None:
        return 0.0
    e = placed.event
    if e.type == "carry":
        speed = CARRY_SPEED_MS
    else:
        kmh = e.meta.get(_SPEED_META.get(e.type, ""))
        speed = float(kmh) / 3.6 if isinstance(kmh, int | float) and kmh > 0 else FALLBACK_SPEED_MS
    return metres(placed.start, placed.end) / speed


@dataclass(frozen=True)
class Anchor:
    t: float
    xy: XY


def _lerp(a: XY, b: XY, f: float) -> XY:
    return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)


class BallPath:
    def __init__(self, placed: Sequence[Placed]) -> None:
        self.anchors: list[Anchor] = []
        last_t = 0.0
        last_xy: XY = (50.0, 50.0)
        for p in placed:
            if p.start is None:
                continue
            travel = min(travel_seconds(p), max(0.0, p.event.t - last_t))
            leave = p.event.t - travel
            if p.start != last_xy:
                # Rest at the last anchor, then bridge to this start in time for it.
                bridge = min(metres(last_xy, p.start) / BRIDGE_SPEED_MS, max(0.0, leave - last_t))
                self._add(leave - bridge, last_xy)
            self._add(leave, p.start)
            if p.end is not None:
                self._add(p.event.t, p.end)
            last_t = p.event.t
            last_xy = p.end_or_start or p.start
        if not self.anchors:
            self.anchors.append(Anchor(0.0, (50.0, 50.0)))
        self._times = [a.t for a in self.anchors]

    def _add(self, t: float, xy: XY) -> None:
        if self.anchors and t < self.anchors[-1].t:
            t = self.anchors[-1].t
        self.anchors.append(Anchor(t, xy))

    def at(self, t: float) -> XY:
        """The ball at match second ``t``; clamped to the first and last anchors."""
        i = bisect_right(self._times, t)
        if i == 0:
            return self.anchors[0].xy
        if i >= len(self.anchors):
            return self.anchors[-1].xy
        a, b = self.anchors[i - 1], self.anchors[i]
        if b.t == a.t:
            return b.xy
        return _lerp(a.xy, b.xy, (t - a.t) / (b.t - a.t))
