"""Core data models for synthetic matches.

Coordinates are floats in ``[0, 100]`` on both axes (Wyscout convention); the team in
possession attacks from left (x=0) to right (x=100). Event type names follow kloppy's
standard event model. All clubs, players and venues are fictional.
"""

from typing import Literal

from pydantic import BaseModel, Field

EventType = Literal[
    "pass",
    "carry",
    "shot",
    "duel",
    "interception",
    "clearance",
    "recovery",
    "miscontrol",
    "ball_out",
    "foul",
    "goalkeeper",
    "pressure",
    "substitution",
    "card",
    "period_start",
    "period_end",
]

Outcome = Literal["success", "fail", "goal", "saved", "blocked", "off_target"]

TeamStyle = Literal["possession", "direct", "pressing", "counter"]

Position = Literal["GK", "DF", "MF", "FW"]

MetaValue = float | int | str | bool


class Point(BaseModel):
    x: float = Field(ge=0, le=100)
    y: float = Field(ge=0, le=100)


class Event(BaseModel):
    event_id: int
    match_id: str
    period: Literal[1, 2]
    t: float = Field(ge=0, description="Seconds since kick-off of the match")
    clock: str
    team_id: str
    player_id: str | None = None
    type: EventType
    subtype: str | None = None
    start: Point
    end: Point | None = None
    outcome: Outcome | None = None
    tags: list[str] = Field(default_factory=list)
    meta: dict[str, MetaValue] = Field(default_factory=dict)


class PlayerAttrs(BaseModel):
    passing: float = Field(ge=0, le=1)
    shooting: float = Field(ge=0, le=1)
    pace: float = Field(ge=0, le=1)
    pressing: float = Field(ge=0, le=1)
    aerial: float = Field(ge=0, le=1)


class Player(BaseModel):
    player_id: str
    name: str
    team_id: str
    position: Position
    shirt: int = Field(ge=1)
    attrs: PlayerAttrs


class Team(BaseModel):
    team_id: str
    name: str
    short_name: str
    colors: tuple[str, str]
    style: TeamStyle
    players: list[Player]


class MatchMeta(BaseModel):
    match_id: str
    seed: int
    home: Team
    away: Team
    venue: str
    competition: str = "Synthetic League"


class Match(BaseModel):
    meta: MatchMeta
    events: list[Event]
    score: tuple[int, int]


def clock_str(t: float) -> str:
    """Format seconds since kick-off as ``mm:ss`` (minutes may exceed 90)."""
    total = int(t)
    return f"{total // 60:02d}:{total % 60:02d}"
