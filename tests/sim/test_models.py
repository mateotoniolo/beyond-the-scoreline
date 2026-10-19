import pytest
from pydantic import ValidationError

from bts.sim.models import Event, Point, clock_str


def test_point_rejects_out_of_range():
    with pytest.raises(ValidationError):
        Point(x=101, y=0)


def test_event_round_trips_json():
    e = Event(
        event_id=1,
        match_id="m",
        period=1,
        t=12.5,
        clock="00:12",
        team_id="h",
        player_id="h7",
        type="pass",
        subtype="short",
        start=Point(x=10, y=50),
        end=Point(x=20, y=55),
        outcome="success",
        tags=["under_pressure"],
        meta={"pass_distance": 11.2},
    )
    assert Event.model_validate_json(e.model_dump_json()) == e


def test_clock_str():
    assert clock_str(0) == "00:00" and clock_str(5425) == "90:25"
