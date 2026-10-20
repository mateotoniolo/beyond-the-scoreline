import math
import time

import pytest

from bts.sim.engine import PITCH_X_M, PITCH_Y_M, simulate
from bts.sim.league import starting_xi
from bts.tracking import FPS, MAX_FRAMES, MAX_SPEED_MS, MatchTracker
from bts.tracking.ball import travel_seconds
from bts.tracking.formation import formation_target, lineup_slots

STEP_M = MAX_SPEED_MS / FPS


def _moved_m(a, b):
    return math.hypot((b[0] - a[0]) * PITCH_X_M / 100, (b[1] - a[1]) * PITCH_Y_M / 100)


@pytest.fixture(scope="module")
def tracker11(match11):
    return MatchTracker(match11.meta, match11.events)


def test_lineup_slots_follow_the_starting_eleven(match11):
    slots = lineup_slots(match11.meta.home)
    xi = starting_xi(match11.meta.home)
    assert list(slots) == [p.player_id for p in xi] and len(slots) == 11
    assert slots[xi[0].player_id] == (6.0, 50.0) and xi[0].position == "GK"
    assert slots[xi[1].player_id] == (22.0, 16.0) and xi[1].position == "DF"
    assert slots[xi[10].player_id] == (64.0, 60.0) and xi[10].position == "FW"


def test_formation_target_shifts_with_the_ball_and_possession():
    assert formation_target((42.0, 38.0), False, (80.0, 70.0), True) == (42 + 9 + 7, 38 + 5)
    assert formation_target((42.0, 38.0), False, (80.0, 70.0), False) == (42 + 9 - 7, 38 + 5)
    assert formation_target((6.0, 50.0), True, (100.0, 50.0), False) == (9.0, 50.0)
    assert formation_target((6.0, 50.0), True, (10.0, 0.0), True) == (6.0, 42.5)
    assert formation_target((64.0, 60.0), False, (100.0, 100.0), True) == (64 + 15 + 7, 72.5)
    assert formation_target((22.0, 84.0), False, (100.0, 100.0), True) == (44.0, 96.5)
    assert formation_target((22.0, 16.0), False, (0.0, 0.0), False) == (2.0, 3.5)


def test_frames_are_on_the_grid_and_bounded(tracker11):
    frames = tracker11.frames(10, 12.6)
    expected = [10.0, 10.25, 10.5, 10.75, 11.0, 11.25, 11.5, 11.75, 12.0, 12.25, 12.5]
    assert [f.t for f in frames] == expected
    capped = tracker11.frames(0, 1000)
    assert len(capped) == MAX_FRAMES and capped[-1].t == 149.75
    assert tracker11.frames(tracker11.end_t + 1, tracker11.end_t + 50) == []
    tail = tracker11.frames(tracker11.end_t - 1, tracker11.end_t + 50)
    assert tail and tail[-1].t <= tracker11.end_t
    assert tracker11.frames(0.1, 0.2) == []
    assert tracker11.frames(5, 5)[0].t == 5.0


def test_same_seed_same_frames_and_seeds_differ(match11):
    a = MatchTracker(match11.meta, match11.events).frames(0, 150)
    b = MatchTracker.for_match(match11.meta).frames(0, 150)
    assert a == b
    assert MatchTracker.for_match(simulate(5).meta).frames(0, 150) != a


def test_for_match_replays_the_same_events(match11):
    tracker = MatchTracker.for_match(match11.meta)
    assert tracker.events == match11.events
    assert tracker.end_t == match11.events[-1].t


def test_frame_holds_22_players_and_the_ball_on_the_pitch(tracker11, match11):
    frame = tracker11.frames(300, 300)[0]
    xi = {p.player_id for t in (match11.meta.home, match11.meta.away) for p in starting_xi(t)}
    assert len(frame.players) == 22 and set(frame.players) == xi
    assert all(0 <= x <= 100 and 0 <= y <= 100 for x, y in frame.players.values())
    assert frame.ball == pytest.approx(tracker11.ball_at(300.0), abs=0.01)
    home = {pid for pid in frame.players if pid.startswith(match11.meta.home.team_id)}
    # The home side defends the left goal: its keeper stays on the left all match long.
    keeper = starting_xi(match11.meta.home)[0].player_id
    assert keeper in home and frame.players[keeper][0] < 15
    away_keeper = starting_xi(match11.meta.away)[0].player_id
    assert frame.players[away_keeper][0] > 85


def test_nobody_moves_faster_than_the_cap(tracker11):
    frames = tracker11.frames(0, 150) + tracker11.frames(3600, 3750)
    checked = 0
    for a, b in zip(frames, frames[1:], strict=False):
        if round(b.t - a.t, 6) != 0.25:
            continue
        for pid, xy in b.players.items():
            if pid in a.players:
                checked += 1
                assert _moved_m(a.players[pid], xy) <= STEP_M + 0.02, (pid, a.t)
    assert checked > 20000


def test_player_reaches_the_pass_before_the_ball_leaves(tracker11, placed11):
    # A pass after the first minute: the passer stands at its start when the ball leaves.
    p = next(p for p in placed11 if p.event.type == "pass" and p.event.t > 60 and p.event.player_id)
    leave = p.event.t - travel_seconds(p)
    t = math.ceil(leave * FPS) / FPS
    frame = tracker11.frames(t, t)[0]
    assert _moved_m(frame.players[p.event.player_id], p.start) < 3.0


def test_substitution_and_red_card_change_the_roster(match11):
    sub = next(e for e in match11.events if e.type == "substitution")
    out, inc = sub.meta["player_out"], sub.meta["player_in"]
    tracker = MatchTracker(match11.meta, match11.events)
    before = tracker.frames(sub.t - 0.5, sub.t - 0.25)[0]
    at = tracker.frames(sub.t, sub.t + 5)
    assert out in before.players and inc not in before.players
    assert out not in at[0].players and inc in at[0].players
    assert at[0].players[inc] == pytest.approx((50.0, 0.0), abs=STEP_M / 0.68 + 0.01)
    assert len(at[-1].players) == 22
    events = [
        e.model_copy(update={"subtype": "red"}) if e.type == "card" else e for e in match11.events
    ]
    first_red = next(e for e in events if e.type == "card")
    red = MatchTracker(match11.meta, events)
    t = math.ceil((first_red.t + 1) * FPS) / FPS
    frame = red.frames(t, t)[0]
    assert first_red.player_id not in frame.players and len(frame.players) == 21


def test_frames_window_after_a_long_skip(match11):
    tracker = MatchTracker(match11.meta, match11.events)
    t0 = time.perf_counter()
    frames = tracker.frames(5000, 5010)
    first = time.perf_counter() - t0
    t0 = time.perf_counter()
    again = tracker.frames(5000, 5010)
    assert again == frames and len(frames) == 41
    assert time.perf_counter() - t0 < first / 5
