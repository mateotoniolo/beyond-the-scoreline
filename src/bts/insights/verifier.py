"""Deterministic fact checks plus an LLM cross-check for generated insights."""

from __future__ import annotations

import re

from pydantic import BaseModel

from bts.insights.llm import LLMClient, LLMError
from bts.insights.prompts import verifier_system, verifier_user
from bts.insights.schemas import FAN_MAX_NUMBERS, HEADLINE_MAX, WHY_MAX, Evidence, Insight
from bts.stats.moments import Moment
from bts.stats.state import StatsSnapshot

NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")
REL_TOL = 0.05
ABS_TOL = 1.0


class ExplainerOutput(BaseModel):
    """Model-facing schema: every field required, no constraints (strict JSON schema rules)."""

    headline: str
    why_it_matters: str
    evidence: list[Evidence]
    confidence: float


class VerifierOutput(BaseModel):
    ok: bool
    issues: list[str]


def _known_numbers(snap: StatsSnapshot, moment: Moment) -> list[float]:
    values: list[float] = [float(snap.score[0]), float(snap.score[1]), snap.momentum]
    for stats in list(snap.teams.values()) + list(snap.last5.values()):
        values.extend(float(v) for v in stats.model_dump().values() if isinstance(v, int | float))
    values.extend(snap.pressure_index.values())
    if moment.player_id and moment.player_id in snap.players:
        ps = snap.players[moment.player_id]
        values.extend(float(v) for v in ps.model_dump().values() if isinstance(v, int | float))
    values.extend(float(v) for v in moment.facts.values() if isinstance(v, int | float))
    values.append(moment.t / 60)
    return values


def _supported(value: float, known: list[float]) -> bool:
    return any(abs(value - k) <= max(ABS_TOL, REL_TOL * abs(k)) for k in known)


def check_facts(insight: Insight, snap: StatsSnapshot, moment: Moment) -> list[str]:
    """Return human-readable issues; an empty list means the insight passes."""
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
    known = _known_numbers(snap, moment)
    for ev in insight.evidence:
        match = NUMBER_RE.search(ev.value.replace("%", ""))
        if match is None:
            continue
        value = float(match.group())
        if not _supported(value, known):
            issues.append(f"evidence {ev.stat}={ev.value} is not supported by the statistics")
    return issues


async def verify(
    llm: LLMClient, insight: Insight, snap: StatsSnapshot, moment: Moment
) -> VerifierOutput:
    issues = check_facts(insight, snap, moment)
    if issues:
        return VerifierOutput(ok=False, issues=issues)
    try:
        return await llm.complete_json(
            system=verifier_system(),
            user=verifier_user(insight, snap, moment),
            schema=VerifierOutput,
        )
    except LLMError as exc:
        return VerifierOutput(ok=True, issues=[f"verifier_unavailable: {exc}"])
