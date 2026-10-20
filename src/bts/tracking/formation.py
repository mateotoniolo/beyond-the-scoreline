"""Formation homes and the possession-shifted target a player drifts to between events.

Everything here is in a team's own attacking frame: own goal at ``x = 0``, the opponent's at
``x = 100``. ``to_team_frame`` maps screen coordinates into it (an involution, so it maps back).
"""

from __future__ import annotations

from bts.sim.league import starting_xi
from bts.sim.models import Position, Team
from bts.tracking.possession import XY

# 4-4-2 over the simulator's starting eleven (one keeper, four defenders, four midfielders,
# two forwards), each position in ``starting_xi`` order.
HOME_442: dict[Position, list[XY]] = {
    "GK": [(6.0, 50.0)],
    "DF": [(22.0, 16.0), (20.0, 38.0), (20.0, 62.0), (22.0, 84.0)],
    "MF": [(44.0, 14.0), (42.0, 38.0), (42.0, 62.0), (44.0, 86.0)],
    "FW": [(64.0, 40.0), (64.0, 60.0)],
}
X_SHIFT = 0.3
Y_SHIFT = 0.25
POSSESSION_PUSH = 7.0
KEEPER_MAX_X = 12.0
KEEPER_X_SHIFT = 0.06
KEEPER_Y_SHIFT = 0.15
X_MIN, X_MAX = 2.0, 98.0
Y_MIN, Y_MAX = 3.0, 97.0


def lineup_slots(team: Team) -> dict[str, XY]:
    """Formation home per starting player, keyed by player id in ``starting_xi`` order."""
    taken: dict[Position, int] = {}
    slots: dict[str, XY] = {}
    for player in starting_xi(team):
        i = taken.get(player.position, 0)
        taken[player.position] = i + 1
        homes = HOME_442[player.position]
        slots[player.player_id] = homes[min(i, len(homes) - 1)]
    return slots


def formation_target(home: XY, keeper: bool, ball: XY, in_possession: bool) -> XY:
    """Where a player without an event to reach drifts to; ``ball`` in the team's frame."""
    if keeper:
        x = min(KEEPER_MAX_X, home[0] + KEEPER_X_SHIFT * max(0.0, ball[0] - 50.0))
        y = home[1] + KEEPER_Y_SHIFT * (ball[1] - 50.0)
        return (x, y)
    push = POSSESSION_PUSH if in_possession else -POSSESSION_PUSH
    x = home[0] + X_SHIFT * (ball[0] - 50.0) + push
    y = home[1] + Y_SHIFT * (ball[1] - 50.0)
    return (min(X_MAX, max(X_MIN, x)), min(Y_MAX, max(Y_MIN, y)))


def to_team_frame(xy: XY, team_id: str, home_id: str) -> XY:
    """Screen coordinates into the team's attacking frame, and back (it mirrors both ways)."""
    if team_id == home_id:
        return xy
    return (100.0 - xy[0], 100.0 - xy[1])
