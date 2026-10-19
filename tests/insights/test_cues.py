from bts.insights.cues import from_insight
from bts.insights.templates import render_insight


def test_cues_timing_and_layers(detected11):
    snap, moments = detected11
    goal = next(x for x in moments if x.type == "goal")
    cues = from_insight(render_insight(goal, snap, "analyst", "en"), goal)
    assert [c.layer for c in cues] == ["lower_third", "side_panel", "ticker"]
    assert all(c.t_start == goal.t for c in cues)
    assert [c.duration_s for c in cues] == [8, 20, 12]
    assert all(c.moment_id == goal.moment_id and c.lang == "en" for c in cues)
    assert len(from_insight(render_insight(goal, snap, "fan", "en"), goal)) == 2
