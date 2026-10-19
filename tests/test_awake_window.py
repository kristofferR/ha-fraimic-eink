"""Awake windows: wake a sleeping Hybrid frame, restart it awake, sleep after."""

import asyncio
import copy
import sys
import types
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from conftest import load

NOW = 1_800_000_000.0


@pytest.fixture
def awake(monkeypatch):
    if "aiohttp" not in sys.modules:
        stub = types.ModuleType("aiohttp")
        stub.ClientError = Exception
        stub.ClientSession = object
        stub.ClientTimeout = lambda **_kwargs: None
        stub.FormData = object
        monkeypatch.setitem(sys.modules, "aiohttp", stub)
    saved: dict = {}
    timers: list = []

    class Store:
        def __init__(self, _hass, _version, key):
            self.key = key

        async def async_load(self):
            return copy.deepcopy(saved.get(self.key))

        async def async_save(self, value):
            saved[self.key] = copy.deepcopy(value)

    def track(_hass, action, when):
        timers.append((when.timestamp(), action))
        return Mock()

    modules = {
        "homeassistant": types.ModuleType("homeassistant"),
        "homeassistant.core": types.ModuleType("homeassistant.core"),
        "homeassistant.helpers": types.ModuleType("homeassistant.helpers"),
        "homeassistant.helpers.event": types.ModuleType("homeassistant.helpers.event"),
        "homeassistant.helpers.storage": types.ModuleType("homeassistant.helpers.storage"),
        "homeassistant.util": types.ModuleType("homeassistant.util"),
        "homeassistant.util.dt": types.ModuleType("homeassistant.util.dt"),
        "fraimic.coordinator": types.ModuleType("fraimic.coordinator"),
    }
    modules["homeassistant.core"].callback = lambda func: func
    modules["homeassistant.core"].HomeAssistant = object
    modules["homeassistant.helpers.event"].async_track_point_in_utc_time = track
    modules["homeassistant.helpers.storage"].Store = Store
    dt = modules["homeassistant.util.dt"]
    dt.as_utc = lambda value: value
    dt.utc_from_timestamp = lambda ts: datetime.fromtimestamp(ts, UTC)
    modules["fraimic.coordinator"].normalize_info = lambda raw: {
        "device": {"uptime_s": raw["uptime"]}
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    load("const")  # registers the synthetic package before the stub child
    monkeypatch.delitem(sys.modules, "fraimic.awake_window", raising=False)
    module = load("awake_window")

    clock = SimpleNamespace(now=NOW)
    monkeypatch.setattr(module.time, "time", lambda: clock.now)
    real_sleep = asyncio.sleep

    async def sleep(seconds):
        clock.now += seconds
        await real_sleep(0)

    monkeypatch.setattr(module.asyncio, "sleep", sleep)

    async def plan(wake_at):
        cloud.wake_at = wake_at
        return cloud.has_image

    cloud = SimpleNamespace(
        wake_at=None,
        has_image=True,
        async_set_keep_awake=AsyncMock(),
        async_deliver=AsyncMock(),
    )
    cloud.async_plan_wake = AsyncMock(side_effect=plan)
    runtime = SimpleNamespace(
        cloud=cloud,
        client=SimpleNamespace(get_info=AsyncMock(), restart=AsyncMock()),
        upload_lock=asyncio.Lock(),
        coordinator=SimpleNamespace(async_set_frame_online=Mock()),
        temporary_overlays=SimpleNamespace(base=(b"bin", b"png", "none"), title="Art"),
    )
    entry = SimpleNamespace(
        entry_id="large",
        title="Large",
        runtime_data=runtime,
        async_create_background_task=lambda _hass, coro, _name: asyncio.ensure_future(coro),
    )
    return SimpleNamespace(
        module=module, window=module.AwakeWindow(None, entry), cloud=cloud,
        client=runtime.client, clock=clock, timers=timers,
    )


def at(ts):
    return datetime.fromtimestamp(ts, UTC)


async def settle():
    for _ in range(200):
        await asyncio.sleep(0)


def test_future_window_lets_the_frame_sleep_until_its_wake(awake):
    m = awake.module
    start = NOW + 8 * 3600

    async def run():
        await awake.window.async_set(at(start), at(start + 3 * 3600))

    asyncio.run(run())
    awake.cloud.async_set_keep_awake.assert_awaited_once_with(False)
    awake.cloud.async_plan_wake.assert_awaited_once_with(start - m.WAKE_LEAD)
    assert [when for when, _ in awake.timers] == [
        start - m.WAKE_LEAD - m.PREPARE, start + 3 * 3600,
    ]


def test_timer_wake_is_restarted_once_into_a_normal_boot(awake):
    m = awake.module
    awake.client.get_info.side_effect = [
        m.FraimicError("asleep"),
        {"uptime": 5},  # the album wake
        m.FraimicError("rebooting"),
        {"uptime": 25},  # the normal boot that honours keep-awake
    ]
    start = NOW + m.WAKE_LEAD + 60

    async def run():
        await awake.window.async_set(at(start), at(start + 5400))
        await settle()
        # The dashboard re-sets the window once it starts: no second restart.
        await awake.window.async_set(at(awake.clock.now), at(awake.clock.now + 5700))
        await settle()

    asyncio.run(run())
    awake.client.restart.assert_awaited_once()
    assert awake.window.awake and awake.window.last_result == "restarted"
    awake.cloud.async_set_keep_awake.assert_awaited_with(True)
    assert awake.client.get_info.await_count == 4


def test_an_already_awake_frame_is_not_restarted(awake):
    awake.client.get_info.return_value = {"uptime": 50_000}

    async def run():
        await awake.window.async_set(at(NOW), at(NOW + 3600))
        await settle()

    asyncio.run(run())
    awake.client.restart.assert_not_awaited()
    assert awake.window.last_result == "already_awake"


@pytest.mark.parametrize("has_image", [True, False])
def test_window_end_sleeps_the_frame_with_a_heartbeat_wake(awake, has_image):
    m = awake.module
    awake.cloud.has_image = has_image
    awake.client.get_info.return_value = {"uptime": 50_000}

    async def run():
        await awake.window.async_set(at(NOW), at(NOW + 3600))
        await settle()
        await awake.window.async_clear()

    asyncio.run(run())
    awake.cloud.async_set_keep_awake.assert_awaited_with(False)
    awake.cloud.async_plan_wake.assert_awaited_with(NOW + m.HEARTBEAT)
    # Without a pending image, the art on the glass carries the wake.
    assert awake.cloud.async_deliver.await_count == (0 if has_image else 1)
    assert not awake.window.active


def test_heartbeat_moves_on_before_the_frame_wakes_for_it(awake):
    m = awake.module
    awake.client.get_info.return_value = {"uptime": 50_000}

    async def run():
        await awake.window.async_set(at(NOW), at(NOW + 3600))
        await settle()
        await awake.window.async_clear()
        when, fire = awake.timers[-1]
        assert when == NOW + m.HEARTBEAT - m.PREPARE
        awake.clock.now = when
        fire(at(when))
        await settle()

    asyncio.run(run())
    awake.cloud.async_plan_wake.assert_awaited_with(NOW + 2 * m.HEARTBEAT)


def test_daily_window_plans_tomorrow_before_the_frame_sleeps(awake):
    m = awake.module
    awake.client.get_info.return_value = {"uptime": 50_000}
    start, end = NOW, NOW + 3600

    async def run():
        await awake.window.async_set(at(start), at(end), repeat_daily=True)
        await settle()
        when, fire = awake.timers[-1]
        assert when == end
        awake.clock.now = end
        fire(at(end))
        await settle()

    asyncio.run(run())
    awake.cloud.async_set_keep_awake.assert_awaited_with(False)
    awake.cloud.async_plan_wake.assert_awaited_with(start + m.DAY - m.WAKE_LEAD)
    assert awake.window.repeat_daily
    assert (awake.window.start, awake.window.end) == (start + m.DAY, end + m.DAY)
