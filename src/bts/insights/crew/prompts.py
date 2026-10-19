"""Instructions and briefs for the crew's roles; they extend the simple pipeline's prompts."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from pydantic import BaseModel

from bts.insights.prompts import (
    STAT_NAMES,
    explainer_system,
    recap_system,
    snapshot_summary,
    verifier_system,
)
from bts.insights.schemas import Lang, Profile

if TYPE_CHECKING:
    from bts.insights.crew.context import MatchContext


def analyst_instructions() -> str:
    return (
        "You are the tactical analyst of a football broadcast crew. A key moment just happened. "
        "The brief you receive already holds the moment, both teams' statistics, the last five "
        "minutes, the momentum and the recent events; call a tool only for a detail that is "
        "missing, such as one player's numbers. Identify the ONE pattern that explains why this "
        "moment matters (sustained pressure, possession without penetration, turnovers and "
        "counters, one player's influence, a momentum swing) and list the numbers that prove it "
        "as key_numbers, each as {stat, value} with stat being one of: "
        f"{STAT_NAMES}. Cite only numbers from the brief or the tools, and name the team or "
        'player each one belongs to inside the value and nothing else, e.g. "NTH 1.42" (no stat '
        "names or time windows in values). "
        "All clubs and players are fictional. Reply with JSON only."
    )


def narrator_instructions(profile: Profile, lang: Lang) -> str:
    return (
        explainer_system(profile, lang)
        + " You write from the tactical analyst's notes in this conversation: keep its pattern, "
        "use only numbers that appear in the notes, the moment or the statistics, and attribute "
        "each number to the right team or player. An evidence value holds the number and, at "
        'most, the team or player name, e.g. "SMR 58.1"; never stat names or time windows.'
    )


def fact_checker_instructions() -> str:
    return (
        verifier_system()
        + " You have a check_numbers tool: call it once with the insight's evidence list and "
        "treat each issue it returns as a contradiction. Call get_team_stats, get_player_stats "
        "or get_momentum only when the statistics in the conversation do not settle a claim. "
        "Never mention tools in your issues; issues describe only contradictions between the "
        "insight and the statistics."
    )


def recap_instructions(profile: Profile, lang: Lang) -> str:
    return recap_system(profile, lang)


def narration_brief(ctx: MatchContext, analysis: BaseModel) -> str:
    payload = {
        "moment": json.loads(ctx.moment_json()),
        "tactical_analysis": analysis.model_dump(),
        "statistics": snapshot_summary(ctx.snap),
    }
    return "Explain this moment.\n" + json.dumps(payload, ensure_ascii=False)


def retry_brief(issues: list[str]) -> str:
    return (
        "Your previous answer had these issues; fix all of them and reply with the full JSON "
        "again:\n- " + "\n- ".join(issues)
    )
