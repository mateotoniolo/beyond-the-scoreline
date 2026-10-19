from bts.insights.schemas import Evidence, Insight
from bts.insights.verifier import check_facts


def _insight(evidence, profile="analyst", why="Why it matters, with numbers."):
    return Insight(
        insight_id="x",
        moment_id="goal-1",
        profile=profile,
        lang="en",
        headline="Headline",
        why_it_matters=why,
        evidence=evidence,
        confidence=0.5,
        verified=False,
        source="llm",
    )


def test_named_stat_must_match_that_stat(moment, snap):
    team_xg = snap.teams[moment.team_id].xg
    ok = _insight([Evidence(stat="xg", value=f"{team_xg:.2f}")])
    assert check_facts(ok, snap, moment) == []
    wrong = _insight([Evidence(stat="xg", value=f"{team_xg + 1.15:.2f}")])
    assert any("xg" in issue for issue in check_facts(wrong, snap, moment))


def test_integer_stats_allow_one_unit_and_floats_five_percent(moment, snap):
    team = snap.teams[moment.team_id]
    near_int = _insight([Evidence(stat="passes", value=str(team.passes + 1))])
    assert check_facts(near_int, snap, moment) == []
    far_int = _insight([Evidence(stat="passes", value=str(team.passes + 3))])
    assert check_facts(far_int, snap, moment)
    pct = _insight([Evidence(stat="possession_pct", value=f"{team.possession_pct * 1.03:.0f}%")])
    assert check_facts(pct, snap, moment) == []


def test_moment_facts_and_spaced_names_resolve(moment, snap):
    shot = _insight([Evidence(stat="shot xG", value=f"{float(moment.facts['xg']):.2f}")])
    assert check_facts(shot, snap, moment) == []
    score = _insight([Evidence(stat="score", value=f"{snap.score[0]}-{snap.score[1]}")])
    assert check_facts(score, snap, moment) == []


def test_unknown_stat_name_falls_back_to_strict_pool(moment, snap):
    assert check_facts(_insight([Evidence(stat="vibes", value="150")]), snap, moment)
