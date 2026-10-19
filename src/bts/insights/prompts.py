"""Prompt builders for the explainer, the verifier and the recap."""

from __future__ import annotations

import json

from bts.insights.schemas import HEADLINE_MAX, WHY_MAX, Insight, Lang, Profile
from bts.sim.models import Event
from bts.stats.moments import Moment
from bts.stats.state import StatsSnapshot

LANG_NAME = {"en": "English", "es": "Spanish (Rioplatense register, neutral enough for any market)"}


def moment_payload(moment: Moment, snap: StatsSnapshot) -> dict:
    """The moment with team and player names, so the model never has to decode ids."""
    data = moment.model_dump()
    team = snap.team_names.get(moment.team_id or "")
    data["team"] = team
    if moment.player_id and moment.player_id in snap.players:
        data["player"] = snap.players[moment.player_id].name
    if moment.type == "momentum_shift" and team:
        # Facts are stored home-positive; show them from the named team's point of view.
        sign = 1 if moment.team_id == snap.home_id else -1
        for name in ("momentum_before", "momentum_now"):
            if isinstance(moment.facts.get(name), int | float):
                data["facts"][name] = round(sign * float(moment.facts[name]), 3)
        data["facts"]["momentum_scale"] = f"-1 to 1, positive favours {team}"
    return data


def snapshot_summary(snap: StatsSnapshot) -> dict:
    home, away = snap.team_names[snap.home_id], snap.team_names[snap.away_id]
    return {
        "clock": snap.clock,
        "score": {home: snap.score[0], away: snap.score[1]},
        "momentum_by_team": {home: snap.momentum, away: round(-snap.momentum, 4)},
        "teams": {
            snap.team_names[tid]: snap.teams[tid].model_dump()
            for tid in (snap.home_id, snap.away_id)
        },
        "pressure_index": {snap.team_names[tid]: v for tid, v in snap.pressure_index.items()},
        "last_5_min": {snap.team_names[tid]: snap.last5[tid].model_dump() for tid in snap.last5},
    }


def events_summary(events: list[Event], snap: StatsSnapshot) -> list[dict]:
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


STAT_NAMES = (
    "xg, shot_xg, possession_pct, passes, passes_completed, pass_accuracy, shots, "
    "shots_on_target, goals, pressures, fouls, tackles_won, final_third_entries, momentum, score"
)


def explainer_system(profile: Profile, lang: Lang) -> str:
    audience = (
        "a data-literate football analyst: cite numbers, name the pattern, be precise and dry"
        if profile == "analyst"
        else "a casual fan watching with friends: plain words, warmth, "
        "at most ONE number in the text"
    )
    target = WHY_MAX[profile] - 40
    return (
        "You explain why a football moment matters, using ONLY the statistics provided. "
        f"Write for {audience}. Write in {LANG_NAME[lang]}. "
        f"Hard limits: headline under {HEADLINE_MAX} characters; why_it_matters under "
        f"{target} characters (two short sentences at most). "
        "Every number you cite must appear in the statistics you were given; "
        "put each cited number in the evidence list as {stat, value}, at most four items, "
        f"with stat being one of: {STAT_NAMES}. "
        "Do not invent players, clubs or events. "
        "All clubs and players are fictional. Reply with JSON only."
    )


def explainer_user(
    moment: Moment, snap: StatsSnapshot, recent: list[Event], issues: list[str] | None = None
) -> str:
    payload = {
        "moment": moment_payload(moment, snap),
        "team_names": snap.team_names,
        "statistics": snapshot_summary(snap),
        "recent_events": events_summary(recent, snap),
    }
    text = json.dumps(payload, ensure_ascii=False)
    if issues:
        text += "\n\nYour previous answer had these issues; fix all of them:\n- " + "\n- ".join(
            issues
        )
    return text


def verifier_system() -> str:
    return (
        "You are a fact checker for football commentary. You receive statistics and a short "
        "insight. Set ok to false ONLY if a claim contradicts the statistics: a wrong number, a "
        "wrong team or player, a wrong scoreline, an event that did not happen. Rounding, "
        "paraphrase, tone, emphasis, imprecise wording and missing context are NOT problems. "
        'If nothing contradicts the statistics, return {"ok": true, "issues": []}. '
        "When ok is false, list only the contradictions, one short sentence each. "
        "Reply with JSON only."
    )


def verifier_user(insight: Insight, snap: StatsSnapshot, moment: Moment) -> str:
    payload = {
        "insight": {
            "headline": insight.headline,
            "why_it_matters": insight.why_it_matters,
            "evidence": [e.model_dump() for e in insight.evidence],
        },
        "moment": moment_payload(moment, snap),
        "team_names": snap.team_names,
        "statistics": snapshot_summary(snap),
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
        "statistics": snapshot_summary(snap),
        "moments": [moment_payload(m, snap) for m in moments],
        "team_names": snap.team_names,
    }
    return json.dumps(payload, ensure_ascii=False)
