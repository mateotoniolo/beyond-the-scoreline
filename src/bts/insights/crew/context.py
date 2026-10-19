"""Shared match state that the crew's agents read through Agent Framework tools.

Every tool returns compact JSON keyed by team and player names; ids never reach the model.
The module-level payload builders are shared with the question desk (``bts.insights.qa``).
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from agent_framework import FunctionTool, tool
from pydantic import Field, ValidationError

from bts.insights.prompts import events_summary, moment_payload
from bts.insights.schemas import Evidence, Insight
from bts.insights.verifier import check_facts
from bts.sim.models import Event
from bts.stats.moments import Moment
from bts.stats.state import PlayerStats, StatsSnapshot, TeamStats

ID_FIELDS = ("team_id", "player_id", "event_ids")
HIDDEN_TEAM_FIELDS = ("possession_seconds",)
MAX_RECENT = 12

TeamName = Annotated[str, Field(description="Team short name as shown in the moment, e.g. NTH")]
PlayerName = Annotated[str, Field(description="Player full name as it appears in the events")]
EventCount = Annotated[int, Field(description="How many of the latest events to return, 1 to 12")]
EvidenceJson = Annotated[
    str, Field(description='JSON list of {"stat": name, "value": "number"} objects to verify')
]


def dump(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False)


# ---------------------------------------------------------------- shared payload builders
def team_names(snap: StatsSnapshot) -> list[str]:
    return [snap.team_names[tid] for tid in (snap.home_id, snap.away_id)]


def team_id_for(snap: StatsSnapshot, team: str) -> str | None:
    wanted = team.strip().lower()
    return next((tid for tid, name in snap.team_names.items() if name.lower() == wanted), None)


def player_id_for(snap: StatsSnapshot, player: str) -> str | None:
    wanted = player.strip().lower()
    return next((pid for pid, p in snap.players.items() if p.name.lower() == wanted), None)


def public_team_stats(stats: TeamStats) -> dict[str, Any]:
    return {k: v for k, v in stats.model_dump().items() if k not in HIDDEN_TEAM_FIELDS}


def team_stats_payload(snap: StatsSnapshot, team: str) -> dict[str, Any]:
    tid = team_id_for(snap, team)
    if tid is None:
        return {"unknown_team": team, "teams": team_names(snap)}
    name = snap.team_names[tid]
    return {"team": name, "is_home": tid == snap.home_id, **public_team_stats(snap.teams[tid])}


def player_payload(snap: StatsSnapshot, stats: PlayerStats) -> dict[str, Any]:
    team = snap.team_names.get(stats.team_id, stats.team_id)
    data = stats.model_dump(exclude={"player_id", "team_id", "name"})
    return {"player": stats.name, "team": team, **data}


def player_stats_payload(snap: StatsSnapshot, player: str) -> dict[str, Any]:
    pid = player_id_for(snap, player)
    if pid is None:
        hint = "use a player name from get_moment or get_recent_events"
        return {"unknown_player": player, "hint": hint}
    return player_payload(snap, snap.players[pid])


def last_five_payload(snap: StatsSnapshot) -> dict[str, Any]:
    return {snap.team_names[tid]: public_team_stats(s) for tid, s in snap.last5.items()}


def momentum_payload(snap: StatsSnapshot) -> dict[str, Any]:
    home, away = team_names(snap)
    return {
        "momentum": {home: snap.momentum, away: round(-snap.momentum, 4)},
        "scale": "-1 to 1 over the last five minutes; positive favours the named team",
        "pressure_index": {snap.team_names[tid]: v for tid, v in snap.pressure_index.items()},
    }


class MatchContext:
    """The moment, the statistics snapshot and the recent events behind one insight."""

    def __init__(self, moment: Moment, snap: StatsSnapshot, recent: list[Event]) -> None:
        self.moment = moment
        self.snap = snap
        self.recent = recent

    @property
    def team_names(self) -> list[str]:
        return team_names(self.snap)

    # ------------------------------------------------------------------ readers
    def moment_json(self) -> str:
        data = moment_payload(self.moment, self.snap)
        for key in ID_FIELDS:
            data.pop(key, None)
        data["score"] = dict(zip(self.team_names, self.snap.score, strict=True))
        return dump(data)

    def team_stats(self, team: str) -> str:
        return dump(team_stats_payload(self.snap, team))

    def player_stats(self, player: str) -> str:
        return dump(player_stats_payload(self.snap, player))

    def last_five_minutes(self) -> str:
        return dump(last_five_payload(self.snap))

    def recent_events(self, n: int = MAX_RECENT) -> str:
        count = max(1, min(int(n), MAX_RECENT))
        return dump(events_summary(self.recent[-count:], self.snap))

    def momentum(self) -> str:
        return dump(momentum_payload(self.snap))

    def check_numbers(self, evidence_json: str) -> str:
        try:
            raw = json.loads(evidence_json)
            if isinstance(raw, dict) and "evidence" in raw:
                raw = raw["evidence"]
            evidence = [Evidence.model_validate(item) for item in raw]
        except (ValueError, TypeError, ValidationError):
            issue = 'evidence must be a JSON list of {"stat": name, "value": "number"} objects'
            return dump({"ok": False, "issues": [issue]})
        if not evidence:
            return dump({"ok": True, "issues": []})
        probe = Insight(
            insight_id="probe",
            moment_id=self.moment.moment_id,
            profile="analyst",
            lang="en",
            headline="probe",
            why_it_matters="probe",
            evidence=evidence,
            confidence=1.0,
            verified=False,
            source="llm",
        )
        issues = [i for i in check_facts(probe, self.snap, self.moment) if i.startswith("evidence")]
        return dump({"ok": not issues, "issues": issues})

    # ------------------------------------------------------------------ tools
    def tools(self) -> list[FunctionTool]:
        """Agent Framework tools bound to this context (no approval needed)."""
        ctx = self

        def get_moment() -> str:
            """The key moment to explain: type, clock, team, player, score and its facts."""
            return ctx.moment_json()

        def get_team_stats(team: TeamName) -> str:
            """Full-match statistics for one team: possession, passes, shots, xG, pressures."""
            return ctx.team_stats(team)

        def get_player_stats(player: PlayerName) -> str:
            """Match statistics for one player: passes, shots, goals, xG, pressures, key passes."""
            return ctx.player_stats(player)

        def get_last_five_minutes() -> str:
            """Both teams' statistics over the last five minutes only."""
            return ctx.last_five_minutes()

        def get_recent_events(n: EventCount = MAX_RECENT) -> str:
            """The latest events before the moment, oldest first, with team and player names."""
            return ctx.recent_events(n)

        def get_momentum() -> str:
            """Momentum (-1 to 1) and pressure index for each team."""
            return ctx.momentum()

        def check_numbers(evidence_json: EvidenceJson) -> str:
            """Check that cited numbers match the statistics; returns ok and the issues found."""
            return ctx.check_numbers(evidence_json)

        funcs = (
            get_moment,
            get_team_stats,
            get_player_stats,
            get_last_five_minutes,
            get_recent_events,
            get_momentum,
            check_numbers,
        )
        return [tool(f, approval_mode="never_require") for f in funcs]
