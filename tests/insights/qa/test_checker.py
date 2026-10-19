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


def test_roster_player_without_events_counts_as_zero(live):
    snap = live.snapshot()
    bench = next(
        p
        for t in (live.meta.home, live.meta.away)
        for p in t.players
        if p.player_id not in snap.players
    )
    zero = [Evidence(stat="passes", value=f"{bench.name} 0")]
    assert check_citations(zero, snap, live.moments, live.meta) == []
    some = [Evidence(stat="passes", value=f"{bench.name} 3")]
    assert check_citations(some, snap, live.moments, live.meta)


def test_evidence_served_by_an_insight_is_accepted_for_its_stat(live):
    snap = live.snapshot()
    away = snap.team_names[snap.away_id]
    old_board = [Evidence(stat="xg", value=f"{away} 9.99")]
    assert check_citations(old_board, snap, live.moments, live.meta)
    served = [Evidence(stat="xg", value="9.99")]
    assert check_citations(old_board, snap, live.moments, live.meta, served) == []
    other_stat = [Evidence(stat="passes", value=f"{away} 9.99")]
    assert check_citations(other_stat, snap, live.moments, live.meta, served)


def test_qualified_values_never_fall_through_to_the_other_side(live):
    snap = live.snapshot()
    home, away = _teams(snap)
    top = max(snap.players.values(), key=lambda p: p.key_passes)
    assert top.key_passes >= 1
    team_cited = [Evidence(stat="key_passes", value=f"{home} {top.key_passes}")]
    assert check_citations(team_cited, snap, live.moments, live.meta)  # teams have no key passes
    poss = snap.teams[snap.home_id].possession_pct
    player_cited = [Evidence(stat="possession_pct", value=f"{top.name} {poss:.2f}")]
    assert check_citations(player_cited, snap, live.moments, live.meta)  # players have none


def test_team_qualified_values_accept_that_team_moment_facts(live):
    snap = live.snapshot()
    goal = next(m for m in live.moments if m.type == "goal")
    team = snap.team_names[goal.team_id]
    ev = [Evidence(stat="shot_xg", value=f"{team} {float(goal.facts['xg']):.3f}")]
    assert check_citations(ev, snap, live.moments, live.meta) == []


def test_served_evidence_keeps_its_qualifier(live):
    snap = live.snapshot()
    home, away = _teams(snap)
    served = [Evidence(stat="xg", value=f"{away} 9.99")]
    leaked = [Evidence(stat="xg", value=f"{home} 9.99")]
    assert check_citations(leaked, snap, live.moments, live.meta, served)
    same = [Evidence(stat="xg", value=f"{away} 9.99")]
    assert check_citations(same, snap, live.moments, live.meta, served) == []
    bare = [Evidence(stat="xg", value="9.99")]
    assert check_citations(bare, snap, live.moments, live.meta, served) == []
