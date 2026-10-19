"""Request and response bodies of the HTTP API."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from bts.sim.league import STYLES
from bts.sim.models import MatchMeta, TeamStyle

TEAM_IDS = [f"t{i + 1}" for i in range(len(STYLES))]
MAX_SPEED = 6000.0


class CreateMatch(BaseModel):
    seed: int = Field(ge=0, le=2_000_000_000)
    home: str = "t1"
    away: str = "t2"
    speed: float = Field(10.0, gt=0, le=MAX_SPEED)

    @model_validator(mode="after")
    def _teams_exist_and_differ(self) -> "CreateMatch":
        if self.home not in TEAM_IDS or self.away not in TEAM_IDS:
            raise ValueError(f"team ids must be one of {TEAM_IDS}")
        if self.home == self.away:
            raise ValueError("home and away must differ")
        return self


class SpeedUpdate(BaseModel):
    speed: float = Field(gt=0, le=MAX_SPEED)


class TeamSummary(BaseModel):
    team_id: str
    name: str
    short_name: str
    colors: tuple[str, str]
    style: TeamStyle
    venue: str


class MatchInfo(BaseModel):
    match_id: str
    meta: MatchMeta
    score: tuple[int, int]
    status: Literal["running", "finished"]
    clock: str
    speed: float
    events_so_far: int
