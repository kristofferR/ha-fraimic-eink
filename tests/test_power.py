"""Pure battery-policy tests (no Home Assistant import required)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from conftest import load

const = load("const")
power = load("power")


def _manager(
    mode: str = const.POWER_MODE_MINIMUM,
) -> power.FraimicPowerManager:
    entry = SimpleNamespace(entry_id="entry", options={const.CONF_POWER_MODE: mode})
    return power.FraimicPowerManager(SimpleNamespace(), entry)


def test_effective_polling_profiles() -> None:
    assert power.effective_scan_interval({}) is None
    assert power.effective_scan_interval(
        {
            const.CONF_POWER_MODE: const.POWER_MODE_BALANCED,
            const.CONF_SCAN_INTERVAL: 60,
        }
    ) == 3600
    assert power.effective_scan_interval(
        {
            const.CONF_POWER_MODE: const.POWER_MODE_RESPONSIVE,
            const.CONF_SCAN_INTERVAL: 300,
        }
    ) == 300


def test_minimum_queue_is_passive_but_tracks_predicted_wake() -> None:
    assert power.queue_probe_delay(const.POWER_MODE_MINIMUM, 0, now=1000) is None
    assert power.queue_probe_delay(
        const.POWER_MODE_MINIMUM,
        0,
        now=1000,
        next_refresh="1970-01-01T00:18:20+00:00",
    ) == 130


def test_tracker_matches_frame_by_host_or_reported_ip() -> None:
    data = {"wifi": {"ip": "192.168.1.51", "mac": "AA:BB:CC:DD:EE:FF"}}

    assert power.tracker_matches_frame(
        "fraimic.local",
        data,
        "device_tracker.frame",
        {"ip_address": "192.168.1.51"},
    )
    assert power.tracker_matches_frame(
        "192.168.1.50",
        data,
        "device_tracker.frame",
        {"host": "192.168.1.50"},
    )


def test_tracker_matches_frame_by_mac_attribute_or_entity_id() -> None:
    data = {"wifi": {"mac": "aa:bb:cc:dd:ee:ff"}}

    assert power.tracker_matches_frame(
        "fraimic.local",
        data,
        "device_tracker.frame",
        {"mac_address": "AA-BB-CC-DD-EE-FF"},
    )
    assert power.tracker_matches_frame(
        "fraimic.local",
        data,
        "device_tracker.aa_bb_cc_dd_ee_ff",
        {},
    )


def test_tracker_rejects_unrelated_or_incomplete_identity() -> None:
    data = {"wifi": {"ip": "192.168.1.51", "mac": "aa:bb:cc:dd:ee:ff"}}

    assert not power.tracker_matches_frame(
        "fraimic.local",
        data,
        "device_tracker.phone",
        {"ip": "192.168.1.20", "mac": "11:22:33:44:55:66"},
    )
    assert not power.tracker_matches_frame(
        "fraimic.local", None, "device_tracker.frame", {}
    )


def test_balanced_queue_backoff() -> None:
    assert power.queue_probe_delay(const.POWER_MODE_BALANCED, 0, now=1000) == 30
    assert power.queue_probe_delay(const.POWER_MODE_BALANCED, 2, now=1000) == 120
    assert power.queue_probe_delay(const.POWER_MODE_BALANCED, 99, now=1000) == 3600


def test_global_duplicate_suppression_applies_to_manual_sends() -> None:
    manager = _manager()
    manager.last_hash = "same"
    token = manager.begin(power.TRIGGER_MANUAL)
    assert manager.skip_reason("same", power.TRIGGER_MANUAL, token, {}) == power.SKIP_DUPLICATE


def test_due_native_refresh_invalidates_duplicate_assumption() -> None:
    manager = _manager()
    manager.last_hash = "same"
    token = manager.begin(power.TRIGGER_MANUAL)
    assert manager.skip_reason(
        "same",
        power.TRIGGER_MANUAL,
        token,
        {"display": {"next_refresh": "1970-01-01T00:16:40+00:00"}},
        now=1001,
    ) is None


def test_automatic_send_is_gated_on_low_battery() -> None:
    manager = _manager(const.POWER_MODE_BALANCED)
    token = manager.begin(power.TRIGGER_PLAYLIST)
    assert manager.skip_reason(
        "new",
        power.TRIGGER_PLAYLIST,
        token,
        {"battery": {"percent": 24, "charging": False}},
        now=10_000,
    ) == power.SKIP_LOW_BATTERY


def test_minimum_mode_defers_automatic_send_with_unknown_battery() -> None:
    manager = _manager()
    token = manager.begin(power.TRIGGER_PLAYLIST)
    assert manager.skip_reason(
        "new", power.TRIGGER_PLAYLIST, token, {}, now=100_000
    ) == power.SKIP_LOW_BATTERY


def test_charging_bypasses_battery_cooldown_and_budget() -> None:
    manager = _manager(const.POWER_MODE_MINIMUM)
    manager.last_automatic_at = 9_999
    manager.budget_day = "1970-01-01"
    manager.automatic_count = 99
    token = manager.begin(power.TRIGGER_SCHEDULED)
    assert manager.skip_reason(
        "new",
        power.TRIGGER_SCHEDULED,
        token,
        {"battery": {"percent": 5, "charging": True}},
        now=10_000,
    ) is None


def test_higher_priority_automatic_send_coalesces_older_work() -> None:
    manager = _manager(const.POWER_MODE_RESPONSIVE)
    camera = manager.begin(power.TRIGGER_CAMERA)
    scheduled = manager.begin(power.TRIGGER_SCHEDULED)
    assert manager.skip_reason(
        "camera", power.TRIGGER_CAMERA, camera, {}, now=10_000
    ) == power.SKIP_COALESCED
    assert manager.skip_reason(
        "scheduled", power.TRIGGER_SCHEDULED, scheduled, {}, now=10_000
    ) is None


def test_native_display_change_invalidates_persisted_hash() -> None:
    manager = _manager()
    manager.last_hash = "integration-image"
    manager.last_display_marker = "old"
    asyncio.run(
        manager.async_observe_frame({"display": {"last_refresh": "new"}})
    )
    assert manager.last_hash is None


def test_minimum_daily_budget_blocks_second_automatic_redraw() -> None:
    manager = _manager()
    asyncio.run(
        manager.async_record_upload("first", power.TRIGGER_SCHEDULED, now=100_000)
    )
    manager.last_automatic_at = 0
    manager.last_upload_at = 0
    token = manager.begin(power.TRIGGER_SCHEDULED)
    assert manager.skip_reason(
        "second",
        power.TRIGGER_SCHEDULED,
        token,
        {"battery": {"percent": 80, "charging": False}},
        now=100_001,
    ) == power.SKIP_DAILY_BUDGET


def test_manual_redraw_starts_automatic_cooldown() -> None:
    manager = _manager(const.POWER_MODE_BALANCED)
    asyncio.run(
        manager.async_record_upload("manual", power.TRIGGER_MANUAL, now=100_000)
    )
    token = manager.begin(power.TRIGGER_CAMERA)
    assert manager.skip_reason(
        "camera",
        power.TRIGGER_CAMERA,
        token,
        {"battery": {"percent": 80, "charging": False}},
        now=100_001,
    ) == power.SKIP_COOLDOWN


def test_experimental_auto_sleep_obeys_safe_guards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slept: list[bool] = []

    async def no_delay(_seconds: float) -> None:
        return None

    async def sleep_frame() -> None:
        slept.append(True)

    entry = SimpleNamespace(
        entry_id="entry",
        options={
            const.CONF_POWER_MODE: const.POWER_MODE_MINIMUM,
            const.CONF_AUTO_SLEEP: True,
        },
    )
    entry.runtime_data = SimpleNamespace(
        coordinator=SimpleNamespace(
            data={
                "battery": {"charging": False, "cable_connected": False},
                "settings": {"keep_awake": False},
            }
        ),
        upload_lock=asyncio.Lock(),
        send_queue=SimpleNamespace(pending=None),
        client=SimpleNamespace(sleep=sleep_frame),
    )
    manager = power.FraimicPowerManager(SimpleNamespace(), entry)
    monkeypatch.setattr(power.asyncio, "sleep", no_delay)

    asyncio.run(manager._async_sleep_after_redraw())

    assert slept == [True]


def test_cloud_delivery_invalidates_local_duplicate_hash_without_spending_budget():
    from unittest.mock import AsyncMock

    manager = _manager()
    manager.last_hash = 'old-local-image'
    manager.last_upload_at = 123
    manager.automatic_count = 1
    manager._store = SimpleNamespace(async_save=AsyncMock())
    asyncio.run(manager.async_invalidate_display())
    assert manager.last_hash is None
    saved = manager._store.async_save.call_args.args[0]
    assert saved['last_hash'] is None
    assert saved['last_upload_at'] == 123
    assert saved['automatic_count'] == 1


@pytest.mark.parametrize("mode,background_reason", [
    (const.POWER_MODE_MINIMUM, power.SKIP_COOLDOWN),
    (const.POWER_MODE_BALANCED, power.SKIP_COOLDOWN),
    (const.POWER_MODE_RESPONSIVE, power.SKIP_DAILY_BUDGET),
])
def test_explicit_queue_interval_is_not_overridden_by_power_mode(mode, background_reason):
    manager = _manager(mode)
    now = 1789732800
    manager.last_upload_at = now - 300
    manager.budget_day = power.datetime.fromtimestamp(now, power.timezone.utc).date().isoformat()
    manager.automatic_count = 100
    data = {"battery": {"percent": 51, "charging": False}}
    token = manager.begin(power.TRIGGER_PLAYLIST)
    assert manager.skip_reason("new", power.TRIGGER_PLAYLIST, token, data, now=now) is None
    manager.finish(token)
    token = manager.begin(power.TRIGGER_CAMERA)
    assert manager.skip_reason("new", power.TRIGGER_CAMERA, token, data, now=now) == background_reason


def test_queue_still_reports_low_battery_and_retry_time():
    manager = _manager()
    token = manager.begin(power.TRIGGER_PLAYLIST)
    assert manager.skip_reason("new", power.TRIGGER_PLAYLIST, token, {"battery": {"percent": 15}}, now=1000) == power.SKIP_LOW_BATTERY
    assert manager.retry_at(power.SKIP_LOW_BATTERY, now=1000) == 1300
    assert manager.retry_at(power.SKIP_DAILY_BUDGET, now=1000) == 86400


def test_queue_redraw_does_not_consume_background_budget():
    from unittest.mock import AsyncMock
    manager = _manager()
    manager._async_save = AsyncMock()
    asyncio.run(manager.async_record_upload("queue", power.TRIGGER_PLAYLIST, now=100_000))
    assert manager.upload_count == 1
    assert manager.last_hash == "queue"
    assert manager.automatic_count == 0


def test_overlay_interval_keeps_low_battery_protection_without_background_cooldown():
    manager = _manager(const.POWER_MODE_BALANCED)
    manager.last_upload_at = 9_999
    manager.budget_day = "1970-01-01"
    manager.automatic_count = 999
    token = manager.begin(power.TRIGGER_OVERLAY)
    assert manager.skip_reason(
        "new", power.TRIGGER_OVERLAY, token,
        {"battery": {"percent": 70, "charging": False}}, now=10_000,
    ) is None
    assert manager.skip_reason(
        "new", power.TRIGGER_OVERLAY, token,
        {"battery": {"percent": 20, "charging": False}}, now=10_000,
    ) == power.SKIP_LOW_BATTERY

@pytest.mark.parametrize("trigger", [power.TRIGGER_MANUAL, power.TRIGGER_OVERLAY])
def test_stale_native_schedule_does_not_repeat_an_already_confirmed_upload(trigger):
    manager = _manager()
    asyncio.run(manager.async_record_upload("same", trigger, now=1005))
    token = manager.begin(trigger)
    data = {"battery": {"percent": 80}, "display": {"next_refresh": "1970-01-01T00:16:40+00:00"}}
    assert manager.skip_reason("same", trigger, token, data, now=1010) == power.SKIP_DUPLICATE
    # A newer native deadline can still replace that upload.
    data["display"]["next_refresh"] = "1970-01-01T00:16:48+00:00"
    assert manager.skip_reason("same", trigger, token, data, now=1010) is None
