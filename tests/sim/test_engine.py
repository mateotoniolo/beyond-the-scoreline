from collections import Counter

from bts.sim.engine import MatchSimulator, simulate
from bts.sim.league import build_league


def test_same_seed_same_events():
    assert simulate(7).events == simulate(7).events


def test_different_seeds_differ():
    assert simulate(7).events != simulate(8).events


def test_time_is_monotonic_and_bracketed_by_period_markers():
    m = simulate(3)
    ts = [e.t for e in m.events]
    assert ts == sorted(ts)
    assert m.events[0].type == "period_start" and m.events[0].period == 1
    assert m.events[-1].type == "period_end" and m.events[-1].period == 2
    assert 5400 <= m.events[-1].t <= 6000


def test_score_matches_goal_events():
    m = simulate(11)
    goals = Counter(e.team_id for e in m.events if e.type == "shot" and e.outcome == "goal")
    assert m.score == (goals[m.meta.home.team_id], goals[m.meta.away.team_id])


def test_single_match_plausible():
    m = simulate(5)
    c = Counter(e.type for e in m.events)
    assert 600 <= c["pass"] <= 1300 and 10 <= c["shot"] <= 45 and c["pressure"] > 20
    assert all(0 <= e.start.x <= 100 and 0 <= e.start.y <= 100 for e in m.events)
    assert all("xg" in e.meta for e in m.events if e.type == "shot")
    assert all(
        "pass_distance" in e.meta and "pass_difficulty" in e.meta
        for e in m.events
        if e.type == "pass"
    )


def test_iter_events_matches_run():
    s1 = MatchSimulator(9, *build_league(9)[:2])
    s2 = MatchSimulator(9, *build_league(9)[:2])
    assert list(s1.iter_events()) == s2.run().events


def test_momentum_trace_in_range():
    s = MatchSimulator(11, *build_league(11)[:2])
    m = s.run()
    assert s.momentum_trace and all(-1 <= v <= 1 for _, v in s.momentum_trace)
    goal_ts = [e.t for e in m.events if e.outcome == "goal"]
    assert goal_ts, "seed 11 must contain a goal; pick another seed if the tuned generator changes"
