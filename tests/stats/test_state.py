import pytest

from bts.sim.engine import MatchSimulator, simulate
from bts.sim.league import build_league
from bts.sim.models import MatchMeta
from bts.stats.state import MatchState


def test_possession_sums_to_100_and_score_tracks_goals():
    m = simulate(5)
    st = MatchState(m.meta)
    for e in m.events:
        st.ingest(e)
    s = st.snapshot()
    assert abs(sum(t.possession_pct for t in s.teams.values()) - 100) < 1e-6
    assert s.score == m.score


def test_pass_accuracy_and_xg():
    m = simulate(5)
    st = MatchState(m.meta)
    for e in m.events:
        st.ingest(e)
    home_id = m.meta.home.team_id
    h = st.team(home_id)
    assert h.pass_accuracy == pytest.approx(h.passes_completed / h.passes)
    assert h.xg == pytest.approx(
        sum(e.meta["xg"] for e in m.events if e.type == "shot" and e.team_id == home_id),
        abs=1e-3,
    )


def test_zero_division_safe():
    m = simulate(5)
    st = MatchState(m.meta)
    s = st.snapshot()
    assert all(t.pass_accuracy == 0.0 and t.possession_pct == 50.0 for t in s.teams.values())


def test_momentum_bounded_and_tracks_hidden_momentum():
    sim = MatchSimulator(11, *build_league(11)[:2])
    st = MatchState(MatchMeta(match_id="m11", seed=11, home=sim.home, away=sim.away, venue="v"))
    obs = []
    for e in sim.iter_events():
        st.ingest(e)
        obs.append((e.t, st.snapshot().momentum))
    assert all(-1 <= v <= 1 for _, v in obs)
    # sign agreement with the hidden trace at full time
    assert (obs[-1][1] > 0) == (sim.momentum_trace[-1][1] > 0) or abs(
        sim.momentum_trace[-1][1]
    ) < 0.2


def test_recent_events_and_clock():
    m = simulate(5)
    st = MatchState(m.meta)
    for e in m.events[:50]:
        st.ingest(e)
    assert [e.event_id for e in st.recent_events(12)] == [e.event_id for e in m.events[38:50]]
    assert st.clock == m.events[49].t
