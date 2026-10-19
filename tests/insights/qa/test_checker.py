from bts.insights.qa.checker import check_citations
from bts.insights.schemas import Evidence


def _teams(snap):
    return snap.team_names[snap.home_id], snap.team_names[snap.away_id]


def test_team_qualified_value_must_match_that_team(live):
    snap = live.snapshot()
    home, _ = _teams(snap)
    home_xg, away_xg = snap.teams[snap.home_id].xg, snap.teams[snap.away_id].xg
    assert abs(home_xg - away_xg) > 0.2, "seed 11 past the first goal separates the xG values"
    ok = [Evidence(stat="xg", value=f"{home} {home_xg:.2f}")]
    assert check_citations(ok, snap, live.moments) == []
    swapped = [Evidence(stat="xg", value=f"{home} {away_xg:.2f}")]
    issues = check_citations(swapped, snap, live.moments)
    assert len(issues) == 1 and "xg" in issues[0]


def test_team_qualified_value_accepts_the_last_five_minutes(live):
    snap = live.snapshot()
    home, _ = _teams(snap)
    last5 = snap.last5[snap.home_id].passes
    full = snap.teams[snap.home_id].passes
    assert abs(last5 - full) > 1
    ev = [Evidence(stat="passes", value=f"{home} {last5}")]
    assert check_citations(ev, snap, live.moments) == []


def test_player_qualified_value_resolves_against_that_player(live):
    snap = live.snapshot()
    ps = max(snap.players.values(), key=lambda p: p.passes)
    ok = [Evidence(stat="passes", value=f"{ps.name} {ps.passes}")]
    assert check_citations(ok, snap, live.moments) == []
    wrong = [Evidence(stat="passes", value=f"{ps.name} {ps.passes + 40}")]
    assert check_citations(wrong, snap, live.moments)
    chances = [Evidence(stat="chances created", value=f"{ps.name}: {ps.key_passes}")]
    assert check_citations(chances, snap, live.moments) == []


def test_unqualified_values_accept_any_team_or_player(live):
    snap = live.snapshot()
    away_xg = snap.teams[snap.away_id].xg
    top = max(snap.players.values(), key=lambda p: p.xg)
    ev = [Evidence(stat="xg", value=f"{away_xg:.2f}"), Evidence(stat="xg", value=f"{top.xg:.2f}")]
    assert check_citations(ev, snap, live.moments) == []
    assert check_citations([Evidence(stat="xg", value="99.9")], snap, live.moments)


def test_score_minute_and_momentum_have_their_own_candidates(live):
    snap = live.snapshot()
    score = [Evidence(stat="score", value=f"{snap.score[0]}-{snap.score[1]}")]
    assert check_citations(score, snap, live.moments) == []
    wrong_score = [Evidence(stat="score", value=f"{snap.score[0] + 5}-{snap.score[1]}")]
    assert check_citations(wrong_score, snap, live.moments)
    played = int(snap.t // 60)
    assert check_citations([Evidence(stat="minute", value=f"{played}'")], snap, live.moments) == []
    assert check_citations([Evidence(stat="clock", value="00:30")], snap, live.moments) == []
    assert check_citations([Evidence(stat="minute", value=f"{played + 30}")], snap, live.moments)
    for sign in (1, -1):
        ev = [Evidence(stat="momentum", value=f"{sign * snap.momentum:.3f}")]
        assert check_citations(ev, snap, live.moments) == []


def test_moment_facts_are_candidates(live):
    snap = live.snapshot()
    goal = next(m for m in live.moments if m.type == "goal")
    ev = [Evidence(stat="shot_xg", value=f"{float(goal.facts['xg']):.2f}")]
    assert check_citations(ev, snap, live.moments) == []


def test_unknown_stat_falls_back_to_strict_pool(live):
    snap = live.snapshot()
    passes = snap.teams[snap.home_id].passes
    assert check_citations([Evidence(stat="vibes", value=str(passes))], snap, live.moments) == []
    assert check_citations([Evidence(stat="vibes", value="123456")], snap, live.moments)


def test_values_without_numbers_are_ignored(live):
    snap = live.snapshot()
    ev = [Evidence(stat="goals", value="none yet"), Evidence(stat="xg", value="")]
    assert check_citations(ev, snap, live.moments) == []
