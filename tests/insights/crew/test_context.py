import json

from bts.insights.crew.context import MatchContext

TOOL_NAMES = {
    "get_moment",
    "get_team_stats",
    "get_player_stats",
    "get_last_five_minutes",
    "get_recent_events",
    "get_momentum",
    "check_numbers",
}


def test_team_stats_by_short_name(moment, snap, recent):
    ctx = MatchContext(moment, snap, recent)
    name = snap.team_names[moment.team_id]
    data = json.loads(ctx.team_stats(name))
    assert data["team"] == name
    assert data["xg"] == snap.teams[moment.team_id].xg
    assert "possession_seconds" not in data


def test_tools_handle_unknown_names(moment, snap, recent):
    ctx = MatchContext(moment, snap, recent)
    assert "unknown_team" in json.loads(ctx.team_stats("Real Nowhere"))
    assert "unknown_player" in json.loads(ctx.player_stats("Nobody"))


def test_player_stats_by_name_is_case_insensitive(moment, snap, recent):
    ctx = MatchContext(moment, snap, recent)
    player = snap.players[moment.player_id]
    data = json.loads(ctx.player_stats(player.name.upper()))
    assert data["player"] == player.name
    assert data["team"] == snap.team_names[player.team_id]
    assert "player_id" not in data


def test_moment_json_names_team_and_player(moment, snap, recent):
    data = json.loads(MatchContext(moment, snap, recent).moment_json())
    assert data["team"] == snap.team_names[moment.team_id]
    assert data["player"] == snap.players[moment.player_id].name
    assert "team_id" not in data and "player_id" not in data


def test_momentum_is_per_team(moment, snap, recent):
    data = json.loads(MatchContext(moment, snap, recent).momentum())
    home, away = snap.team_names[snap.home_id], snap.team_names[snap.away_id]
    assert data["momentum"][home] == snap.momentum
    assert data["momentum"][away] == round(-snap.momentum, 4)
    assert set(data["pressure_index"]) == {home, away}


def test_recent_events_are_named_and_bounded(moment, snap, recent):
    data = json.loads(MatchContext(moment, snap, recent).recent_events(3))
    assert len(data) == 3
    assert all("team" in e and "player" in e and "team_id" not in e for e in data)


def test_check_numbers_tool_flags_bad_values(moment, snap, recent):
    ctx = MatchContext(moment, snap, recent)
    bad = json.dumps([{"stat": "xg", "value": "999.9"}])
    good = json.dumps([{"stat": "xg", "value": f"{snap.teams[moment.team_id].xg:.2f}"}])
    assert json.loads(ctx.check_numbers(bad))["ok"] is False
    assert json.loads(ctx.check_numbers(good))["ok"] is True


def test_check_numbers_tool_reports_malformed_input(moment, snap, recent):
    data = json.loads(MatchContext(moment, snap, recent).check_numbers("not json"))
    assert data["ok"] is False and data["issues"]


def test_tools_are_agent_framework_tools(moment, snap, recent):
    tools = MatchContext(moment, snap, recent).tools()
    assert {t.name for t in tools} == TOOL_NAMES
    assert all(t.description for t in tools)
