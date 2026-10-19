"""Instructions and the per-question brief of the question desk."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from bts.insights.prompts import LANG_NAME, STAT_NAMES
from bts.insights.schemas import Lang, Profile

if TYPE_CHECKING:
    from bts.insights.qa.context import QAContext

TOOL_LIST = (
    "get_score_and_clock, get_team_stats, get_player_stats, get_top_players, get_lineup, "
    "get_last_five_minutes, get_momentum, get_moments, get_insight, get_recent_events, "
    "search_events"
)


def qa_instructions(profile: Profile, lang: Lang) -> str:
    audience = (
        "a data-literate football analyst: precise and dry, cite the numbers"
        if profile == "analyst"
        else "a casual fan watching with friends: plain words, warmth, at most two numbers"
    )
    return (
        "You are the question desk of a football broadcast. You answer questions about ONE "
        "match using the data your tools return and nothing else. The user message carries a "
        "match card (clock, score, status, team names and the key moments so far); every "
        "statistic, player number, event or explanation comes from a tool: "
        f"{TOOL_LIST}. Call the tools you need (several at once when they are independent), "
        "then answer. Never use outside knowledge and never guess; all clubs and players are "
        "fictional. If the tools cannot answer the question, say so in one sentence and set "
        "grounded to false. "
        f"Write for {audience}. Write in {LANG_NAME[lang]}. At most three short sentences. "
        "Put every number you mention in citations as {stat, value}: stat is one of "
        f"{STAT_NAMES}, key_passes, minute; value holds the number and the team short name or "
        'player name it belongs to, e.g. "NTH 1.42" or "Player Name 3", and nothing else (no '
        "stat names, no time windows). The answer text is plain prose: never write citations, "
        "braces or stat names inside it. confidence is 0 to 1. grounded is true only when every "
        "claim comes from the tools or the match card. Reply with JSON only."
    )


def question_brief(ctx: QAContext, question: str) -> str:
    card = json.dumps(ctx.match_card(), ensure_ascii=False)
    return f"Match card:\n{card}\n\nQuestion: {question}"
