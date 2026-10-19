"""Instructions for the three model-backed roles; they extend the simple pipeline's prompts."""

from __future__ import annotations

from bts.insights.prompts import STAT_NAMES, explainer_system, verifier_system
from bts.insights.schemas import Lang, Profile


def analyst_instructions() -> str:
    return (
        "You are the tactical analyst of a football broadcast crew. A key moment just happened. "
        "Call the tools to read the moment, both teams' match statistics, the last five minutes, "
        "the recent events and the momentum before you answer. Identify the ONE pattern that "
        "explains why this moment matters (sustained pressure, possession without penetration, "
        "turnovers and counters, one player's influence, a momentum swing) and list the numbers "
        "that prove it as key_numbers, each as {stat, value} with stat being one of: "
        f"{STAT_NAMES}. Cite only numbers the tools returned, with the team or player they "
        "belong to in the pattern text. All clubs and players are fictional. Reply with JSON only."
    )


def narrator_instructions(profile: Profile, lang: Lang) -> str:
    return (
        explainer_system(profile, lang)
        + " You write from the tactical analyst's notes in this conversation: keep its pattern, "
        "use only numbers that appear in the notes or in the moment, and attribute each number "
        "to the right team or player."
    )


def fact_checker_instructions() -> str:
    return (
        verifier_system()
        + " Before you judge, call check_numbers with the insight's evidence list and treat every "
        "issue it returns as a contradiction. Use get_team_stats, get_player_stats and "
        "get_momentum to confirm that each team, player and number is attributed correctly."
    )
