"""Which side has the ball, and where every event sits on screen.

The simulator records each event in the attacking frame of the side in possession, with the
defending side's actions (pressure, interception, save, …) expressed in that same frame. This
module follows possession through the event list so the tracker can place every event in one
**screen frame**: both axes 0 to 100, the home side attacking from left to right all match long,
the away frame mirrored as ``(100 - x, 100 - y)``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from bts.sim.models import Event, MatchMeta, Point

XY = tuple[float, float]

# Events whose coordinates are in their own team's frame; possession rules below.
ON_BALL = frozenset({"pass", "carry", "shot", "miscontrol", "ball_out"})
# Events with ball coordinates recorded in the frame of the side that had the ball before them.
DEFENSIVE = frozenset(
    {"pressure", "foul", "card", "interception", "recovery", "duel", "clearance", "goalkeeper"}
)
# The ball is at these events; substitutions and the final whistle carry no ball location.
_NO_BALL = frozenset({"substitution", "period_end"})
_TAKES_THE_BALL = frozenset({"interception", "recovery", "clearance", "goalkeeper"})
CENTRE: XY = (50.0, 50.0)


def other(team_id: str, home_id: str, away_id: str) -> str:
    return away_id if team_id == home_id else home_id


def possession_after(event: Event, holder: str, home_id: str, away_id: str) -> str:
    """The side with the ball once ``event`` has happened, given who held it before."""
    t = event.type
    if t in ("period_start", "pass", "carry"):
        return event.team_id
    if t in ("ball_out", "miscontrol"):
        return other(event.team_id, home_id, away_id)
    if t == "shot":
        if event.outcome in ("goal", "off_target"):
            return other(event.team_id, home_id, away_id)
        return event.team_id  # a save, a block: the next event resolves it
    if t in _TAKES_THE_BALL:
        return event.team_id
    if t == "duel":
        return event.team_id if event.outcome == "success" else holder
    return holder  # pressure, foul, card, substitution, period_end


def frame_team(event: Event, holder: str) -> str:
    """The team whose attacking frame the event's coordinates are expressed in."""
    return event.team_id if event.type in ON_BALL else holder


def to_screen(p: Point, team_id: str, home_id: str) -> XY:
    if team_id == home_id:
        return (float(p.x), float(p.y))
    return (100.0 - p.x, 100.0 - p.y)


@dataclass(frozen=True)
class Placed:
    """An event with its coordinates on screen and the possession it leaves behind."""

    event: Event
    team: str  # the frame the event was recorded in
    holder_after: str
    start: XY | None
    end: XY | None

    @property
    def end_or_start(self) -> XY | None:
        return self.end if self.end is not None else self.start


def place_events(meta: MatchMeta, events: Sequence[Event]) -> list[Placed]:
    """Place every event on screen, in order; the home side holds the ball before kick-off."""
    home_id, away_id = meta.home.team_id, meta.away.team_id
    holder = home_id
    placed: list[Placed] = []
    for e in events:
        team = frame_team(e, holder)
        holder = possession_after(e, holder, home_id, away_id)
        if e.type == "period_start":
            start: XY | None = CENTRE
        elif e.type in _NO_BALL:
            start = None
        else:
            start = to_screen(e.start, team, home_id)
        end: XY | None = None
        if e.end is not None and start is not None:
            blocked = e.type == "shot" and e.outcome == "blocked"
            if not blocked:
                end = to_screen(e.end, team, home_id)
        placed.append(Placed(event=e, team=team, holder_after=holder, start=start, end=end))
    return placed
