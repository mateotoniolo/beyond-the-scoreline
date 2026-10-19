from bts.sim.engine import simulate
from tests.stats.test_moments import feed


def test_possession_milestone_reports_the_minute_it_fires():
    for seed in range(1, 40):
        ms = [m for m in feed(simulate(seed).events, seed=seed) if m.type == "milestone"]
        for m in ms:
            if m.facts.get("kind") == "possession":
                assert int(m.facts["minute"]) == int(m.t // 60)
                return
    raise AssertionError("no possession milestone in seeds 1..39")
