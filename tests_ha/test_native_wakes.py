"""Native wake schedules: the frame's clock, its wakes, and missed ones."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Generator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.fraimic import native_wakes
from custom_components.fraimic.api import (
    FraimicApiError,
    FraimicClient,
    FraimicConnectionError,
)
from custom_components.fraimic.const import DOMAIN
from custom_components.fraimic.wake_schedule import DAYS, WakeSchedule

from .conftest import FRAME_INFO, setup_entry

# 18:00 in Oslo; the frame keeps the EST5EDT fallback (UTC-05:00).
NOW = "2026-11-10T17:00:00+00:00"
EST_FRAME = {
    **FRAME_INFO,
    "firmware_version": "0.2.31",
    "time_synced": True,
    "local_time": "2026-11-10T12:00:00",
}
FIRST_WAKE = datetime(2026, 11, 11, 6, tzinfo=UTC)  # 07:00 Oslo, 01:00 EST


@pytest.fixture
def frame(frame_client: dict[str, AsyncMock]) -> Generator[dict[str, AsyncMock]]:
    """A 0.2.31 frame whose schedule starts off, as Large's did."""
    frame_client["get_info"].return_value = dict(EST_FRAME)
    state: dict[str, Any] = {
        "enabled": False,
        "times": [],
        "interval_minutes": None,
        "weekdays": list(DAYS),
        "max_idle": 120,
        "time_valid": True,
        "next_wakes": [],
    }

    def post(payload: dict[str, Any]) -> dict[str, Any]:
        state.update(payload)
        if "times" in payload:
            state["interval_minutes"] = None
        state["next_wakes"] = (
            ["2026-11-11T01:00:00-05:00", "2026-11-12T01:00:00-05:00"]
            if state["enabled"]
            else []
        )
        return dict(state)

    mocks = {
        "get_wake_schedule": AsyncMock(side_effect=lambda: dict(state)),
        "set_wake_schedule": AsyncMock(side_effect=post),
        "sleep": AsyncMock(return_value={"status": "sleeping"}),
    }
    with patch.multiple(FraimicClient, **mocks):
        yield {**frame_client, **mocks}


async def _until(hass: HomeAssistant, done: Callable[[], bool]) -> None:
    """Run the loop until ``done``; the integration's own workers never finish."""
    for _ in range(500):
        await hass.async_block_till_done()
        if done():
            return
        await asyncio.sleep(0)
    raise AssertionError("never settled")


async def _set_up(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, entry: MockConfigEntry
) -> native_wakes.NativeWakes:
    await hass.config.async_set_time_zone("Europe/Oslo")
    freezer.move_to(NOW)
    await setup_entry(hass, entry)
    wakes = entry.runtime_data.wakes
    await _until(hass, lambda: wakes.supported is not None)
    assert wakes.supported is True
    await wakes.async_set_schedule(WakeSchedule.from_dict({"times": ["07:00"]}))
    return wakes


async def _reach(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    wakes: native_wakes.NativeWakes,
    when: datetime,
) -> None:
    """Move to ``when`` and run the wake caught there to its end."""
    before = wakes.last_wake
    freezer.move_to(when)
    async_fire_time_changed(hass, when)
    await _until(hass, lambda: wakes.last_wake is not before and not wakes._catching)


async def test_schedule_lands_on_the_frames_clock_and_its_wake_is_caught(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    frame: dict[str, AsyncMock],
    config_entry: MockConfigEntry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(native_wakes, "IDLE_SECONDS", 0)
    monkeypatch.setattr(native_wakes, "PROBE_EVERY", 0)
    wakes = await _set_up(hass, freezer, config_entry)

    # 07:00 in Oslo is 01:00 on the frame's clock.
    frame["set_wake_schedule"].assert_awaited_once_with(
        {"enabled": True, "times": ["01:00"], "weekdays": list(DAYS), "max_idle": 120}
    )
    assert not wakes.dirty
    assert wakes.next_wake == FIRST_WAKE
    assert wakes.slots(dt_util.utcnow(), 1) == [FIRST_WAKE]
    assert wakes.next_change(dt_util.utcnow()) == FIRST_WAKE - timedelta(seconds=30)

    await _reach(hass, freezer, wakes, FIRST_WAKE - timedelta(seconds=30))

    frame["sleep"].assert_awaited_once()
    assert wakes.last_wake is not None and wakes.last_wake["outcome"] == "answered"
    assert wakes.next_wake == FIRST_WAKE + timedelta(days=1)
    # Already in sync: the wake only reads the schedule.
    frame["set_wake_schedule"].assert_awaited_once()


async def test_missed_wakes_raise_a_repair(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    frame: dict[str, AsyncMock],
    config_entry: MockConfigEntry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(native_wakes, "PROBE_EVERY", 0)
    wakes = await _set_up(hass, freezer, config_entry)

    def asleep(**_kwargs: Any) -> dict[str, Any]:
        freezer.tick(10)
        raise FraimicConnectionError("asleep")

    frame["get_battery"].side_effect = asleep
    issue_id = f"wake_missed_{config_entry.entry_id}"
    await _reach(hass, freezer, wakes, FIRST_WAKE - timedelta(seconds=30))
    assert wakes.misses == 1
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None

    await _reach(hass, freezer, wakes, FIRST_WAKE + timedelta(days=1, seconds=-30))
    assert wakes.misses == 2
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is not None
    frame["sleep"].assert_not_awaited()


async def test_older_firmware_keeps_the_queue_interval(
    hass: HomeAssistant,
    frame: dict[str, AsyncMock],
    config_entry: MockConfigEntry,
) -> None:
    frame["get_wake_schedule"].side_effect = FraimicApiError("not found", status=404)
    await setup_entry(hass, config_entry)
    wakes = config_entry.runtime_data.wakes
    await _until(hass, lambda: wakes.supported is not None)

    assert wakes.supported is False
    assert not wakes.active
    with pytest.raises(HomeAssistantError):
        await wakes.async_set_schedule(WakeSchedule.from_dict({"times": ["07:00"]}))


async def test_a_window_closed_before_sleep_still_counts_as_asleep(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    frame: dict[str, AsyncMock],
    config_entry: MockConfigEntry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(native_wakes, "IDLE_SECONDS", 0)
    monkeypatch.setattr(native_wakes, "PROBE_EVERY", 0)
    wakes = await _set_up(hass, freezer, config_entry)
    # Large's render outlasts the 120 s window, so the frame is gone by then.
    frame["sleep"].side_effect = FraimicConnectionError("asleep")

    await _reach(hass, freezer, wakes, FIRST_WAKE - timedelta(seconds=30))

    assert wakes.last_wake is not None and wakes.last_wake["outcome"] == "answered"
    assert config_entry.runtime_data.coordinator.frame_online is False
