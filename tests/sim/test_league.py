from collections import Counter

from bts.sim.league import build_league, starting_xi


def test_league_is_deterministic():
    assert build_league(42) == build_league(42)


def test_league_shape():
    teams = build_league(1)
    assert [t.team_id for t in teams] == ["t1", "t2", "t3", "t4"]
    assert {t.style for t in teams} == {"possession", "direct", "pressing", "counter"}
    for t in teams:
        assert len(t.players) == 18
        assert Counter(p.position for p in t.players) == {"GK": 2, "DF": 6, "MF": 6, "FW": 4}
        assert len({p.name for p in t.players}) == 18
        assert [p.shirt for p in t.players] == list(range(1, 19))
        assert all(p.player_id == f"{t.team_id}p{p.shirt}" for p in t.players)


def test_starting_xi_shape():
    xi = starting_xi(build_league(1)[0])
    assert Counter(p.position for p in xi) == {"GK": 1, "DF": 4, "MF": 4, "FW": 2}


def test_style_shapes_attributes():
    teams = {t.style: t for t in build_league(3)}

    def mean(t, a):
        return sum(getattr(p.attrs, a) for p in t.players) / 18

    assert mean(teams["pressing"], "pressing") > mean(teams["possession"], "pressing")
    assert mean(teams["possession"], "passing") > mean(teams["direct"], "passing")
