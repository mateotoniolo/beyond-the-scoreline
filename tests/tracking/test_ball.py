import pytest

from bts.tracking.ball import BRIDGE_SPEED_MS, CARRY_SPEED_MS, BallPath, metres, travel_seconds


def test_ball_at_anchor_of_the_last_event_at_a_time(placed11):
    path = BallPath(placed11)
    last_at = {}
    for p in placed11:
        if p.start is not None:
            last_at[p.event.t] = p.end_or_start
    assert len(last_at) > 1000
    for t, xy in last_at.items():
        assert path.at(t) == pytest.approx(xy, abs=1e-6), t


def test_pass_leaves_start_at_its_own_speed(placed11):
    path = BallPath(placed11)
    p = next(
        p
        for p in placed11
        if p.event.type == "pass" and p.event.outcome == "success" and p.event.t > 20
    )
    travel = metres(p.start, p.end) / (p.event.meta["ball_speed"] / 3.6)
    assert 0 < travel < p.event.t
    assert travel_seconds(p) == pytest.approx(travel)
    assert path.at(p.event.t - travel) == pytest.approx(p.start, abs=1e-6)
    mid = path.at(p.event.t - travel / 2)
    expected = ((p.start[0] + p.end[0]) / 2, (p.start[1] + p.end[1]) / 2)
    assert mid == pytest.approx(expected, abs=1e-6)


def test_carry_and_shot_speeds(placed11):
    carry = next(p for p in placed11 if p.event.type == "carry")
    assert travel_seconds(carry) == pytest.approx(metres(carry.start, carry.end) / CARRY_SPEED_MS)
    shot = next(p for p in placed11 if p.event.type == "shot" and p.end is not None)
    speed = shot.event.meta["shot_speed"] / 3.6
    assert travel_seconds(shot) == pytest.approx(metres(shot.start, shot.end) / speed)
    blocked = next(p for p in placed11 if p.event.type == "shot" and p.event.outcome == "blocked")
    assert travel_seconds(blocked) == 0.0
    assert metres((0.0, 0.0), (100.0, 0.0)) == 105.0 and metres((0.0, 0.0), (0.0, 100.0)) == 68.0


def test_ball_rests_then_bridges_to_a_distant_anchor(placed11):
    path = BallPath(placed11)
    goal = next(p for p in placed11 if p.event.type == "shot" and p.event.outcome == "goal")
    kickoff = next(p for p in placed11 if p.event.t > goal.event.t and p.start is not None)
    assert kickoff.start == (50.0, 50.0)
    leave = kickoff.event.t - travel_seconds(kickoff)
    assert path.at(goal.event.t + 1.0) == pytest.approx(goal.end, abs=1e-6)  # resting
    bridge = metres(goal.end, kickoff.start) / BRIDGE_SPEED_MS
    assert goal.event.t < leave - bridge
    assert path.at(leave - bridge) == pytest.approx(goal.end, abs=1e-6)
    assert path.at(leave) == pytest.approx(kickoff.start, abs=1e-6)
    half = path.at(leave - bridge / 2)
    expected = ((goal.end[0] + 50.0) / 2, (goal.end[1] + 50.0) / 2)
    assert half == pytest.approx(expected, abs=1e-6)


def test_same_time_anchors_hand_over_instantly(placed11):
    # A saved shot and the keeper's save share one t: the ball flies to the goal mouth and is in
    # the keeper's hands at t, with no bridge in between.
    path = BallPath(placed11)
    i, shot = next((i, p) for i, p in enumerate(placed11) if p.event.outcome == "saved")
    save = placed11[i + 1]
    assert save.event.type == "goalkeeper" and save.event.t == shot.event.t
    assert path.at(shot.event.t) == pytest.approx(save.start, abs=1e-6)
    assert path.at(shot.event.t - 1e-3) == pytest.approx(shot.end, abs=0.05)


def test_path_is_clamped_outside_the_match(placed11):
    path = BallPath(placed11)
    assert path.at(-5) == (50.0, 50.0)
    assert path.at(10**6) == path.anchors[-1].xy
    ts = [a.t for a in path.anchors]
    assert ts == sorted(ts)
