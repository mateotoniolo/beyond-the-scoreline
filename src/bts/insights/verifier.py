"""Deterministic fact checks plus an LLM cross-check for generated insights."""

from __future__ import annotations

import re

from pydantic import BaseModel

from bts.insights.llm import LLMClient, LLMError
from bts.insights.prompts import verifier_system, verifier_user
from bts.insights.schemas import FAN_MAX_NUMBERS, HEADLINE_MAX, WHY_MAX, Evidence, Insight
from bts.stats.moments import Moment
from bts.stats.state import StatsSnapshot

# A minus sign only counts when it is not the dash of a range such as "1-3".
NUMBER_RE = re.compile(r"(?<!\d)-?\d+(?:\.\d+)?")
PAREN_RE = re.compile(r"\([^)]*\)")
CLOCK_RE = re.compile(r"\b(\d{1,3}):(\d{2})\b")
# Identifiers such as ``last_5_min`` or ``shot_xg`` are labels, not numbers.
IDENT_RE = re.compile(r"\S*_\S*")
# Verifier replies that describe a claim as fine are commentary, not contradictions.
NON_ISSUE_RE = re.compile(
    r"no issue|not a contradiction|matches|is supported|is correct|consistent with"
    r"|no contradiction",
    re.IGNORECASE,
)


class ExplainerOutput(BaseModel):
    """Model-facing schema: every field required, no constraints (strict JSON schema rules)."""

    headline: str
    why_it_matters: str
    evidence: list[Evidence]
    confidence: float


class VerifierOutput(BaseModel):
    ok: bool
    issues: list[str]


ALIASES = {
    "xg": "xg",
    "expected_goals": "xg",
    "shot_xg": "shot_xg",
    "chance_xg": "shot_xg",
    "possession": "possession_pct",
    "possession_pct": "possession_pct",
    "possession_percent": "possession_pct",
    "pass_accuracy": "pass_accuracy",
    "accuracy": "pass_accuracy",
    "passes_completed": "passes_completed",
    "completed_passes": "passes_completed",
    "passes": "passes",
    "shots": "shots",
    "shots_on_target": "shots_on_target",
    "on_target": "shots_on_target",
    "goals": "goals",
    "pressures": "pressures",
    "pressure_events": "pressures",
    "fouls": "fouls",
    "tackles_won": "tackles_won",
    "final_third_entries": "final_third_entries",
    "momentum": "momentum",
    "score": "score",
    "minute": "minute",
    "clock": "minute",
}
INT_TOL = 1.0
FLOAT_REL = 0.05
FLOAT_ABS = 0.05


def _normalize(stat: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "_", stat.strip().lower()).strip("_")
    return ALIASES.get(key, key)


def _close(value: float, known: float) -> bool:
    if float(known).is_integer() and value.is_integer():
        return abs(value - known) <= INT_TOL
    return abs(value - known) <= max(FLOAT_ABS, FLOAT_REL * abs(known))


def _candidates_for(key: str, snap: StatsSnapshot, moment: Moment) -> list[float]:
    """Numbers a correctly named stat may legitimately refer to."""
    teams = [moment.team_id] if moment.team_id in snap.teams else []
    teams += [t for t in snap.teams if t not in teams]
    values: list[float] = []
    if key == "score":
        return [float(snap.score[0]), float(snap.score[1])]
    if key == "minute":
        return [moment.t / 60, snap.t / 60]
    if key == "momentum":
        values = [snap.momentum, -snap.momentum]
        for name in ("momentum_before", "momentum_now"):
            if isinstance(moment.facts.get(name), int | float):
                value = float(moment.facts[name])
                values.extend((value, -value))
        return values
    if key == "shot_xg":
        values.extend(float(v) for k, v in moment.facts.items() if k == "xg")
    if key in moment.facts and isinstance(moment.facts[key], int | float):
        values.append(float(moment.facts[key]))
    for tid in teams:
        for stats in (snap.teams[tid], snap.last5.get(tid)):
            if stats is None:
                continue
            data = stats.model_dump()
            if key in data and isinstance(data[key], int | float):
                values.append(float(data[key]))
    if moment.player_id and moment.player_id in snap.players:
        data = snap.players[moment.player_id].model_dump()
        if key in data and isinstance(data[key], int | float):
            values.append(float(data[key]))
    return values


