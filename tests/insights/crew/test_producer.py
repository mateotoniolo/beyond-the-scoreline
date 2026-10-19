from bts.insights.crew.producer import MAX_WAIT_S, plan_cues
from bts.insights.cues import LOWER_THIRD_S, SIDE_PANEL_S, TICKER_S
from bts.insights.schemas import AgentStep, Insight
from bts.insights.templates import render_insight


def _two_close_moments(detected11):
    snap, moments = detected11
    goal = next(m for m in moments if m.type == "goal")
    later = goal.model_copy(update={"moment_id": "m-later", "t": goal.t + 3.0, "severity": 0.4})
    return snap, goal, later


def _layer(cues, layer):
    return [c for c in cues if c.layer == layer]


def test_lower_third_never_overlaps_previous(detected11):
    snap, goal, later = _two_close_moments(detected11)
    first = plan_cues(render_insight(goal, snap, "analyst", "en"), goal, [], speed=1.0)
    second = plan_cues(render_insight(later, snap, "analyst", "en"), later, first, speed=1.0)
    assert _layer(first, "lower_third")[0].t_start == goal.t
    assert _layer(second, "lower_third")[0].t_start == goal.t + LOWER_THIRD_S


def test_short_waits_queue_and_long_waits_cut_the_running_cue(detected11):
    snap, goal, later = _two_close_moments(detected11)
    first = plan_cues(render_insight(goal, snap, "analyst", "en"), goal, [], speed=1.0)
    second = plan_cues(render_insight(later, snap, "analyst", "en"), later, first, speed=1.0)
    # Ticker: 9 s left on the running cue, within MAX_WAIT_S, so the new one queues.
    assert TICKER_S - 3.0 <= MAX_WAIT_S
    assert _layer(second, "ticker")[0].t_start == goal.t + TICKER_S
    # Side panel: 17 s left, too long to wait, so the new one starts now and cuts the old one.
    assert SIDE_PANEL_S - 3.0 > MAX_WAIT_S
    panels = _layer(second, "side_panel")
    new_panel = next(c for c in panels if c.moment_id == later.moment_id)
    cut_panel = next(c for c in panels if c.moment_id == goal.moment_id)
    assert new_panel.t_start == later.t
    assert cut_panel.cue_id == _layer(first, "side_panel")[0].cue_id
    assert cut_panel.duration_s == 3.0


def test_durations_scale_with_playback_speed(detected11):
    snap, goal, later = _two_close_moments(detected11)
    later = later.model_copy(update={"t": goal.t + 100.0})
    first = plan_cues(render_insight(goal, snap, "fan", "en"), goal, [], speed=30.0)
    second = plan_cues(render_insight(later, snap, "fan", "en"), later, first, speed=30.0)
    # 8 real seconds at 30x cover 240 match seconds, so a cue 100 s later still waits.
    assert _layer(second, "lower_third")[0].t_start == goal.t + LOWER_THIRD_S * 30.0


def test_goal_preempts_running_lower_third(detected11):
    snap, goal, later = _two_close_moments(detected11)
    quiet, loud = later.model_copy(update={"t": goal.t - 3.0, "moment_id": "m-quiet"}), goal
    first = plan_cues(render_insight(quiet, snap, "analyst", "en"), quiet, [], speed=1.0)
    second = plan_cues(render_insight(loud, snap, "analyst", "en"), loud, first, speed=1.0)
    new_lt = [c for c in _layer(second, "lower_third") if c.moment_id == goal.moment_id][0]
    cut = [c for c in _layer(second, "lower_third") if c.moment_id == "m-quiet"][0]
    assert new_lt.t_start == goal.t
    assert cut.cue_id == _layer(first, "lower_third")[0].cue_id
    assert cut.duration_s == 3.0


def test_far_apart_cues_keep_their_moment_time(detected11):
    snap, goal, later = _two_close_moments(detected11)
    later = later.model_copy(update={"t": goal.t + 600.0})
    first = plan_cues(render_insight(goal, snap, "fan", "es"), goal, [], speed=1.0)
    second = plan_cues(render_insight(later, snap, "fan", "es"), later, first, speed=1.0)
    assert all(c.t_start == later.t for c in second)
    assert all(c.moment_id == later.moment_id for c in second)


def test_insight_trace_is_optional_and_typed(detected11):
    snap, goal, _ = _two_close_moments(detected11)
    insight = render_insight(goal, snap, "fan", "en")
    assert insight.trace == []
    step = AgentStep(agent="narrator", ms=1200, tool_calls=0, ok=True)
    with_trace = Insight(**{**insight.model_dump(), "trace": [step]})
    assert with_trace.model_dump()["trace"][0]["agent"] == "narrator"
