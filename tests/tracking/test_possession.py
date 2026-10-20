import math

from bts.sim.models import Event, Point
from bts.tracking.possession import frame_team, possession_after, to_screen


def _event(type_, team, x, y, outcome=None, end=None, t=1.0):
    return Event(
        event_id=1,
        match_id="m",
        period=1,
        t=t,
        clock="00:01",
        team_id=team,
        type=type_,
        start=Point(x=x, y=y),
        end=Point(x=end[0], y=end[1]) if end else None,
        outcome=outcome,
    )


def test_possession_after_each_type():
    h, a = "t1", "t2"
    assert possession_after(_event("pass", a, 1, 1, "fail"), h, h, a) == a
    assert possession_after(_event("carry", a, 1, 1, "success"), h, h, a) == a
    assert possession_after(_event("ball_out", a, 1, 1, "fail"), a, h, a) == h
    assert possession_after(_event("miscontrol", h, 1, 1, "fail"), h, h, a) == a
    assert possession_after(_event("shot", h, 90, 50, "off_target"), h, h, a) == a
    assert possession_after(_event("shot", h, 90, 50, "goal"), h, h, a) == a
    assert possession_after(_event("shot", h, 90, 50, "saved"), h, h, a) == h
    assert possession_after(_event("shot", h, 90, 50, "blocked"), h, h, a) == h
    assert possession_after(_event("goalkeeper", a, 97, 50, "success"), h, h, a) == a
    assert possession_after(_event("interception", a, 60, 60, "success"), h, h, a) == a
    assert possession_after(_event("recovery", a, 60, 60, "success"), h, h, a) == a
    assert possession_after(_event("clearance", a, 60, 60, "success"), h, h, a) == a
    assert possession_after(_event("duel", a, 60, 60, "success"), h, h, a) == a
    assert possession_after(_event("duel", a, 60, 60, "fail"), h, h, a) == h
    for type_ in ("pressure", "foul", "card", "substitution", "period_end"):
        assert possession_after(_event(type_, a, 60, 60), h, h, a) == h, type_
    assert possession_after(_event("period_start", a, 50, 50), h, h, a) == a


def test_frame_team_and_screen_mapping():
    assert frame_team(_event("pass", "t2", 1, 1), "t1") == "t2"
    assert frame_team(_event("interception", "t2", 1, 1), "t1") == "t1"
    assert frame_team(_event("pressure", "t1", 1, 1), "t2") == "t2"
    assert to_screen(Point(x=90, y=20), "t1", "t1") == (90.0, 20.0)
    assert to_screen(Point(x=90, y=20), "t2", "t1") == (10.0, 80.0)


def test_place_events_keeps_the_ball_continuous(match11, placed11):
    # The ball only jumps after a goal, an off-target shot, a clearance or at a kick-off: the
    # simulator restarts play elsewhere in those cases and nowhere else.
    prev = None
    for p in placed11:
        if p.start is None:
            continue
        if prev is not None and prev.end_or_start is not None:
            d = math.dist(prev.end_or_start, p.start)
            if d > 8 and p.event.type != "period_start":
                ids = (prev.event.event_id, p.event.event_id, d)
                assert prev.event.type in ("shot", "clearance"), ids
                assert prev.event.type != "shot" or prev.event.outcome in ("goal", "off_target")
        prev = p
    assert len(placed11) == len(match11.events)
    assert all(p.event is e for p, e in zip(placed11, match11.events, strict=True))
    sub = next(p for p in placed11 if p.event.type == "substitution")
    assert sub.start is None and sub.end is None and sub.end_or_start is None
    kickoff = placed11[0]
    assert kickoff.event.type == "period_start" and kickoff.start == (50.0, 50.0)
    assert kickoff.holder_after == match11.meta.home.team_id
    blocked = next(p for p in placed11 if p.event.type == "shot" and p.event.outcome == "blocked")
    assert blocked.end is None and blocked.end_or_start == blocked.start
    save = next(p for p in placed11 if p.event.type == "goalkeeper")
    assert save.team != save.event.team_id  # the shooter's frame, not the keeper's
