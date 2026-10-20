"""Awake windows: wake a sleeping Hybrid frame, restart it awake, sleep after."""

import asyncio
import copy
import sys
import types
from datetime import UTC, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo
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

        async def async_remove(self):
            saved.pop(self.key, None)

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
    dt.as_utc = lambda value: value.astimezone(UTC)
    dt.as_local = lambda value: value.astimezone(ZoneInfo("Europe/Oslo"))
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
        cloud.wake_album_id = None if wake_at is None else "wake"

    async def cancel():
        cloud.has_image = False

    cloud = SimpleNamespace(
        device_id="canvas",
        wake_at=None,
        wake_album_id="wake",
        has_image=True,
        last_anchor=None,
        delivery_deadline=None,
        async_set_keep_awake=AsyncMock(),
        async_deliver=AsyncMock(),
        async_cancel_delivery=AsyncMock(side_effect=cancel),
    )
    cloud.async_plan_wake = AsyncMock(side_effect=plan)
    runtime = SimpleNamespace(
        cloud=cloud,
        client=SimpleNamespace(get_info=AsyncMock(), restart=AsyncMock()),
        upload_lock=asyncio.Lock(),
        coordinator=SimpleNamespace(async_set_frame_online=Mock()),
        temporary_overlays=SimpleNamespace(async_cloud_withdrawn=AsyncMock()),
    )
    entry = SimpleNamespace(
        entry_id="large",
        title="Large",
        runtime_data=runtime,
        async_create_background_task=lambda _hass, coro, _name: asyncio.ensure_future(coro),
    )
    return SimpleNamespace(
        module=module, window=module.AwakeWindow(None, entry), cloud=cloud,
        client=runtime.client, clock=clock, timers=timers, runtime=runtime,
        entry=entry, saved=saved,
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
    assert awake.cloud.async_plan_wake.await_args.args[0] == start - m.WAKE_LEAD
    assert [when for when, _ in awake.timers] == [
        start - m.WAKE_LEAD - m.PREPARE,
        start - m.WAKE_LEAD + m.CATCH_WINDOW,  # follow-up if the wake is missed
        start + 3 * 3600,
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
    # Pending art is retired, so the normal boot has nothing to redraw; an
    # overlay that was waiting in the cloud goes over the LAN instead.
    awake.cloud.async_cancel_delivery.assert_awaited()
    awake.runtime.temporary_overlays.async_cloud_withdrawn.assert_awaited_once()
    assert awake.window.awake and awake.window.last_result == "restarted"
    awake.cloud.async_set_keep_awake.assert_awaited_with(True)
    assert awake.client.get_info.await_count == 4


def test_an_already_awake_frame_is_not_restarted(awake):
    awake.client.get_info.return_value = {"uptime": 50_000}
    awake.cloud.has_image = False

    async def run():
        await awake.window.async_set(at(NOW), at(NOW + 3600))
        await settle()

    asyncio.run(run())
    awake.client.restart.assert_not_awaited()
    assert awake.window.last_result == "already_awake"
    # Nothing was waiting in the cloud: no album edit, no resend.
    awake.cloud.async_cancel_delivery.assert_not_awaited()
    awake.runtime.temporary_overlays.async_cloud_withdrawn.assert_not_awaited()


def test_window_end_sleeps_the_frame_with_a_heartbeat_wake(awake):
    m = awake.module
    awake.client.get_info.return_value = {"uptime": 50_000}

    async def run():
        await awake.window.async_set(at(NOW), at(NOW + 3600))
        await settle()
        await awake.window.async_clear()

    asyncio.run(run())
    awake.cloud.async_set_keep_awake.assert_awaited_with(False)
    # Only the empty wake album changes: the awake frame redraws nothing.
    awake.cloud.async_plan_wake.assert_awaited_with(NOW + m.HEARTBEAT)
    awake.cloud.async_deliver.assert_not_awaited()
    assert not awake.window.active and awake.window.resting


def test_heartbeat_moves_on_before_the_frame_wakes_for_it(awake):
    m = awake.module
    awake.client.get_info.return_value = {"uptime": 50_000}

    async def run():
        await awake.window.async_set(at(NOW), at(NOW + 3600))
        await settle()
        await awake.window.async_clear()
        when, fire = awake.timers[-1]
        assert when == NOW + m.HEARTBEAT - m.STEER_LEAD
        awake.clock.now = when
        fire(at(when))
        await settle()

    asyncio.run(run())
    assert awake.cloud.async_plan_wake.await_args.args[0] == NOW + 2 * m.HEARTBEAT


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
    assert awake.cloud.async_plan_wake.await_args.args[0] == start + 86400 - m.WAKE_LEAD
    assert awake.window.repeat_daily
    assert (awake.window.start, awake.window.end) == (start + 86400, end + 86400)


@pytest.mark.parametrize(
    ("after", "wake", "standby", "expected"),
    [
        (0, None, None, 86400),  # heartbeat
        (0, 50_000, None, 50_000),  # sleep straight to the window's wake
        (0, 50_000, 30_000, 30_000),  # sleep until standby
        (0, 200_000, 150_000, 86400),  # never more than a day
        (30_000, 50_000, 30_000, 30_300),  # standby checks
        (49_900, 50_000, 30_000, 50_000),  # the last check is the wake
        (50_000, 50_000, 30_000, 50_300),  # due but not caught: keep checking
    ],
)
def test_following_wake(awake, after, wake, standby, expected):
    assert awake.module.following_wake(after, wake=wake, standby_from=standby) == expected


def test_standby_checks_are_steered_before_the_frame_wakes(awake):
    m = awake.module
    standby, start = NOW + 3600, NOW + 8 * 3600

    async def run():
        await awake.window.async_set(at(start), at(start + 3600), standby_from=at(standby))
        steer = [t for t in awake.timers if t[0] == standby - m.STEER_LEAD]
        assert len(steer) == 1
        awake.clock.now = standby - m.STEER_LEAD
        steer[0][1](at(awake.clock.now))
        await settle()

    asyncio.run(run())
    assert [c.args[0] for c in awake.cloud.async_plan_wake.await_args_list] == [
        standby, standby + m.STANDBY_INTERVAL,
    ]


def test_window_due_soon_still_gets_its_wake_slot(awake):
    m = awake.module
    start = NOW + 10 * 60  # inside WAKE_LEAD + PREPARE, wake 4 minutes ahead

    async def run():
        await awake.window.async_set(at(start), at(start + 3600))

    asyncio.run(run())
    assert awake.cloud.async_plan_wake.await_args.args[0] == start - m.WAKE_LEAD


@pytest.mark.parametrize("failing", ["keep_awake", "retire"])
def test_no_restart_until_keep_awake_is_on_and_the_album_retired(awake, failing):
    m = awake.module
    awake.client.get_info.return_value = {"uptime": 5}
    if failing == "keep_awake":
        awake.cloud.async_set_keep_awake.side_effect = m.FraimicCloudError("down")
    else:
        awake.cloud.async_cancel_delivery.side_effect = m.FraimicCloudError("down")

    async def run():
        await awake.window.async_set(at(NOW), at(NOW + 120))
        await settle()

    asyncio.run(run())
    awake.client.restart.assert_not_awaited()
    assert not awake.window.awake


def test_frame_keeps_keep_awake_until_a_wake_can_be_armed(awake):
    m = awake.module
    awake.cloud.async_plan_wake.side_effect = m.FraimicCloudError("down")
    start = NOW + 8 * 3600

    async def run():
        await awake.window.async_set(at(start), at(start + 3600))

    asyncio.run(run())
    awake.cloud.async_set_keep_awake.assert_not_awaited()
    assert not awake.window.resting
    assert (NOW + m.RETRY) in [when for when, _ in awake.timers]


def test_daily_window_keeps_its_local_time_across_dst(awake):
    oslo = ZoneInfo("Europe/Oslo")
    # Norway leaves summer time on Sunday 25 October 2026.
    start = datetime(2026, 10, 24, 7, 0, tzinfo=oslo)
    end = datetime(2026, 10, 24, 9, 0, tzinfo=oslo)
    awake.clock.now = end.timestamp()

    async def run():
        awake.window.start, awake.window.end = start.timestamp(), end.timestamp()
        awake.window.repeat_daily = awake.window.managed = True
        await awake.window._async_end()

    asyncio.run(run())
    nxt = datetime.fromtimestamp(awake.window.start, oslo)
    assert (nxt.day, nxt.hour, nxt.minute) == (25, 7, 0)


def test_leaving_hybrid_releases_a_held_frame(awake):
    m = awake.module

    async def run():
        await awake.window.async_set(at(NOW + 8 * 3600), at(NOW + 9 * 3600))
        await m.async_retire_awake_window(None, awake.entry, awake.cloud)

    asyncio.run(run())
    awake.cloud.async_set_keep_awake.assert_awaited_with(False)
    assert awake.cloud.async_plan_wake.await_args.args[0] is None
    assert awake.saved == {}


def test_overdue_steering_plans_from_now(awake):
    m = awake.module
    awake.cloud.wake_at = NOW - 3 * 3600  # Home Assistant was down

    async def run():
        awake.window.managed = True
        await awake.window._async_steer()

    asyncio.run(run())
    assert awake.cloud.async_plan_wake.await_count == 1
    assert awake.cloud.async_plan_wake.await_args.args[0] == NOW + m.HEARTBEAT


def test_daily_window_after_downtime_skips_only_passed_days(awake):
    oslo = ZoneInfo("Europe/Oslo")
    start = datetime(2026, 10, 24, 7, 0, tzinfo=oslo)
    end = datetime(2026, 10, 24, 9, 0, tzinfo=oslo)
    # Back on the 25th at 08:30, after DST ended: that day's window still runs.
    awake.clock.now = datetime(2026, 10, 25, 8, 30, tzinfo=oslo).timestamp()

    async def run():
        awake.window.start, awake.window.end = start.timestamp(), end.timestamp()
        awake.window.repeat_daily = awake.window.managed = True
        await awake.window._async_end()

    asyncio.run(run())
    nxt = datetime.fromtimestamp(awake.window.start, oslo)
    assert (nxt.day, nxt.hour) == (25, 7)


def test_rest_stays_pending_until_keep_awake_is_off(awake):
    m = awake.module
    awake.cloud.async_set_keep_awake.side_effect = m.FraimicCloudError("down")

    async def run():
        await awake.window.async_set(at(NOW + 8 * 3600), at(NOW + 9 * 3600))
        assert not awake.window.resting
        # Home Assistant restarts during the outage: the retry survives.
        restored = m.AwakeWindow(None, awake.entry)
        await restored.async_setup()
        assert restored.diagnostics()["rest_pending"]
        awake.cloud.async_set_keep_awake.side_effect = None
        awake.timers.clear()
        await restored._async_rest()
        assert restored.resting

    asyncio.run(run())


def test_a_refused_restart_is_retried(awake):
    m = awake.module
    awake.client.get_info.side_effect = [{"uptime": 5}, {"uptime": 7}, {"uptime": 30}]
    awake.client.restart.side_effect = [m.FraimicApiError("busy"), None]

    async def run():
        await awake.window.async_set(at(NOW), at(NOW + 3600))
        await settle()

    asyncio.run(run())
    assert awake.client.restart.await_count == 2
    assert awake.window.last_result == "restarted"


def test_a_replacement_window_ends_a_pending_rest(awake):
    m = awake.module
    awake.cloud.async_set_keep_awake.side_effect = [m.FraimicCloudError("down"), None, None]
    awake.client.get_info.return_value = {"uptime": 50_000}

    async def run():
        await awake.window.async_set(at(NOW + 8 * 3600), at(NOW + 9 * 3600))
        assert awake.window.holds_awake  # rest pending
        await awake.window.async_set(at(NOW), at(NOW + 3600))
        await settle()

    asyncio.run(run())
    assert awake.window.awake
    assert awake.window.diagnostics()["rest_pending"] is False
    # Keep-awake was only ever turned on again, never off mid-window.
    assert awake.cloud.async_set_keep_awake.await_args.args == (True,)


def test_a_window_does_not_follow_a_new_canvas(awake):
    m = awake.module

    async def run():
        await awake.window.async_set(at(NOW + 8 * 3600), at(NOW + 9 * 3600))
        awake.cloud.device_id = "other canvas"
        restored = m.AwakeWindow(None, awake.entry)
        await restored.async_setup()
        return restored

    restored = asyncio.run(run())
    assert restored.start is None and not restored.managed
    # The cloud no longer steers the new canvas toward the old window.
    assert awake.cloud.async_plan_wake.await_args.args[0] is None


def test_failed_hybrid_exit_is_reported_and_kept(awake):
    m = awake.module

    async def run():
        await awake.window.async_set(at(NOW + 8 * 3600), at(NOW + 9 * 3600))
        awake.cloud.async_set_keep_awake.side_effect = m.FraimicCloudError("down")
        return await m.async_retire_awake_window(None, awake.entry, awake.cloud)

    assert asyncio.run(run()) is False
    assert awake.saved  # retried on the next setup


def test_a_rest_in_flight_cannot_undo_a_replacement(awake):
    release = asyncio.Event()
    first = True

    async def slow_plan(wake_at):
        nonlocal first
        if first:
            first = False
            await release.wait()
        awake.cloud.wake_at = wake_at

    awake.cloud.async_plan_wake.side_effect = slow_plan
    awake.client.get_info.return_value = {"uptime": 50_000}

    async def run():
        resting = asyncio.ensure_future(
            awake.window.async_set(at(NOW + 8 * 3600), at(NOW + 9 * 3600))
        )
        await settle()
        replacing = asyncio.ensure_future(awake.window.async_set(at(NOW), at(NOW + 3600)))
        await settle()
        release.set()
        await asyncio.gather(resting, replacing)
        await settle()

    asyncio.run(run())
    # The old rest finishes before the replacement starts: never "off" mid-window.
    calls = [c.args for c in awake.cloud.async_set_keep_awake.await_args_list]
    assert calls == [(False,), (True,)]
    assert awake.window.awake


def test_a_missed_wake_goes_back_to_checks(awake):
    m = awake.module
    awake.client.get_info.side_effect = m.FraimicError("asleep")
    start = NOW + 8 * 3600
    wake = start - m.WAKE_LEAD

    async def run():
        await awake.window.async_set(at(start), at(start + 3600))
        steer = [fire for when, fire in awake.timers if when == wake + m.CATCH_WINDOW]
        assert len(steer) == 1
        awake.clock.now = wake + m.CATCH_WINDOW
        steer[0](at(awake.clock.now))
        await settle()
        awake.window.shutdown()

    asyncio.run(run())
    assert awake.cloud.async_plan_wake.await_args.args[0] == wake + m.CATCH_WINDOW + m.STANDBY_INTERVAL


def test_an_unknown_uptime_is_restarted_rather_than_trusted(awake):
    awake.client.get_info.side_effect = [{"uptime": None}, {"uptime": None}]

    async def run():
        await awake.window.async_set(at(NOW), at(NOW + 3600))
        await settle()

    asyncio.run(run())
    awake.client.restart.assert_awaited_once()
    assert awake.window.last_result == "restarted"


@pytest.mark.parametrize("slot_ahead", [True, False])
def test_a_plan_from_before_the_wake_album_is_moved_onto_it(awake, slot_ahead):
    m = awake.module
    awake.cloud.wake_album_id = None
    awake.cloud.delivery_deadline = NOW + (3600 if slot_ahead else -60)
    awake.saved["fraimic_awake_window_large"] = {"managed": True, "device_id": "canvas"}

    async def run():
        await awake.window.async_setup()
        await settle()

    asyncio.run(run())
    # The frame must not sleep on a slot that only the art album carried,
    # and that album's slot must not redraw it at the planned wake.
    assert awake.cloud.async_plan_wake.await_args.args[0] == NOW + m.HEARTBEAT
    awake.cloud.async_cancel_delivery.assert_awaited_once()
    # Art whose slot had not come yet is sent again rather than lost.
    assert awake.runtime.temporary_overlays.async_cloud_withdrawn.await_count == int(slot_ahead)


def test_a_late_catch_does_not_resend_what_may_be_drawn(awake):
    awake.client.get_info.side_effect = [{"uptime": 150}, {"uptime": 20}]

    async def run():
        await awake.window.async_set(at(NOW), at(NOW + 3600))
        await settle()

    asyncio.run(run())
    assert awake.window.last_result == "restarted"
    awake.cloud.async_cancel_delivery.assert_awaited()
    # The frame had time to download the image before the restart.
    awake.runtime.temporary_overlays.async_cloud_withdrawn.assert_not_awaited()


@pytest.mark.parametrize(("sent_ago", "resent"), [(600, False), (10, True)])
def test_an_awake_frame_only_misses_art_its_poll_has_not_seen(awake, sent_ago, resent):
    awake.client.get_info.return_value = {"uptime": 50_000}
    awake.cloud.last_anchor = datetime.fromtimestamp(NOW - sent_ago, UTC).isoformat()

    async def run():
        await awake.window.async_set(at(NOW), at(NOW + 3600))
        await settle()

    asyncio.run(run())
    # Older art was pushed at the frame's last poll; newer art would be lost.
    assert awake.runtime.temporary_overlays.async_cloud_withdrawn.await_count == int(resent)
