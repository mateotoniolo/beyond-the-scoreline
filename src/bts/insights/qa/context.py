"""The live match as the question desk sees it: a protocol over the session and its tools.

A context is created per question over the session's current state, so an answer during a
running match reflects the clock on screen. Tools return compact JSON keyed by team and
player names; ids never reach the model.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Any, Protocol

from agent_framework import FunctionTool, tool
from pydantic import Field

from bts.insights.crew.context import (
    HIDDEN_TEAM_FIELDS,
    dump,
    last_five_payload,
    momentum_payload,
    player_id_for,
    player_payload,
    team_id_for,
    team_names,
    team_stats_payload,
)
from bts.insights.prompts import events_summary, moment_payload
from bts.insights.schemas import Evidence, Insight, Lang, Profile
from bts.sim.models import Event, MatchMeta, Player
from bts.stats.moments import Moment
from bts.stats.state import PlayerStats, StatsSnapshot

MAX_EVENTS = 20
MAX_TOP = 10
PLAYER_STATS = ("passes", "passes_completed", "shots", "goals", "xg", "pressures", "key_passes")
VARIANTS: tuple[tuple[Profile, Lang], ...] = (
    ("analyst", "en"),
    ("fan", "en"),
    ("analyst", "es"),
    ("fan", "es"),
)
MOMENT_LIST_FIELDS = ("moment_id", "type", "clock", "team", "player", "severity")

TeamName = Annotated[str, Field(description="Team short name, e.g. NTH, as in the match card")]
PlayerName = Annotated[str, Field(description="Player full name as in the lineup or the events")]
StatName = Annotated[str, Field(description=f"One player statistic: {', '.join(PLAYER_STATS)}")]
TopCount = Annotated[int, Field(description="How many leaders to return, 1 to 10")]
MomentId = Annotated[str, Field(description="A moment_id from the match card or get_moments")]
EventCount = Annotated[int, Field(description="How many of the latest events to return, 1 to 20")]
EventType = Annotated[
    str,
    Field(
        description="Event type to keep (pass, carry, shot, duel, pressure, foul, card, "
        "goalkeeper, substitution...), empty for any"
    ),
]
OptionalTeam = Annotated[str, Field(description="Team short name to keep, empty for any")]
OptionalPlayer = Annotated[str, Field(description="Player full name to keep, empty for any")]
FromMinute = Annotated[int, Field(description="First minute of the window, 0 for kick-off")]
ToMinute = Annotated[int, Field(description="Last minute of the window, 999 for now")]


class LiveMatch(Protocol):
    """What the question desk needs from a match session."""

    match_id: str
    meta: MatchMeta
    status: str
    events: Sequence[Event]
    moments: Sequence[Moment]

    def snapshot(self) -> StatsSnapshot: ...

    def cached_insight(self, moment_id: str, profile: Profile, lang: Lang) -> Insight | None: ...


def _moment_row(moment: Moment, snap: StatsSnapshot, *, facts: bool) -> dict[str, Any]:
    data = moment_payload(moment, snap)
    row = {k: data.get(k) for k in MOMENT_LIST_FIELDS}
    if facts:
        row["facts"] = data.get("facts", {})
    return row


class QAContext:
    """Readers over one live match for one audience (profile and language).

    The statistics are pinned when the context is created (one question, one board) so the
    tools, the match card and the citation check all see the same numbers while the match
    moves on. Events and moments are read live (they only append).
    """

    def __init__(self, match: LiveMatch, profile: Profile, lang: Lang) -> None:
        self.match = match
        self.profile = profile
        self.lang = lang
        self.snap: StatsSnapshot = match.snapshot()
        # Evidence of the crew insights served through get_insight: numbers from a moment's
        # board, which the citation check accepts even after the match moved on.
        self.served: list[Evidence] = []
        self._roster: dict[str, Player] = {
            p.name.lower(): p for t in (match.meta.home, match.meta.away) for p in t.players
        }

    # ------------------------------------------------------------------ readers
    def match_card(self) -> dict[str, Any]:
        snap = self.snap
        meta = self.match.meta
        return {
            "clock": snap.clock,
            "score": dict(zip(team_names(snap), snap.score, strict=True)),
            "status": self.match.status,
            "teams": {meta.home.short_name: meta.home.name, meta.away.short_name: meta.away.name},
            "moments": [_moment_row(m, snap, facts=False) for m in self.match.moments],
        }

    def score_and_clock(self) -> str:
        card = self.match_card()
        card.pop("moments")
        return dump(card)

    def team_stats(self, team: str) -> str:
        return dump(team_stats_payload(self.snap, team))

    def player_stats(self, player: str) -> str:
        snap = self.snap
        found = self._roster.get(player.strip().lower())
        if found is None:
            hint = "use a player name from get_lineup, get_top_players or the events"
            return dump({"unknown_player": player, "hint": hint})
        stats = snap.players.get(found.player_id) or PlayerStats(
            player_id=found.player_id, name=found.name, team_id=found.team_id
        )
        data = player_payload(snap, stats)
        return dump({**data, "position": found.position, "shirt": found.shirt})

    def top_players(self, stat: str, n: int = 5) -> str:
        key = stat.strip().lower()
        if key not in PLAYER_STATS:
            return dump({"unknown_stat": stat, "stats": list(PLAYER_STATS)})
        snap = self.snap
        count = max(1, min(int(n), MAX_TOP))
        ranked = sorted(snap.players.values(), key=lambda p: getattr(p, key), reverse=True)
        rows = [
            {
                "player": p.name,
                "team": snap.team_names.get(p.team_id, p.team_id),
                key: getattr(p, key),
            }
            for p in ranked[:count]
        ]
        return dump({"stat": key, "players": rows})

    def lineup(self, team: str) -> str:
        snap = self.snap
        tid = team_id_for(snap, team)
        if tid is None:
            return dump({"unknown_team": team, "teams": team_names(snap)})
        meta = self.match.meta
        squad = meta.home if tid == meta.home.team_id else meta.away
        players = []
        for p in squad.players:
            stats = snap.players.get(p.player_id) or PlayerStats(
                player_id=p.player_id, name=p.name, team_id=p.team_id
            )
            numbers = stats.model_dump(include=set(PLAYER_STATS))
            players.append({"player": p.name, "position": p.position, "shirt": p.shirt, **numbers})
        return dump({"team": snap.team_names[tid], "players": players})

    def last_five_minutes(self) -> str:
        return dump(last_five_payload(self.snap))

    def momentum(self) -> str:
        return dump(momentum_payload(self.snap))

    def moments(self) -> str:
        snap = self.snap
        return dump([_moment_row(m, snap, facts=True) for m in self.match.moments])

    def insight(self, moment_id: str) -> str:
        variants = [(self.profile, self.lang), *VARIANTS]
        for profile, lang in variants:
            found = self.match.cached_insight(moment_id, profile, lang)
            if found is not None:
                self.served.extend(found.evidence)
                return dump(found.model_dump(exclude={"insight_id", "trace"}))
        hint = "the crew has not explained this moment yet; answer from the statistics"
        return dump({"no_insight": moment_id, "hint": hint})

    def recent_events(self, n: int = MAX_EVENTS) -> str:
        count = max(1, min(int(n), MAX_EVENTS))
        events = list(self.match.events)[-count:]
        return dump(events_summary(events, self.snap))

    def search_events(
        self,
        type: str = "",
        team: str = "",
        player: str = "",
        from_minute: int = 0,
        to_minute: int = 999,
    ) -> str:
        snap = self.snap
        tid = pid = None
        if team.strip():
            tid = team_id_for(snap, team)
            if tid is None:
                return dump({"unknown_team": team, "teams": team_names(snap)})
        if player.strip():
            found = self._roster.get(player.strip().lower())
            pid = found.player_id if found else player_id_for(snap, player)
            if pid is None:
                return dump({"unknown_player": player, "hint": "use a name from get_lineup"})
        kind = type.strip().lower()
        lo, hi = float(from_minute) * 60, (float(to_minute) + 1) * 60
        matches = [
            e
            for e in self.match.events
            if (not kind or e.type == kind)
            and (tid is None or e.team_id == tid)
            and (pid is None or e.player_id == pid)
            and lo <= e.t < hi
        ]
        return dump({"total": len(matches), "events": events_summary(matches[-MAX_EVENTS:], snap)})

    # ------------------------------------------------------------------ tools
    def tools(self) -> list[FunctionTool]:
        """Agent Framework tools bound to this context (no approval needed)."""
        ctx = self

        def get_score_and_clock() -> str:
            """The clock, the score by team, the match status and both team names."""
            return ctx.score_and_clock()

        def get_team_stats(team: TeamName) -> str:
            """Full-match statistics for one team: possession, passes, shots, xG, pressures."""
            return ctx.team_stats(team)

        def get_player_stats(player: PlayerName) -> str:
            """One player's passes, shots, goals, xG, pressures, key passes, position and shirt."""
            return ctx.player_stats(player)

        def get_top_players(stat: StatName, n: TopCount = 5) -> str:
            """The leaders in one player statistic across both teams, best first."""
            return ctx.top_players(stat, n)

        def get_lineup(team: TeamName) -> str:
            """The team's players with position (GK, DF, MF, FW), shirt and match statistics."""
            return ctx.lineup(team)

        def get_last_five_minutes() -> str:
            """Both teams' statistics over the last five minutes only."""
            return ctx.last_five_minutes()

        def get_momentum() -> str:
            """Momentum (-1 to 1) and pressure index for each team."""
            return ctx.momentum()

        def get_moments() -> str:
            """The key moments so far (goals, chances, momentum shifts, cards) with their facts."""
            return ctx.moments()

        def get_insight(moment_id: MomentId) -> str:
            """The crew's verified explanation of one key moment, when it exists."""
            return ctx.insight(moment_id)

        def get_recent_events(n: EventCount = 12) -> str:
            """The latest events, oldest first, with team and player names."""
            return ctx.recent_events(n)

        def search_events(
            type: EventType = "",
            team: OptionalTeam = "",
            player: OptionalPlayer = "",
            from_minute: FromMinute = 0,
            to_minute: ToMinute = 999,
        ) -> str:
            """Events matching a type, team, player and minute window: total and the latest 20."""
            return ctx.search_events(type, team, player, from_minute, to_minute)

        funcs = (
            get_score_and_clock,
            get_team_stats,
            get_player_stats,
            get_top_players,
            get_lineup,
            get_last_five_minutes,
            get_momentum,
            get_moments,
            get_insight,
            get_recent_events,
            search_events,
        )
        return [tool(f, approval_mode="never_require") for f in funcs]


__all__ = ["HIDDEN_TEAM_FIELDS", "LiveMatch", "MAX_EVENTS", "MAX_TOP", "PLAYER_STATS", "QAContext"]
