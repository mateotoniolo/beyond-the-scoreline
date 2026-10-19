"""Shared insight, recap and overlay-cue schemas."""

from typing import Literal

from pydantic import BaseModel, Field

Profile = Literal["analyst", "fan"]
Lang = Literal["en", "es"]
Layer = Literal["lower_third", "side_panel", "ticker"]
Source = Literal["llm", "template"]

HEADLINE_MAX = 80
WHY_MAX: dict[str, int] = {"analyst": 280, "fan": 160}
FAN_MAX_NUMBERS = 1


class Evidence(BaseModel):
    stat: str
    value: str


class AgentStep(BaseModel):
    """One crew member's turn while producing an insight."""

    agent: str
    ms: int
    tool_calls: int = 0
    ok: bool = True


class Insight(BaseModel):
    insight_id: str
    moment_id: str
    profile: Profile
    lang: Lang
    headline: str
    why_it_matters: str
    evidence: list[Evidence] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    verified: bool
    source: Source
    trace: list[AgentStep] = Field(default_factory=list)


class Recap(BaseModel):
    profile: Profile
    lang: Lang
    title: str
    paragraphs: list[str]
    key_moments: list[str]
    source: Source


class Cue(BaseModel):
    cue_id: str
    t_start: float
    duration_s: float
    layer: Layer
    text: str
    lang: Lang
    profile: Profile
    moment_id: str