def _strict_pool(snap: StatsSnapshot, moment: Moment) -> list[float]:
    """Fallback for unrecognised stat names: every number on the board, matched strictly."""
    values: list[float] = [float(snap.score[0]), float(snap.score[1]), snap.momentum]
    for stats in list(snap.teams.values()) + list(snap.last5.values()):
        values.extend(
            float(v)
            for k, v in stats.model_dump().items()
            if isinstance(v, int | float) and k != "possession_seconds"
        )
    if moment.player_id and moment.player_id in snap.players:
        values.extend(
            float(v)
            for v in snap.players[moment.player_id].model_dump().values()
            if isinstance(v, int | float)
        )
    values.extend(float(v) for v in moment.facts.values() if isinstance(v, int | float))
    return values


def _supported(value: float, candidates: list[float]) -> bool:
    return any(_close(value, k) for k in candidates)


def check_facts(insight: Insight, snap: StatsSnapshot, moment: Moment) -> list[str]:
    """Return human-readable issues; an empty list means the insight passes.

    Evidence is resolved by stat name: ``xg`` must match the team's (or player's or moment's)
    xG, ``passes`` the pass count, and so on. Integer stats tolerate one unit, floats 5%.
    Unknown names fall back to a strict match against every number on the board.
    """
    issues: list[str] = []
    if len(insight.headline) > HEADLINE_MAX:
        issues.append(f"headline longer than {HEADLINE_MAX} characters")
    limit = WHY_MAX[insight.profile]
    if len(insight.why_it_matters) > limit:
        issues.append(f"why_it_matters longer than {limit} characters for a {insight.profile}")
    if not insight.headline.strip() or not insight.why_it_matters.strip():
        issues.append("empty headline or why_it_matters")
    if insight.profile == "fan":
        numbers = NUMBER_RE.findall(insight.why_it_matters)
        if len(numbers) > FAN_MAX_NUMBERS:
            issues.append(
                f"fan copy uses {len(numbers)} numbers; at most {FAN_MAX_NUMBERS} allowed"
            )
    elif not insight.evidence:
        issues.append("analyst copy must cite at least one piece of numeric evidence")
    pool = _strict_pool(snap, moment)
    for ev in insight.evidence:
        cleaned = CLOCK_RE.sub(lambda m: str(int(m[1]) + int(m[2]) / 60), ev.value)
        cleaned = IDENT_RE.sub(" ", PAREN_RE.sub("", cleaned)).replace("%", "")
        numbers = [float(n) for n in NUMBER_RE.findall(cleaned)]
        if not numbers:
            continue
        key = _normalize(ev.stat)
        candidates = _candidates_for(key, snap, moment) or pool
        for value in numbers:
            if not _supported(value, candidates):
                issues.append(f"evidence {ev.stat}={ev.value} is not supported by the statistics")
                break
    return issues


async def verify(
    llm: LLMClient, insight: Insight, snap: StatsSnapshot, moment: Moment
) -> VerifierOutput:
    issues = check_facts(insight, snap, moment)
    if issues:
        return VerifierOutput(ok=False, issues=issues)
    try:
        result = await llm.complete_json(
            system=verifier_system(),
            user=verifier_user(insight, snap, moment),
            schema=VerifierOutput,
        )
    except LLMError as exc:
        return VerifierOutput(ok=True, issues=[f"verifier_unavailable: {exc}"])
    if result.ok:
        return VerifierOutput(ok=True, issues=[])
    contradictions = [i for i in result.issues if i.strip() and not NON_ISSUE_RE.search(i)]
    return VerifierOutput(ok=not contradictions, issues=contradictions)
