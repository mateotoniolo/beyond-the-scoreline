"""Deterministic check of the question desk's citations against the live statistics.

Same number extraction and tolerances as ``verifier.check_facts``, but there is no moment to
anchor on: a value that names a team resolves against that team only, a value that names a
player against that player only, and an unqualified value against everything on the board.
A known statistic the named entity does not have (a team's key passes, a player's possession)
is an issue, never a fall-through; only an unknown stat name reaches the strict pool.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from bts.insights.qa.context import PLAYER_STATS
from bts.insights.schemas import Evidence
from bts.insights.verifier import CLOCK_RE, IDENT_RE, NUMBER_RE, PAREN_RE, _close, _normalize
from bts.sim.models import MatchMeta
from bts.stats.moments import Moment
from bts.stats.state import StatsSnapshot, TeamStats

Roster = dict[str, str]  # lower-case player name -> player id
Qualifier = tuple[str, str] | None  # ("team", id) | ("player", id) | None

QA_ALIASES = {
    "chances_created": "key_passes",
    "chances": "key_passes",
    "key_pass": "key_passes",
    "time": "minute",
}
TEAM_STATS = frozenset(TeamStats.model_fields) - {"possession_seconds"}
KNOWN_STATS = TEAM_STATS | frozenset(PLAYER_STATS) | {"shot_xg", "score", "momentum"}
WORD_RE = re.compile(r"[a-z]+")


def _key(stat: str) -> str:
    key = _normalize(stat)
    return QA_ALIASES.get(key, key)


def _numbers(value: str) -> list[float]:
    cleaned = CLOCK_RE.sub(lambda m: str(int(m[1]) + int(m[2]) / 60), value)
    cleaned = IDENT_RE.sub(" ", PAREN_RE.sub("", cleaned)).replace("%", "")
    return [float(n) for n in NUMBER_RE.findall(cleaned)]


def roster_of(meta: MatchMeta | None) -> Roster:
    if meta is None:
        return {}
    return {p.name.lower(): p.player_id for t in (meta.home, meta.away) for p in t.players}


def _qualifier(value: str, snap: StatsSnapshot, roster: Roster) -> Qualifier:
    """``("player", id)`` or ``("team", id)`` when the value names one, else None."""
    text = value.lower()
    names = {**roster, **{p.name.lower(): pid for pid, p in snap.players.items()}}
    for name, pid in names.items():
        if name in text:
            return "player", pid
    words = set(WORD_RE.findall(text))
    for tid, name in snap.team_names.items():
        if name.lower() in words:
            return "team", tid
    return None


def _stat_values(data: dict, key: str) -> list[float]:
    value = data.get(key)
    return [float(value)] if isinstance(value, int | float) else []


def _facts(moments: Sequence[Moment], key: str) -> list[float]:
    facts_key = "xg" if key == "shot_xg" else key
    return [
        float(m.facts[facts_key])
        for m in moments
        if isinstance(m.facts.get(facts_key), int | float)
    ]


def _team_scope(snap: StatsSnapshot, moments: Sequence[Moment], tid: str, key: str) -> list[float]:
    values = _stat_values(snap.teams[tid].model_dump(), key)
    if tid in snap.last5:
        values += _stat_values(snap.last5[tid].model_dump(), key)
    return values + _facts([m for m in moments if m.team_id == tid], key)


def _player_scope(
    snap: StatsSnapshot, moments: Sequence[Moment], pid: str, key: str
) -> list[float]:
    if key not in PLAYER_STATS:
        values: list[float] = []
    elif pid in snap.players:
        values = _stat_values(snap.players[pid].model_dump(), key)
    else:  # on the roster, no event yet: every statistic is zero
        values = [0.0]
    return values + _facts([m for m in moments if m.player_id == pid], key)


def _served_candidates(
    served: Sequence[Evidence],
    key: str,
    qualifier: Qualifier,
    snap: StatsSnapshot,
    roster: Roster,
) -> list[float]:
    """Numbers of insight evidence the agent read, for this stat and the same entity."""
    values: list[float] = []
    for ev in served:
        if _key(ev.stat) != key:
            continue
        own = _qualifier(ev.value, snap, roster)
        if qualifier is None or own is None or own == qualifier:
            values += _numbers(ev.value)
    return values


def _candidates(
    key: str,
    qualifier: Qualifier,
    snap: StatsSnapshot,
    moments: Sequence[Moment],
    served: Sequence[Evidence],
    roster: Roster,
) -> list[float] | None:
    """The numbers a citation may refer to; None when the stat name is unknown."""
    if key not in KNOWN_STATS:
        return None
    extra = _served_candidates(served, key, qualifier, snap, roster)
    if key == "score":
        return [float(snap.score[0]), float(snap.score[1])] + extra
    if key == "momentum":
        values = [snap.momentum, -snap.momentum]
        for m in moments:
            for name in ("momentum_before", "momentum_now"):
                if isinstance(m.facts.get(name), int | float):
                    values += [float(m.facts[name]), -float(m.facts[name])]
        return values + extra
    if qualifier is not None:
        kind, ident = qualifier
        scoped = (
            _team_scope(snap, moments, ident, key)
            if kind == "team"
            else _player_scope(snap, moments, ident, key)
        )
        return scoped + extra
    values = []
    for tid in snap.teams:
        values += _team_scope(snap, moments, tid, key)
    for pid in snap.players:
        values += _player_scope(snap, moments, pid, key)
    return values + _facts([m for m in moments if m.team_id is None], key) + extra


def _strict_pool(
    snap: StatsSnapshot, moments: Sequence[Moment], served: Sequence[Evidence]
) -> list[float]:
    """Every number on the board, for stat names the checker does not know."""
    values: list[float] = [float(snap.score[0]), float(snap.score[1]), snap.momentum]
    for stats in list(snap.teams.values()) + list(snap.last5.values()):
        values += [
            float(v)
            for k, v in stats.model_dump().items()
            if isinstance(v, int | float) and k != "possession_seconds"
        ]
    for player in snap.players.values():
        values += [float(v) for v in player.model_dump().values() if isinstance(v, int | float)]
    for m in moments:
        values += [float(v) for v in m.facts.values() if isinstance(v, int | float)]
    return values + [n for ev in served for n in _numbers(ev.value)]


def check_citations(
    citations: Sequence[Evidence],
    snap: StatsSnapshot,
    moments: Sequence[Moment],
    meta: MatchMeta | None = None,
    served: Sequence[Evidence] = (),
) -> list[str]:
    """Return one issue per citation whose numbers the statistics do not support.

    ``meta`` (the match's rosters) lets a value name a player who has no event yet; ``served``
    is the evidence of crew insights the agent read, numbers from a moment's board that still
    count for their statistic and entity.
    """
    issues: list[str] = []
    pool: list[float] | None = None
    roster = roster_of(meta)
    for citation in citations:
        numbers = _numbers(citation.value)
        if not numbers:
            continue
        key = _key(citation.stat)
        if key == "minute":
            ok = all(0 <= n <= snap.t / 60 + 1 for n in numbers)
        else:
            qualifier = _qualifier(citation.value, snap, roster)
            candidates = _candidates(key, qualifier, snap, moments, served, roster)
            if candidates is None:
                if pool is None:
                    pool = _strict_pool(snap, moments, served)
                candidates = pool
            ok = all(any(_close(n, c) for c in candidates) for n in numbers)
        if not ok:
            issues.append(
                f"citation {citation.stat}={citation.value} is not supported by the statistics"
            )
    return issues
