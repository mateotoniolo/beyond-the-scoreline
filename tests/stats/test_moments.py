from bts.sim.engine import simulate
from bts.sim.models import Event
from bts.stats.moments import KeyMomentDetector, Moment
from bts.stats.state import MatchState


def feed(events: list[Event], seed: int = 11) -> list[Moment]:
    meta = simulate(seed).meta
    state = MatchState(meta)
    detector = KeyMomentDetector()
    out: list[Moment] = []
    for e in events:
        state.ingest(e)
        moment = detector.observe(e, state)
        if moment is not None:
            out.append(moment)
    return out


def test_goal_and_big_chance_detected():
    m = simulate(11)
    ms = feed(m.events)
    assert sum(x.type == "goal" for x in ms) == sum(m.score)
    assert all(x.facts["xg"] >= 0.30 for x in ms if x.type == "big_chance")
    assert all(x.moment_id == f"{x.type}-{x.event_ids[-1]}" for x in ms)


def test_pressure_spike_requires_six_in_two_minutes():
    base = simulate(2).events[0]
    presses = [
        base.model_copy(
            update={
                "event_id": i + 2,
                "t": 100 + i * 10,
                "type": "pressure",
                "team_id": "t2",
                "player_id": "t2p5",
                "outcome": None,
            }
        )
        for i in range(6)
    ]
    ms = feed([base, *presses], seed=2)
    assert [x.type for x in ms][-1] == "pressure_spike" and ms[-1].facts["count"] == 6
    assert sum(x.type == "pressure_spike" for x in ms) == 1


def test_milestones_fire_once():
    m = simulate(11)
    ms = feed(m.events)
    keys = [
        (x.type, x.team_id, x.player_id, x.facts.get("kind")) for x in ms if x.type == "milestone"
    ]
    assert len(keys) == len(set(keys))


def test_period_end_and_card():
    m = simulate(11)
    ms = feed(m.events)
    assert sum(x.type == "period_end" for x in ms) == 2
    cards = [e for e in m.events if e.type == "card"]
    assert sum(x.type == "card" for x in ms) == len(cards)
