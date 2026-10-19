"""Shared match state that the crew's agents read through Agent Framework tools.

Every tool returns compact JSON keyed by team and player names; ids never reach the model.
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
from bts.stats.state import StatsSnapshot, TeamStats

ID_FIELDS = ("team_id", "player_id", "event_ids")
HIDDEN_TEAM_FIELDS = ("possession_seconds",)
MAX_RECENT = 12

TeamName = Annotated[str, Field(description="Team short name as shown in the moment, e.g. NTH")]
PlayerName = Annotated[str, Field(description="Player full name as it appears in the events")]
EventCount = Annotated[int, Field(description="How many of the latest events to return, 1 to 12")]
EvidenceJson = Annotated[
    str, Field(description='JSON list of {"stat": name, "value": "number"} objects to verify')
]


def _dump(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False)


def _team_stats(stats: TeamStats) -> dict[str, Any]:
    return {k: v for k, v in stats.model_dump().items() if k not in HIDDEN_TEAM_FIELDS}


class MatchContext:
    """The moment, the statistics snapshot and the recent events behind one insight."""

    def __init__(self, moment: Moment, snap: StatsSnapshot, recent: list[Event]) -> None:
        self.moment = moment
        self.snap = snap
        self.recent = recent
        self._team_by_name = {name.lower(): tid for tid, name in snap.team_names.items()}
        self._player_by_name = {p.name.lower(): pid for pid, p in snap.players.items()}

    @property
    def team_names(self) -> list[str]:
        return [self.snap.team_names[tid] for tid in (self.snap.home_id, self.snap.away_id)]

    # ------------------------------------------------------------------ readers
    def moment_json(self) -> str:
        data = moment_payload(self.moment, self.snap)
        for key in ID_FIELDS:
            data.pop(key, None)
        data["score"] = dict(zip(self.team_names, self.snap.score, strict=True))
        return _dump(data)

    def team_stats(self, team: str) -> str:
        tid = self._team_by_name.get(team.strip().lower())
        if tid is None:
            return _dump({"unknown_team": team, "teams": self.team_names})
        name = self.snap.team_names[tid]
        home = tid == self.snap.home_id
        return _dump({"team": name, "is_home": home, **_team_stats(self.snap.teams[tid])})

    def player_stats(self, player: str) -> str:
        pid = self._player_by_name.get(player.strip().lower())
        if pid is None:
            hint = "use a player name from get_moment or get_recent_events"
            return _dump({"unknown_player": player, "hint": hint})
        ps = self.snap.players[pid]
        team = self.snap.team_names.get(ps.team_id, ps.team_id)
        data = ps.model_dump(exclude={"player_id", "team_id", "name"})
        return _dump({"player": ps.name, "team": team, **data})

    def last_five_minutes(self) -> str:
        return _dump(
            {self.snap.team_names[tid]: _team_stats(s) for tid, s in self.snap.last5.items()}
        )

    def recent_events(self, n: int = MAX_RECENT) -> str:
        count = max(1, min(int(n), MAX_RECENT))
        return _dump(events_summary(self.recent[-count:], self.snap))

    def momentum(self) -> str:
        home, away = self.team_names
        return _dump(
            {
                "momentum": {home: self.snap.momentum, away: round(-self.snap.momentum, 4)},
                "scale": "-1 to 1 over the last five minutes; positive favours the named team",
                "pressure_index": {
                    self.snap.team_names[tid]: v for tid, v in self.snap.pressure_index.items()
                },
            }
        )

    def check_numbers(self, evidence_json: str) -> str:
        try:
            raw = json.loads(evidence_json)
            if isinstance(raw, dict) and "evidence" in raw:
                raw = raw["evidence"]
            evidence = [Evidence.model_validate(item) for item in raw]
        except (ValueError, TypeError, ValidationError):
            issue = 'evidence must be a JSON list of {"stat": name, "value": "number"} objects'
            return _dump({"ok": False, "issues": [issue]})
        if not evidence:
            return _dump({"ok": True, "issues": []})
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
        return _dump({"ok": not issues, "issues": issues})

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
