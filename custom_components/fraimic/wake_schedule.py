"""Native wake schedules (``/api/wake-schedule``, firmware 0.2.31+).

The frame wakes by itself at up to four daily times, or every N minutes
counted from its own midnight, on chosen weekdays, and stays reachable for
``max_idle`` seconds. Its times are in the frame's stored POSIX zone, which is
often not Home Assistant's (``EST5EDT`` fallback, no LAN setter), so a
schedule picked in Home Assistant's zone is shifted onto the frame's clock.

HA-free so the conversions are unit-testable.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta, timezone, tzinfo
from itertools import count as count_from
from itertools import islice
from typing import Any

# Minutes; the firmware only accepts intervals that divide a day.
INTERVALS = (60, 90, 120, 180, 240, 360, 480, 720, 1440)
MAX_TIMES = 4
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
ALL_DAYS = frozenset(range(7))
# Seconds the frame stays reachable after each wake (firmware default).
MAX_IDLE = 120
DAY = 1440

_TIME = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


class WakeScheduleError(ValueError):
    """A schedule the frame cannot store."""


@dataclass(frozen=True)
class WakeSchedule:
    """Daily times or an interval, on some weekdays, on one wall clock."""

    times: tuple[time, ...] = ()
    interval: int | None = None  # minutes
    days: frozenset[int] = ALL_DAYS

    def __post_init__(self) -> None:
        if bool(self.times) == (self.interval is not None):
            raise WakeScheduleError("set either times or an interval")
        if len(self.times) > MAX_TIMES:
            raise WakeScheduleError(f"at most {MAX_TIMES} times")
        if len(set(self.times)) != len(self.times):
            raise WakeScheduleError("times must differ")
        if any(value.second or value.microsecond for value in self.times):
            raise WakeScheduleError("times are whole minutes")
        if self.interval is not None and self.interval not in INTERVALS:
            raise WakeScheduleError(
                "interval must be one of " + ", ".join(map(str, INTERVALS)) + " minutes"
            )
        if not self.days or not self.days <= ALL_DAYS:
            raise WakeScheduleError("pick at least one weekday")

    @classmethod
    def from_dict(cls, data: Any) -> WakeSchedule:
        """Parse ``{"times": [...]}`` or ``{"interval": N}``, plus ``days``."""
        if not isinstance(data, dict):
            raise WakeScheduleError("schedule must be an object")
        times = data.get("times") or ()
        interval = data.get("interval")
        if isinstance(interval, bool) or (
            interval is not None and not isinstance(interval, int)
        ):
            raise WakeScheduleError("interval must be whole minutes")
        days = data.get("days")
        return cls(
            times=tuple(sorted(_parse_time(value) for value in times)),
            interval=interval,
            days=ALL_DAYS if days is None else _parse_days(days),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "times": [value.strftime("%H:%M") for value in self.times],
            "interval": self.interval,
            "days": [DAYS[day] for day in sorted(self.days)],
        }

    @classmethod
    def from_frame(cls, state: Any) -> WakeSchedule | None:
        """The schedule a frame reports, or None when it is off or unreadable."""
        if not isinstance(state, dict) or state.get("enabled") is not True:
            return None
        try:
            return cls(
                times=tuple(sorted(_parse_time(value) for value in state.get("times") or ())),
                interval=state.get("interval_minutes") or None,
                days=_parse_days(state.get("weekdays") or DAYS),
            )
        except WakeScheduleError:
            return None

    def frame_payload(self) -> dict[str, Any]:
        """``POST /api/wake-schedule`` body; every field, so nothing is inherited."""
        payload: dict[str, Any] = {
            "enabled": True,
            "weekdays": [DAYS[day] for day in sorted(self.days)],
            "max_idle": MAX_IDLE,
        }
        if self.interval is not None:
            payload["interval_minutes"] = self.interval
        else:
            payload["times"] = [value.strftime("%H:%M") for value in self.times]
        return payload

    def shifted(self, minutes: int) -> WakeSchedule:
        """The same wakes on a wall clock ``minutes`` ahead of this one.

        Weekdays become every day a wake lands on, so the frame can wake on a
        day the original skips; ``art_slots`` leaves those out. An interval
        keeps counting from the shifted clock's midnight, as the frame does.
        """
        if self.interval is not None:
            spread = {0} if minutes % DAY == 0 else {minutes // DAY, (minutes + DAY - 1) // DAY}
            return WakeSchedule(interval=self.interval, days=_move(self.days, spread))
        moved = [(value.hour * 60 + value.minute + minutes) for value in self.times]
        return WakeSchedule(
            times=tuple(sorted(time(*divmod(value % DAY, 60)) for value in moved)),
            days=_move(self.days, {value // DAY for value in moved}),
        )

    def wakes(self, after: datetime, count: int) -> list[datetime]:
        """The next ``count`` wakes strictly after ``after``, on its clock."""
        upcoming = (wake for wake in self.iter_wakes(after) if wake > after)
        return list(islice(upcoming, count))

    def iter_wakes(self, after: datetime) -> Iterator[datetime]:
        """Wakes from the day before ``after`` on, on ``after``'s clock."""
        zone = after.tzinfo or UTC
        start = after.date() - timedelta(days=1)
        for offset in count_from(0):
            day = start + timedelta(days=offset)
            if day.weekday() not in self.days:
                continue
            if self.interval is not None:
                midnight = datetime.combine(day, time(), zone)
                for step in range(DAY // self.interval):
                    yield midnight + timedelta(minutes=step * self.interval)
            else:
                for value in self.times:
                    yield datetime.combine(day, value, zone)

    @property
    def wakes_per_week(self) -> int:
        per_day = len(self.times) if self.interval is None else DAY // self.interval
        return per_day * len(self.days)


def art_slots(
    schedule: WakeSchedule,
    after: datetime,
    count: int,
    *,
    zone: tzinfo,
    frame_offset: int,
) -> list[datetime]:
    """When art changes: the frame's wakes for ``schedule`` that keep its weekdays.

    ``schedule`` is on ``zone``'s clock; ``frame_offset`` (minutes from UTC)
    is the frame's current one. Times are exact on ``zone``'s clock; intervals
    follow the frame's grid, which counts from its own midnight.
    """
    if schedule.interval is None:
        slots = schedule.wakes(after.astimezone(zone), count)
        return [slot.astimezone(UTC) for slot in slots]
    frame_zone = timezone(timedelta(minutes=frame_offset))
    local_offset = after.astimezone(zone).utcoffset() or timedelta()
    shift = frame_offset - int(local_offset.total_seconds() // 60)
    # The shifted days are a superset, so the original days always turn up.
    kept = (
        wake.astimezone(UTC)
        for wake in schedule.shifted(shift).iter_wakes(after.astimezone(frame_zone))
        if wake > after and wake.astimezone(zone).weekday() in schedule.days
    )
    return list(islice(kept, count))


def frame_wakes(state: Any) -> list[datetime]:
    """The frame's own ``next_wakes`` (it applies its DST rules), as UTC."""
    wakes: list[datetime] = []
    if not isinstance(state, dict):
        return wakes
    for value in state.get("next_wakes") or ():
        try:
            parsed = datetime.fromisoformat(value)
        except (TypeError, ValueError):
            continue
        if parsed.tzinfo is not None:
            wakes.append(parsed.astimezone(UTC))
    return sorted(wakes)


def frame_offset(state: Any) -> int | None:
    """The frame's UTC offset in minutes, from its first ``next_wakes`` entry."""
    if not isinstance(state, dict):
        return None
    for value in state.get("next_wakes") or ():
        try:
            offset = datetime.fromisoformat(value).utcoffset()
        except (TypeError, ValueError):
            continue
        if offset is not None:
            return int(offset.total_seconds() // 60)
    return None


def matches(state: Any, payload: dict[str, Any]) -> bool:
    """Whether a frame's reported schedule already is ``payload``."""
    if not isinstance(state, dict):
        return False
    if payload.get("enabled") is not True:
        return state.get("enabled") is False
    want = WakeSchedule.from_frame(payload)
    return (
        want is not None
        and WakeSchedule.from_frame(state) == want
        and state.get("max_idle") == payload.get("max_idle")
    )


def _parse_time(value: Any) -> time:
    if not isinstance(value, str) or not (match := _TIME.match(value)):
        raise WakeScheduleError(f"{value!r} is not HH:MM")
    return time(int(match[1]), int(match[2]))


def _parse_days(values: Any) -> frozenset[int]:
    if isinstance(values, str) or not isinstance(values, Iterable):
        raise WakeScheduleError("days must be a list")
    days: set[int] = set()
    for value in values:
        if value not in DAYS:
            raise WakeScheduleError(f"unknown weekday {value!r}")
        days.add(DAYS.index(value))
    return frozenset(days)


def _move(days: frozenset[int], deltas: set[int]) -> frozenset[int]:
    return frozenset((day + delta) % 7 for day in days for delta in deltas)
