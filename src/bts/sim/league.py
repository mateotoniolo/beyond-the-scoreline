"""Seeded fictional league: four clubs with distinct styles and 18 players each."""

import random

from bts.sim.models import Player, PlayerAttrs, Position, Team, TeamStyle
from bts.sim.names import CLUBS, make_name

STYLES: list[TeamStyle] = ["possession", "direct", "pressing", "counter"]

_POSITIONS: list[Position] = (
    ["GK"] + ["DF"] * 6 + ["MF"] * 6 + ["FW"] * 4 + ["GK"]
)  # 18 shirts, 2 GK / 6 DF / 6 MF / 4 FW

_STYLE_BONUS: dict[TeamStyle, dict[str, float]] = {
    "possession": {"passing": 0.15},
    "direct": {"aerial": 0.10, "shooting": 0.05},
    "pressing": {"pressing": 0.15, "pace": 0.05},
    "counter": {"pace": 0.15, "shooting": 0.05},
}

_POSITION_BONUS: dict[Position, dict[str, float]] = {
    "GK": {"shooting": -0.3, "passing": -0.1, "pressing": -0.2},
    "DF": {"aerial": 0.10, "shooting": -0.15},
    "MF": {"passing": 0.08},
    "FW": {"shooting": 0.15, "pace": 0.05},
}

_XI_SHAPE: dict[Position, int] = {"GK": 1, "DF": 4, "MF": 4, "FW": 2}


def _clip(v: float) -> float:
    return max(0.0, min(1.0, v))


def _attrs(rng: random.Random, style: TeamStyle, position: Position) -> PlayerAttrs:
    values: dict[str, float] = {}
    for name in ("passing", "shooting", "pace", "pressing", "aerial"):
        base = rng.uniform(0.35, 0.75)
        bonus = _STYLE_BONUS[style].get(name, 0.0) + _POSITION_BONUS[position].get(name, 0.0)
        values[name] = round(_clip(base + bonus), 3)
    return PlayerAttrs(**values)


def build_league(seed: int) -> list[Team]:
    """Build four teams deterministically from ``seed``."""
    rng = random.Random(seed)
    teams: list[Team] = []
    for index, ((name, short, colors, _venue), style) in enumerate(zip(CLUBS, STYLES, strict=True)):
        team_id = f"t{index + 1}"
        used: set[str] = set()
        players: list[Player] = []
        for shirt, position in enumerate(_POSITIONS, start=1):
            player_name = make_name(rng)
            while player_name in used:
                player_name = make_name(rng)
            used.add(player_name)
            players.append(
                Player(
                    player_id=f"{team_id}p{shirt}",
                    name=player_name,
                    team_id=team_id,
                    position=position,
                    shirt=shirt,
                    attrs=_attrs(rng, style, position),
                )
            )
        teams.append(
            Team(
                team_id=team_id,
                name=name,
                short_name=short,
                colors=colors,
                style=style,
                players=players,
            )
        )
    return teams


def venue_for(team: Team) -> str:
    """Home venue of a club from the fixed invented list."""
    index = int(team.team_id[1:]) - 1
    return CLUBS[index][3]


def starting_xi(team: Team) -> list[Player]:
    """Pick 1 GK, 4 DF, 4 MF, 2 FW by highest attribute sum."""

    def strength(p: Player) -> float:
        a = p.attrs
        return a.passing + a.shooting + a.pace + a.pressing + a.aerial

    xi: list[Player] = []
    for position, count in _XI_SHAPE.items():
        pool = sorted(
            (p for p in team.players if p.position == position), key=strength, reverse=True
        )
        xi.extend(pool[:count])
    return xi
