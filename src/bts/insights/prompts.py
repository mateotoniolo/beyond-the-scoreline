"""Prompt builders for the explainer, the verifier and the recap."""

from __future__ import annotations

import json

from bts.insights.schemas import HEADLINE_MAX, WHY_MAX, Insight, Lang, Profile
from bts.sim.models import Event
from bts.stats.moments import Moment
from bts.stats.state import StatsSnapshot

LANG_NAME = {"en": "English", "es": "Spanish (Rioplatense register, neutral enough for any market)"}


def _snapshot_summary(snap: StatsSnapshot) -> dict:
    return {
        "clock": snap.clock,
        "score": {
            snap.team_names[snap.home_id]: snap.score[0],
            snap.team_names[snap.away_id]: snap.score[1],
        },
        "momentum_home_positive": snap.momentum,
        "teams": {
            snap.team_names[tid]: snap.teams[tid].model_dump()
            for tid in (snap.home_id, snap.away_id)
        },
        "pressure_index": {snap.team_names[tid]: v for tid, v in snap.pressure_index.items()},
        "last_5_min": {snap.team_names[tid]: snap.last5[tid].model_dump() for tid in snap.last5},
    }


def _events_summary(events: list[Event], snap: StatsSnapshot) -> list[dict]:
    out = []
    for e in events:
        name = snap.players[e.player_id].name if e.player_id in snap.players else e.player_id
        out.append(
            {
                "clock": e.clock,
                "team": snap.team_names.get(e.team_id, e.team_id),
                "player": name,
                "type": e.type,
                "subtype": e.subtype,
                "outcome": e.outcome,
                "x": round(e.start.x),
                "y": round(e.start.y),
                "meta": e.meta,
            }
        )
    return out


def explainer_system(profile: Profile, lang: Lang) -> str:
    audience = (
        "a data-literate football analyst: cite numbers, name the pattern, be precise and dry"
        if profile == "analyst"
        else "a casual fan watching with friends: plain words, warmth, "
        "at most ONE number in the text"
    )
    return (
        "You explain why a football moment matters, using ONLY the statistics provided. "
        f"Write for {audience}. Write in {LANG_NAME[lang]}. "
        f"Headline at most {HEADLINE_MAX} characters; "
        f"why_it_matters at most {WHY_MAX[profile]} characters. "
        "Every number you cite must appear in the statistics you were given; "
        "put each cited number in the evidence list as {stat, value}. "
        "Do not invent players, clubs or events. "
        "All clubs and players are fictional. Reply with JSON only."
    )


def explainer_user(
    moment: Moment, snap: StatsSnapshot, recent: list[Event], issues: list[str] | None = None
) -> str:
    payload = {
        "moment": moment.model_dump(),
        "team_names": snap.team_names,
        "statistics": _snapshot_summary(snap),
        "recent_events": _events_summary(recent, snap),
    }
    text = json.dumps(payload, ensure_ascii=False)
    if issues:
        text += "\n\nYour previous answer had these issues; fix all of them:\n- " + "\n- ".join(
            issues
        )
    return text


def verifier_system() -> str:
    return (
        "You are a fact checker for football commentary. Given statistics and a short insight, "
        "decide whether every claim in the insight is supported by the statistics. Numbers may be "
        'rounded. Reply with JSON only: {"ok": bool, "issues": [string]}.'
    )


def verifier_user(insight: Insight, snap: StatsSnapshot, moment: Moment) -> str:
    payload = {
        "insight": {
            "headline": insight.headline,
            "why_it_matters": insight.why_it_matters,
            "evidence": [e.model_dump() for e in insight.evidence],
        },
        "moment": moment.model_dump(),
        "statistics": _snapshot_summary(snap),
    }
    return json.dumps(payload, ensure_ascii=False)


def recap_system(profile: Profile, lang: Lang) -> str:
    audience = "an analyst" if profile == "analyst" else "a casual fan"
    return (
        f"Write a full-time match recap for {audience} in {LANG_NAME[lang]}, "
        "from the statistics and key moments provided only. Two or three short paragraphs "
        "plus a list of key moments (one line each, with the clock). Reply with JSON only: "
        '{"title": string, "paragraphs": [string], "key_moments": [string]}.'
    )


def recap_user(snap: StatsSnapshot, moments: list[Moment], profile: Profile, lang: Lang) -> str:
    payload = {
        "statistics": _snapshot_summary(snap),
        "moments": [m.model_dump() for m in moments],
        "team_names": snap.team_names,
    }
    return json.dumps(payload, ensure_ascii=False)
