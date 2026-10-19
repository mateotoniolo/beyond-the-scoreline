"""Deterministic check of the question desk's citations against the live statistics.

Same number extraction and tolerances as ``verifier.check_facts``, but there is no moment to
anchor on: a value that names a team resolves against that team, a value that names a player
against that player, and an unqualified value against everything on the board.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from bts.insights.qa.context import PLAYER_STATS
from bts.insights.schemas import Evidence
from bts.insights.verifier import CLOCK_RE, IDENT_RE, NUMBER_RE, PAREN_RE, _close, _normalize
from bts.sim.models import MatchMeta
from bts.stats.moments import Moment
from bts.stats.state import StatsSnapshot

Roster = dict[str, str]  # lower-case player name -> player id

QA_ALIASES = {
    "chances_created": "key_passes",
    "chances": "key_passes",
    "key_pass": "key_passes",
    "time": "minute",
}
WORD_RE = re.compile(r"[a-z]+")


def _numbers(value: str) -> list[float]:
    cleaned = CLOCK_RE.sub(lambda m: str(int(m[1]) + int(m[2]) / 60), value)
    cleaned = IDENT_RE.sub(" ", PAREN_RE.sub("", cleaned)).replace("%", "")
    return [float(n) for n in NUMBER_RE.findall(cleaned)]


def roster_of(meta: MatchMeta | None) -> Roster:
    if meta is None:
        return {}
    return {p.name.lower(): p.player_id for t in (meta.home, meta.away) for p in t.players}


def _qualifier(value: str, snap: StatsSnapshot, roster: Roster) -> tuple[str, str] | None:
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


def _team_candidates(snap: StatsSnapshot, tid: str, key: str) -> list[float]:
    values = _stat_values(snap.teams[tid].model_dump(), key)
    if tid in snap.last5:
        values += _stat_values(snap.last5[tid].model_dump(), key)
    return values


def _player_candidates(snap: StatsSnapshot, pid: str, key: str) -> list[float]:
    if key not in PLAYER_STATS:
        return []
    if pid not in snap.players:  # on the roster, no event yet: every statistic is zero
        return [0.0]
    return _stat_values(snap.players[pid].model_dump(), key)


def _moment_candidates(moments: Sequence[Moment], key: str) -> list[float]:
    facts_key = "xg" if key == "shot_xg" else key
    return [
        float(m.facts[facts_key])
        for m in moments
        if isinstance(m.facts.get(facts_key), int | float)
    ]


def _key(stat: str) -> str:
    key = _normalize(stat)
    return QA_ALIASES.get(key, key)


def _served_candidates(served: Sequence[Evidence], key: str) -> list[float]:
    return [n for ev in served if _key(ev.stat) == key for n in _numbers(ev.value)]


def _candidates(
    key: str,
    qualifier: tuple[str, str] | None,
    snap: StatsSnapshot,
    moments: Sequence[Moment],
    served: Sequence[Evidence],
) -> list[float]:
    extra = _served_candidates(served, key)
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
            _team_candidates(snap, ident, key)
            if kind == "team"
            else _player_candidates(snap, ident, key)
        )
        if scoped:
            return scoped + extra
    values: list[float] = []
    for tid in snap.teams:
        values += _team_candidates(snap, tid, key)
    for pid in snap.players:
        values += _player_candidates(snap, pid, key)
    return values + _moment_candidates(moments, key) + extra


def _strict_pool(snap: StatsSnapshot, moments: Sequence[Moment]) -> list[float]:
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
    return values


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
    count for their statistic.
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
            candidates = _candidates(key, qualifier, snap, moments, served)
            if not candidates:
                if pool is None:
                    pool = _strict_pool(snap, moments)
                    pool += [n for ev in served for n in _numbers(ev.value)]
                candidates = pool
            ok = all(any(_close(n, c) for c in candidates) for n in numbers)
        if not ok:
            issues.append(
                f"citation {citation.stat}={citation.value} is not supported by the statistics"
            )
    return issues
