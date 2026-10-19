import json

from bts.insights import templates
from bts.insights.qa.context import MAX_EVENTS, QAContext

TOOL_NAMES = {
    "get_score_and_clock",
    "get_team_stats",
    "get_player_stats",
    "get_top_players",
    "get_lineup",
    "get_last_five_minutes",
    "get_momentum",
    "get_moments",
    "get_insight",
    "get_recent_events",
    "search_events",
}


def test_tools_are_agent_framework_tools(live):
    tools = QAContext(live, "analyst", "en").tools()
    assert {t.name for t in tools} == TOOL_NAMES
    assert all(t.description for t in tools)


def test_score_and_clock_names_teams(live):
    data = json.loads(QAContext(live, "analyst", "en").score_and_clock())
    snap = live.snapshot()
    assert data["clock"] == snap.clock
    assert set(data["score"]) == set(snap.team_names.values())
    assert data["status"] == "running"
    home, away = live.meta.home, live.meta.away
    assert data["teams"] == {home.short_name: home.name, away.short_name: away.name}


def test_team_stats_by_short_name_hide_ids(live):
    snap = live.snapshot()
    name = snap.team_names[snap.home_id]
    data = json.loads(QAContext(live, "analyst", "en").team_stats(name.lower()))
    assert data["team"] == name and data["is_home"] is True
    assert data["xg"] == snap.teams[snap.home_id].xg
    assert "possession_seconds" not in data


def test_unknown_names_return_hints(live):
    ctx = QAContext(live, "fan", "es")
    assert "unknown_team" in json.loads(ctx.team_stats("Real Nowhere"))
    assert "unknown_player" in json.loads(ctx.player_stats("Nobody"))
    assert "unknown_team" in json.loads(ctx.lineup("Nowhere"))
    assert "unknown_stat" in json.loads(ctx.top_players("vibes"))
    assert "no_insight" in json.loads(ctx.insight("goal-999999"))


def test_player_stats_carry_position_and_shirt(live):
    gk = next(p for p in live.meta.away.players if p.position == "GK")
    data = json.loads(QAContext(live, "analyst", "en").player_stats(gk.name.lower()))
    assert data["player"] == gk.name
    assert data["team"] == live.meta.away.short_name
    assert data["position"] == "GK" and data["shirt"] == gk.shirt
    assert "player_id" not in data and "team_id" not in data


def test_lineup_lists_players_with_positions(live):
    data = json.loads(QAContext(live, "analyst", "en").lineup(live.meta.home.short_name))
    assert data["team"] == live.meta.home.short_name
    assert len(data["players"]) == len(live.meta.home.players)
    assert all({"player", "position", "shirt"} <= set(p) for p in data["players"])


def test_top_players_orders_by_stat(live):
    data = json.loads(QAContext(live, "analyst", "en").top_players("passes", 3))
    assert data["stat"] == "passes" and len(data["players"]) == 3
    values = [p["passes"] for p in data["players"]]
    assert values == sorted(values, reverse=True)
    assert all("team" in p and "player" in p for p in data["players"])
    many = json.loads(QAContext(live, "analyst", "en").top_players("xg", 99))["players"]
    assert 1 <= len(many) <= 10 and many[0]["xg"] >= many[-1]["xg"]


def test_moments_and_insight(live):
    ctx = QAContext(live, "analyst", "en")
    moments = json.loads(ctx.moments())
    assert moments and all("team_id" not in m and "moment_id" in m for m in moments)
    goal = next(m for m in moments if m["type"] == "goal")
    assert goal["team"] in live.snapshot().team_names.values()
    assert "no_insight" in json.loads(ctx.insight(goal["moment_id"]))
    moment = next(m for m in live.moments if m.moment_id == goal["moment_id"])
    live.insights[(goal["moment_id"], "fan", "es")] = templates.render_insight(
        moment, live.snapshot(), "fan", "es"
    )
    fallback = json.loads(ctx.insight(goal["moment_id"]))  # another variant still counts
    assert fallback["headline"] and fallback["lang"] == "es"
    live.insights[(goal["moment_id"], "analyst", "en")] = templates.render_insight(
        moment, live.snapshot(), "analyst", "en"
    )
    data = json.loads(ctx.insight(goal["moment_id"]))
    assert data["lang"] == "en" and data["evidence"] and "insight_id" not in data


def test_search_events_filters_and_bounds(live):
    ctx = QAContext(live, "analyst", "en")
    data = json.loads(ctx.search_events(type="shot"))
    assert data["total"] >= len(data["events"]) >= 1
    assert len(data["events"]) <= MAX_EVENTS
    assert all(e["type"] == "shot" and "team_id" not in e for e in data["events"])
    home = live.meta.home.short_name
    narrowed = json.loads(ctx.search_events(type="shot", team=home, from_minute=0, to_minute=45))
    assert all(e["team"] == home for e in narrowed["events"])
    assert narrowed["total"] <= data["total"]
    shooter = data["events"][0]["player"]
    by_player = json.loads(ctx.search_events(player=shooter.upper()))
    assert by_player["total"] >= 1 and all(e["player"] == shooter for e in by_player["events"])
    assert "unknown_team" in json.loads(ctx.search_events(team="Nowhere"))
    assert "unknown_player" in json.loads(ctx.search_events(player="Nobody"))
    everything = json.loads(ctx.search_events())
    assert everything["total"] == len(live.events) and len(everything["events"]) == MAX_EVENTS


def test_recent_events_are_named_and_bounded(live):
    ctx = QAContext(live, "analyst", "en")
    assert len(json.loads(ctx.recent_events(99))) == MAX_EVENTS
    three = json.loads(ctx.recent_events(3))
    assert len(three) == 3 and all("team" in e and "player" in e for e in three)


def test_momentum_and_last_five_are_per_team(live):
    ctx = QAContext(live, "analyst", "en")
    snap = live.snapshot()
    names = set(snap.team_names.values())
    momentum = json.loads(ctx.momentum())
    assert set(momentum["momentum"]) == names and set(momentum["pressure_index"]) == names
    last5 = json.loads(ctx.last_five_minutes())
    assert set(last5) == names and "possession_seconds" not in next(iter(last5.values()))


def test_match_card_is_compact_and_named(live):
    card = QAContext(live, "analyst", "en").match_card()
    assert {"clock", "score", "status", "teams", "moments"} <= set(card)
    assert all("team_id" not in m and "event_ids" not in m for m in card["moments"])


def test_context_pins_a_snapshot_per_question_and_refreshes(live):
    ctx = QAContext(live, "analyst", "en")
    before = json.loads(ctx.score_and_clock())
    live.advance(200)
    assert json.loads(ctx.score_and_clock())["clock"] == before["clock"]  # one question, one board
    assert ctx.snap.clock == before["clock"]
    ctx.refresh()
    after = json.loads(ctx.score_and_clock())
    assert after["clock"] != before["clock"] and ctx.snap.clock == after["clock"]
    assert len(json.loads(ctx.moments())) == len(live.moments)


def test_insight_records_the_evidence_it_served(live):
    ctx = QAContext(live, "analyst", "en")
    goal = next(m for m in live.moments if m.type == "goal")
    assert ctx.served == []
    ctx.insight(goal.moment_id)  # nothing cached yet
    assert ctx.served == []
    insight = templates.render_insight(goal, live.snapshot(), "analyst", "en")
    live.insights[(goal.moment_id, "analyst", "en")] = insight
    ctx.insight(goal.moment_id)
    assert ctx.served == insight.evidence
