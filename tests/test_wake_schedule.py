"""Native wake schedule model: validation, frame payloads and time-zone shifts."""

from __future__ import annotations

from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

import pytest

from conftest import load

ws = load("wake_schedule")
OSLO = ZoneInfo("Europe/Oslo")
# Large's reply on firmware 0.2.31 (EST5EDT fallback zone).
FRAME_TIMES = {
    "enabled": True,
    "times": ["23:30", "01:15"],
    "interval_minutes": None,
    "weekdays": ["mon", "wed"],
    "max_idle": 120,
    "time_valid": True,
    "next_wakes": [
        "2026-11-11T01:15:00-05:00",
        "2026-11-11T23:30:00-05:00",
        "2026-11-16T01:15:00-05:00",
    ],
}


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"times": ["07:00"], "interval": 60},
        {"times": ["7:00"]},
        {"times": ["07:00", "08:00", "09:00", "10:00", "11:00"]},
        {"times": ["07:00", "07:00"]},
        {"interval": 100},
        {"interval": True},
        {"times": ["07:00"], "days": []},
        {"times": ["07:00"], "days": ["Mon"]},
    ],
)
def test_rejects_what_the_frame_cannot_store(data):
    with pytest.raises(ws.WakeScheduleError):
        ws.WakeSchedule.from_dict(data)


def test_round_trips_and_builds_a_complete_frame_payload():
    schedule = ws.WakeSchedule.from_dict({"times": ["19:00", "07:00"], "days": ["fri", "mon"]})
    assert schedule.to_dict() == {"times": ["07:00", "19:00"], "interval": None, "days": ["mon", "fri"]}
    assert ws.WakeSchedule.from_dict(schedule.to_dict()) == schedule
    assert schedule.frame_payload() == {
        "enabled": True,
        "times": ["07:00", "19:00"],
        "weekdays": ["mon", "fri"],
        "max_idle": 120,
    }
    assert ws.WakeSchedule(interval=360).frame_payload()["interval_minutes"] == 360
    assert schedule.wakes_per_week == 4


def test_reads_the_frames_reply():
    schedule = ws.WakeSchedule.from_frame(FRAME_TIMES)
    assert schedule == ws.WakeSchedule(times=(time(1, 15), time(23, 30)), days=frozenset({0, 2}))
    assert ws.WakeSchedule.from_frame({**FRAME_TIMES, "enabled": False}) is None
    assert ws.frame_offset(FRAME_TIMES) == -300
    assert ws.frame_wakes(FRAME_TIMES)[0] == datetime(2026, 11, 11, 6, 15, tzinfo=UTC)
    assert ws.matches(FRAME_TIMES, schedule.frame_payload())
    assert not ws.matches(FRAME_TIMES, ws.WakeSchedule(times=(time(1, 15),)).frame_payload())
    assert ws.matches({**FRAME_TIMES, "enabled": False}, {"enabled": False})
    assert not ws.matches(FRAME_TIMES, {"enabled": False})


def test_times_move_onto_the_frames_clock_with_their_weekdays():
    # Oslo (UTC+1) to a frame on EST (UTC-5): six hours back.
    morning = ws.WakeSchedule.from_dict({"times": ["07:00"], "days": ["mon", "fri"]})
    assert morning.shifted(-360) == ws.WakeSchedule(times=(time(1, 0),), days=frozenset({0, 4}))
    night = ws.WakeSchedule.from_dict({"times": ["03:00"], "days": ["mon"]})
    assert night.shifted(-360) == ws.WakeSchedule(times=(time(21, 0),), days=frozenset({6}))
    # Times landing on different days need both days on the frame.
    mixed = ws.WakeSchedule.from_dict({"times": ["03:00", "19:00"], "days": ["mon"]})
    assert mixed.shifted(-360).days == frozenset({6, 0})
    weekly = ws.WakeSchedule(interval=240, days=frozenset({0}))
    assert weekly.shifted(-360).days == frozenset({6, 0})
    assert weekly.shifted(0) == weekly


def test_set_times_keep_the_wall_clock_across_daylight_saving():
    schedule = ws.WakeSchedule.from_dict({"times": ["07:00"]})
    after = datetime(2026, 10, 24, 12, tzinfo=UTC)
    slots = ws.art_slots(schedule, after, 2, zone=OSLO, frame_offset=-240)
    # Summer time ends early on the 25th: 07:00 is 05:00 UTC before, 06:00 after.
    assert slots == [
        datetime(2026, 10, 25, 6, tzinfo=UTC),
        datetime(2026, 10, 26, 6, tzinfo=UTC),
    ]
    before = ws.art_slots(schedule, datetime(2026, 10, 23, 12, tzinfo=UTC), 1, zone=OSLO, frame_offset=-240)
    assert before == [datetime(2026, 10, 24, 5, tzinfo=UTC)]


def test_intervals_follow_the_frames_grid_on_the_chosen_days():
    # Every 4 h counted from the frame's (EST) midnight lands at 02, 06, ... in Oslo.
    schedule = ws.WakeSchedule(interval=240, days=frozenset({0}))
    after = datetime(2026, 11, 15, 12, tzinfo=UTC)  # Sunday
    slots = ws.art_slots(schedule, after, 7, zone=OSLO, frame_offset=-300)
    local = [slot.astimezone(OSLO) for slot in slots]
    assert [slot.hour for slot in local] == [2, 6, 10, 14, 18, 22, 2]
    assert {slot.weekday() for slot in local} == {0}
    assert local[0].date().isoformat() == "2026-11-16"
