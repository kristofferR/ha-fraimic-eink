"""Pure-logic tests for cloud delivery: auth quirks, album cadence, PNG shape."""

from __future__ import annotations

import io
import sys
import types

import numpy as np
import pytest
from conftest import load


@pytest.fixture(scope="module")
def cloud():
    """Load ``cloud`` with aiohttp stubbed so no network stack is needed."""
    if "aiohttp" not in sys.modules:
        stub = types.ModuleType("aiohttp")

        class _Timeout:
            def __init__(self, **_kwargs) -> None:
                pass

        stub.ClientTimeout = _Timeout
        stub.ClientError = Exception
        stub.ClientSession = object
        stub.FormData = object
        sys.modules["aiohttp"] = stub
    return load("cloud")


const = load("const")
ic = load("image_convert")


def test_password_variants_prefer_raw_then_form_encoded(cloud):
    assert cloud.password_variants("plain123") == ("plain123",)
    assert cloud.password_variants("a b&c") == ("a b&c", "a+b%26c")


def test_album_interval_adds_lead_and_rounds_up(cloud):
    lead = const.CLOUD_SLOT_LEAD_MINUTES
    assert cloud.album_interval_minutes(600) == 10 + lead
    assert cloud.album_interval_minutes(601) == 11 + lead
    assert cloud.album_interval_minutes(1) == 1 + lead


def test_album_schedule_uses_largest_whole_unit(cloud):
    assert cloud.album_schedule(57 * 60)["interval_unit"] == "hours"
    assert cloud.album_schedule(57 * 60)["interval_value"] == 1
    assert cloud.album_schedule((1440 - const.CLOUD_SLOT_LEAD_MINUTES) * 60) == {
        "type": "interval",
        "interval_value": 1,
        "interval_unit": "days",
    }
    assert cloud.album_schedule(300)["interval_unit"] == "minutes"


def test_settings_payload_sends_every_key(cloud):
    payload = cloud.device_settings_payload({"style": "NONE"}, keep_awake=False)
    assert payload == {
        "voiceRecordingEnabled": True,
        "keepAwakeEnabled": False,
        "chargingLedEnabled": True,
        "style": "NONE",
    }


def test_cloud_png_is_pure_primaries_in_viewed_orientation():
    from PIL import Image

    width, height = 1440, 2560
    indices = np.tile(np.arange(6, dtype=np.uint8), width * height // 6)
    png = ic.indices_to_cloud_png(indices, width, height, 90)
    image = Image.open(io.BytesIO(png)).convert("RGB")
    assert image.size == (2560, 1440)
    colours = {colour for _count, colour in image.getcolors(16)}
    assert colours == set(ic._OFFICIAL_PALETTE_RGB)


def test_cloud_png_rotation_is_clockwise_like_the_preview():
    from PIL import Image

    width, height = 1600, 1200
    indices = np.ones(width * height, dtype=np.uint8)  # white
    indices[:width] = 0  # black top row of the native buffer
    # A frame mounted with base rotation 90 shows the native buffer turned
    # back by 270 clockwise, so its top row ends up on the left edge.
    png = ic.indices_to_cloud_png(indices, width, height, (-90) % 360)
    image = Image.open(io.BytesIO(png)).convert("RGB")
    assert image.size == (1200, 1600)
    assert image.getpixel((0, 800)) == (0, 0, 0)
    assert image.getpixel((1199, 800)) == (255, 255, 255)


@pytest.fixture
def delivery_module(cloud, monkeypatch):
    core = types.ModuleType("homeassistant.core")
    core.HomeAssistant = object
    storage = types.ModuleType("homeassistant.helpers.storage")
    storage.Store = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, "homeassistant.core", core)
    monkeypatch.setitem(sys.modules, "homeassistant.helpers.storage", storage)
    sys.modules.pop("fraimic.cloud_delivery", None)
    return load("cloud_delivery")


def test_reassignment_restores_old_canvas_and_releases_new_canvas(delivery_module):
    import asyncio
    from unittest.mock import AsyncMock

    client = types.SimpleNamespace(
        async_set_keep_awake=AsyncMock(),
        async_update_album=AsyncMock(return_value={"id": "album"}),
    )
    entry = types.SimpleNamespace(entry_id="frame", title="Frame")
    delivery = delivery_module.FraimicCloudDelivery(None, entry, client, "new")
    delivery._store = types.SimpleNamespace(async_save=AsyncMock())
    delivery.album_id = "album"
    delivery.album_device_id = "old"
    delivery.keep_awake_released = True

    asyncio.run(delivery._async_point_album("upload", 60))
    client.async_set_keep_awake.assert_awaited_once_with("old", True)
    assert delivery.album_device_id == "new"
    assert delivery.keep_awake_released is False
    asyncio.run(delivery._async_release_keep_awake())
    assert client.async_set_keep_awake.call_args.args == ("new", False)


def test_release_targets_persisted_canvas_and_keeps_failed_cleanup(delivery_module):
    import asyncio
    from unittest.mock import AsyncMock

    client = types.SimpleNamespace(
        async_set_keep_awake=AsyncMock(),
        async_update_album=AsyncMock(side_effect=delivery_module.FraimicCloudError("offline")),
    )
    entry = types.SimpleNamespace(entry_id="frame", title="Frame")
    delivery = delivery_module.FraimicCloudDelivery(None, entry, client, "new")
    delivery._store = types.SimpleNamespace(async_save=AsyncMock())
    delivery.album_id = "album"
    delivery.album_device_id = "old"
    delivery.keep_awake_released = True

    assert asyncio.run(delivery.async_release()) is False
    assert delivery.album_id == "album"
    client.async_set_keep_awake.assert_awaited_once_with("old", True)


def test_cloud_snapshot_drops_volatile_lan_fields(delivery_module):
    previous = {
        "device_id": "canvas", "firmware_version": "0.2.29",
        "battery": {"charging": True, "percent": 99},
        "wifi": {"connected": True, "rssi": -30},
        "device": {"uptime_s": 600},
        "display": {"width": 1600, "height": 1200, "last_refresh": 123},
        "raw": {"charging": True},
    }
    snapshot = delivery_module.cloud_device_snapshot({"battery_pct": 70}, previous)
    assert snapshot["device_id"] == "canvas"
    assert snapshot["firmware_version"] == "0.2.29"
    assert snapshot["display"] == {"width": 1600, "height": 1200}
    assert snapshot["battery"] == {"percent": 70}
    assert "connected" not in snapshot["wifi"]
    assert "uptime_s" not in snapshot["device"]
    assert "raw" not in snapshot


def test_cloud_album_expires_once_and_reactivates_for_later_send(delivery_module, monkeypatch):
    import asyncio
    from unittest.mock import AsyncMock

    client = types.SimpleNamespace(async_update_album=AsyncMock(return_value={"id": "album"}))
    entry = types.SimpleNamespace(entry_id="frame", title="Frame")
    delivery = delivery_module.FraimicCloudDelivery(None, entry, client, "canvas")
    delivery._store = types.SimpleNamespace(async_save=AsyncMock())
    delivery.album_id = "album"
    delivery.album_device_id = "canvas"
    delivery.album_active = True
    delivery.upload_id = "image"
    delivery.last_anchor = "2026-09-08T12:00:00+00:00"
    deadline = delivery.delivery_deadline
    assert deadline == delivery_module.datetime.fromisoformat(delivery.last_anchor).timestamp() + delivery.wake_interval + 180
    monkeypatch.setattr(delivery_module.time, "time", lambda: deadline - 1)
    asyncio.run(delivery.async_expire_delivery())
    client.async_update_album.assert_not_awaited()
    monkeypatch.setattr(delivery_module.time, "time", lambda: deadline + 1)
    asyncio.run(delivery.async_expire_delivery())
    asyncio.run(delivery.async_expire_delivery())
    client.async_update_album.assert_awaited_once_with("album", {"active": False})
    assert not delivery.has_image
    asyncio.run(delivery._async_point_album("next", 363))
    assert client.async_update_album.call_args.args == (
        "album",
        {
            "upload_ids": ["next"],
            "active": True,
            "schedule": {"type": "interval", "interval_value": 363, "interval_unit": "minutes"},
        },
    )
    assert delivery.album_active


@pytest.mark.parametrize("released", [False, True])
def test_account_change_keeps_ownership_until_cleanup_succeeds(delivery_module, released):
    import asyncio
    from unittest.mock import AsyncMock

    delivery = types.SimpleNamespace(
        async_release=AsyncMock(return_value=released),
        async_forget_album=AsyncMock(),
    )
    entry = types.SimpleNamespace(
        options={"cloud_email": "old@example.test"},
        runtime_data=types.SimpleNamespace(cloud=delivery, upload_lock=asyncio.Lock()),
    )
    assert asyncio.run(delivery_module.async_release_for_account_change(
        None, entry, "new@example.test"
    )) is released
    assert delivery.async_forget_album.await_count == int(released)
    assert entry.options["cloud_email"] == "old@example.test"


def test_camera_interval_overrides_playlist_sync_and_restores(delivery_module):
    import asyncio
    from unittest.mock import AsyncMock

    client = types.SimpleNamespace(async_update_album=AsyncMock(return_value={}))
    entry = types.SimpleNamespace(entry_id="frame", title="Frame")
    delivery = delivery_module.FraimicCloudDelivery(None, entry, client, "canvas")
    delivery._store = types.SimpleNamespace(async_save=AsyncMock())
    delivery.album_id = "album"
    delivery.camera_interval = 600

    asyncio.run(delivery.async_sync_interval(1800))
    assert delivery.interval == 600
    delivery.camera_interval = None
    asyncio.run(delivery.async_sync_interval(1800))
    assert delivery.interval == 1800


@pytest.mark.parametrize("released", [True, False])
def test_removal_preserves_ownership_and_reports_failed_cleanup(delivery_module, monkeypatch, released):
    import asyncio
    from unittest.mock import AsyncMock, Mock

    issues = types.ModuleType("homeassistant.helpers.issue_registry")
    issues.IssueSeverity = types.SimpleNamespace(WARNING="warning")
    issues.async_create_issue = Mock()
    issues.async_delete_issue = Mock()
    helpers = types.ModuleType("homeassistant.helpers")
    helpers.issue_registry = issues
    monkeypatch.setitem(sys.modules, "homeassistant.helpers", helpers)
    monkeypatch.setitem(sys.modules, "homeassistant.helpers.issue_registry", issues)
    entry = types.SimpleNamespace(entry_id="frame", title="Frame")
    delivery = delivery_module.FraimicCloudDelivery(None, entry, None, "canvas")
    delivery._store = types.SimpleNamespace(async_save=AsyncMock(), async_remove=AsyncMock())
    delivery.album_id = "album"
    delivery.album_device_id = "canvas"
    delivery.async_release = AsyncMock(return_value=released)

    asyncio.run(delivery.async_remove())

    if released:
        assert delivery.album_id is None
        delivery._store.async_remove.assert_awaited_once()
        issues.async_create_issue.assert_not_called()
    else:
        assert delivery.album_id == "album"
        delivery._store.async_remove.assert_not_awaited()
        issues.async_create_issue.assert_called_once()
        assert issues.async_create_issue.call_args.kwargs["is_persistent"] is True


def test_lan_refresh_invalidates_cached_cloud_fallback(delivery_module, monkeypatch):
    import asyncio
    import time
    from datetime import timezone
    from unittest.mock import AsyncMock, Mock

    class GenericStub:
        def __class_getitem__(cls, _item):
            return cls

    stubs = {
        "homeassistant.config_entries": {"ConfigEntry": GenericStub},
        "homeassistant.const": {"CONF_HOST": "host"},
        "homeassistant.core": {"HomeAssistant": object, "callback": lambda fn: fn},
        "homeassistant.helpers.aiohttp_client": {"async_get_clientsession": Mock()},
        "homeassistant.helpers.event": {"async_call_later": Mock()},
        "homeassistant.helpers.update_coordinator": {
            "DataUpdateCoordinator": GenericStub, "UpdateFailed": RuntimeError,
        },
        "homeassistant.util": {
            "dt": types.SimpleNamespace(get_default_time_zone=lambda: timezone.utc),
        },
        "homeassistant.helpers": {"issue_registry": Mock()},
    }
    for name, attributes in stubs.items():
        module = types.ModuleType(name)
        module.__dict__.update(attributes)
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.delitem(sys.modules, "fraimic.coordinator", raising=False)
    coordinator_module = load("coordinator")
    coordinator = object.__new__(coordinator_module.FraimicDataUpdateCoordinator)
    cloud_device = AsyncMock(return_value={
        "battery_pct": 80, "settings": {"keepAwakeEnabled": True},
    })
    coordinator.config_entry = types.SimpleNamespace(
        runtime_data=types.SimpleNamespace(
            power=None, cloud=types.SimpleNamespace(async_device=cloud_device),
        ),
    )
    coordinator.client = types.SimpleNamespace(
        last_response=None, wrong_device=None,
        get_info=AsyncMock(side_effect=[
            {"battery_pct": 80}, coordinator_module.FraimicConnectionError("asleep"),
        ]),
    )
    coordinator._cloud_snapshot = (time.time(), {"battery": {"percent": 20}})
    coordinator._cable_drain = None
    coordinator._async_backfill_unique_id = Mock()
    coordinator._async_save_cache = AsyncMock()

    async def poll():
        lan = await coordinator._async_update_data()
        assert lan["battery"]["percent"] == 80
        assert coordinator._cloud_snapshot is None
        fallback = await coordinator._async_update_data()
        assert fallback["battery"]["percent"] == 80
        assert fallback["settings"]["keep_awake"] is True

    asyncio.run(poll())
    cloud_device.assert_awaited_once()


@pytest.mark.parametrize('status', [None, 404, 503])
def test_hybrid_cancels_pending_album_without_changing_keep_awake(delivery_module, status):
    import asyncio
    from unittest.mock import AsyncMock

    error = delivery_module.FraimicCloudError('failed', status=status) if status else None
    client = types.SimpleNamespace(
        async_update_album=AsyncMock(side_effect=error), async_set_keep_awake=AsyncMock(),
    )
    delivery = delivery_module.FraimicCloudDelivery(
        None, types.SimpleNamespace(entry_id='frame'), client, 'canvas',
    )
    delivery._store = types.SimpleNamespace(async_save=AsyncMock())
    delivery.album_id = 'owned-album'
    delivery.album_active = True
    delivery.last_anchor = '2026-09-17T12:00:00+00:00'
    deadline = delivery.delivery_deadline
    assert deadline is not None
    delivery.keep_awake_released = True
    if status == 503:
        with pytest.raises(delivery_module.FraimicCloudError):
            asyncio.run(delivery.async_cancel_delivery())
        assert delivery.album_active
        assert delivery.delivery_deadline == deadline
        delivery._store.async_save.assert_not_awaited()
    else:
        asyncio.run(delivery.async_cancel_delivery())
        assert not delivery.album_active
        assert delivery.delivery_deadline is None
        delivery._store.async_save.assert_awaited_once()
        asyncio.run(delivery.async_cancel_delivery())
    client.async_update_album.assert_awaited_once_with('owned-album', {'active': False})
    client.async_set_keep_awake.assert_not_awaited()
    assert delivery.keep_awake_released


@pytest.mark.parametrize("accepted", [True, False])
def test_cloud_preview_persists_only_accepted_artwork(delivery_module, accepted):
    import asyncio
    from unittest.mock import AsyncMock

    hass = types.SimpleNamespace(async_add_executor_job=AsyncMock(return_value=b"new-preview"))
    client = types.SimpleNamespace(async_upload_png=AsyncMock(return_value="new-upload"))
    entry = types.SimpleNamespace(entry_id="frame", data={}, options={})
    delivery = delivery_module.FraimicCloudDelivery(hass, entry, client, "canvas")
    delivery._store = types.SimpleNamespace(async_save=AsyncMock())
    delivery.preview_png, delivery.preview_title = b"old-preview", "Old artwork"
    delivery.keep_awake_released = True
    delivery._async_point_album = AsyncMock(
        return_value={"updated_at": "2026-09-17T12:00:00+00:00"},
        side_effect=None if accepted else delivery_module.FraimicCloudError("rejected"),
    )
    delivery._async_discard = AsyncMock()
    if not accepted:
        with pytest.raises(delivery_module.FraimicCloudError):
            asyncio.run(delivery.async_deliver(b"packed", title="New artwork", preview_png=b"rendered-preview"))
        assert (delivery.preview_png, delivery.preview_title) == (b"old-preview", "Old artwork")
        delivery._store.async_save.assert_not_awaited()
        return
    source = {"library_image": "image-1"}
    asyncio.run(delivery.async_deliver(
        b"packed", title="New artwork", preview_png=b"rendered-preview", source=source,
    ))
    saved = delivery._store.async_save.call_args.args[0]
    restored = delivery_module.FraimicCloudDelivery(hass, entry, client, "canvas")
    restored._store = types.SimpleNamespace(async_load=AsyncMock(return_value=saved), async_save=AsyncMock())
    asyncio.run(restored.async_setup())
    assert (restored.preview_png, restored.preview_title, restored.preview_source) == (
        b"rendered-preview", "New artwork", source
    )
    asyncio.run(restored.async_clear_preview())
    cleared = restored._store.async_save.call_args.args[0]
    assert cleared["preview_png"] is cleared["preview_title"] is cleared["preview_source"] is None


@pytest.mark.parametrize("normal", [63, 363, 1440])
def test_steered_slots_land_on_the_wake_within_a_minute_per_slot(cloud, normal):
    now = 1_800_000_000.0
    assert cloud.steered_minutes(now, normal, None) == normal
    assert cloud.steered_minutes(now, normal, now + 120) == normal  # too late
    for remaining in range(const.CLOUD_SLOT_LEAD_MINUTES, 2 * 1440):
        minutes = cloud.steered_minutes(now, normal, now + remaining * 60 + 30)
        slots = -(-remaining // normal)
        assert minutes <= normal
        assert 0 <= remaining - slots * minutes < slots


def test_art_retires_after_its_slot_even_with_a_planned_wake(delivery_module, monkeypatch):
    import asyncio
    from unittest.mock import AsyncMock

    client = types.SimpleNamespace(async_update_album=AsyncMock(return_value={"id": "album"}))
    entry = types.SimpleNamespace(entry_id="frame", title="Frame")
    delivery = delivery_module.FraimicCloudDelivery(None, entry, client, "canvas")
    delivery._store = types.SimpleNamespace(async_save=AsyncMock())
    delivery.album_id, delivery.album_active, delivery.upload_id = "album", True, "image"
    delivery.last_anchor = "2026-09-08T12:00:00+00:00"
    delivery.slot_minutes = 30
    deadline = delivery.delivery_deadline
    assert deadline == delivery_module.datetime.fromisoformat(delivery.last_anchor).timestamp() + 30 * 60 + 180
    # The wake album carries the wake; re-serving the art there would redraw it.
    delivery.wake_at = deadline + 3600
    monkeypatch.setattr(delivery_module.time, "time", lambda: deadline + 1)
    asyncio.run(delivery.async_expire_delivery())
    client.async_update_album.assert_awaited_once_with("album", {"active": False})


def _wake_delivery(delivery_module, monkeypatch, now):
    from unittest.mock import AsyncMock

    monkeypatch.setattr(delivery_module.time, "time", lambda: now)
    client = types.SimpleNamespace(
        async_create_album=AsyncMock(return_value={"id": "wake"}),
        async_update_album=AsyncMock(return_value={"updated_at": "2027-01-15T08:00:00+00:00"}),
        async_delete_album=AsyncMock(),
    )
    entry = types.SimpleNamespace(entry_id="frame", title="Frame")
    delivery = delivery_module.FraimicCloudDelivery(None, entry, client, "canvas")
    delivery._store = types.SimpleNamespace(async_save=AsyncMock())
    delivery.interval = 6 * 3600
    return delivery, client, entry


def test_planning_a_wake_never_touches_the_art_album(delivery_module, monkeypatch):
    import asyncio

    now = 1_800_000_000.0
    delivery, client, entry = _wake_delivery(delivery_module, monkeypatch, now)
    delivery.album_id, delivery.album_active, delivery.upload_id = "album", True, "image"

    # Idle art: one slot, at the wake. The empty album has nothing to redraw.
    asyncio.run(delivery.async_plan_wake(now + 650 * 60))
    created = client.async_create_album.call_args.args[0]
    assert created["upload_ids"] == [] and created["active"] is True
    assert created["schedule"]["interval_value"] == 650
    assert created["device_assignments"] == [{"device_id": "canvas"}]
    assert delivery.wake_album_id == "wake"

    # Rotating art: a wake for every picture on the way.
    entry.runtime_data = types.SimpleNamespace(scheduler=types.SimpleNamespace(producing=True))
    asyncio.run(delivery.async_plan_wake(now + 650 * 60))
    client.async_update_album.assert_awaited_once_with(
        "wake",
        {
            "active": True,
            "schedule": {"type": "interval", "interval_value": 325, "interval_unit": "minutes"},
            "device_assignments": [{"device_id": "canvas"}],
            "upload_ids": [],  # an image added in the app would redraw every wake
        },
    )
    assert client.async_create_album.await_count == 1

    client.async_update_album.side_effect = delivery_module.FraimicCloudError("down")
    with pytest.raises(delivery_module.FraimicCloudError):
        asyncio.run(delivery.async_plan_wake(now + 900 * 60))
    assert delivery.wake_at == now + 650 * 60  # the old plan still stands

    client.async_update_album.side_effect = None
    asyncio.run(delivery.async_plan_wake(None))
    client.async_delete_album.assert_awaited_once_with("wake")
    assert delivery.wake_album_id is None and delivery.wake_at is None


def test_a_deleted_wake_album_is_recreated(delivery_module, monkeypatch):
    import asyncio

    delivery, client, _entry = _wake_delivery(delivery_module, monkeypatch, 1_800_000_000.0)
    delivery.wake_album_id = "gone"
    client.async_update_album.side_effect = delivery_module.FraimicCloudError("gone", status=404)
    asyncio.run(delivery.async_plan_wake(1_800_000_000.0 + 3600))
    client.async_create_album.assert_awaited_once()
    assert delivery.wake_album_id == "wake"


@pytest.mark.parametrize(("lead", "aligned"), [(3600, True), (60, False)])
def test_cloud_art_moves_the_wake_onto_its_slot(delivery_module, monkeypatch, lead, aligned):
    import asyncio
    from unittest.mock import AsyncMock

    now = 1_800_000_000.0
    delivery, client, entry = _wake_delivery(delivery_module, monkeypatch, now)
    entry.data, entry.options = {}, {}
    delivery.wake_album_id, delivery.wake_at = "wake", now + lead
    delivery.hass = types.SimpleNamespace(async_add_executor_job=AsyncMock(return_value=b"png"))
    client.async_upload_png = AsyncMock(return_value="upload")
    delivery.album_id, delivery.album_device_id, delivery.keep_awake_released = "album", "canvas", True

    asyncio.run(delivery.async_deliver(b"bin", title="Art", preview_png=b"preview"))
    calls = {call.args[0]: call.args[1] for call in client.async_update_album.await_args_list}
    if aligned:
        # One grid for both albums: the frame wakes when the art is due.
        assert calls["wake"]["schedule"] == calls["album"]["schedule"]
    else:
        # Too close to steer; the planned wake comes first and stays.
        assert "wake" not in calls


def test_failed_wake_alignment_fails_the_delivery(delivery_module, monkeypatch):
    import asyncio
    from unittest.mock import AsyncMock

    now = 1_800_000_000.0
    delivery, client, entry = _wake_delivery(delivery_module, monkeypatch, now)
    entry.data, entry.options = {}, {}
    delivery.wake_album_id, delivery.wake_at = "wake", now + 3600
    delivery.hass = types.SimpleNamespace(async_add_executor_job=AsyncMock(return_value=b"png"))
    client.async_upload_png = AsyncMock(return_value="upload")
    delivery.album_id, delivery.album_device_id, delivery.keep_awake_released = "album", "canvas", True

    async def update(album_id, payload):
        if album_id == "wake":
            raise delivery_module.FraimicCloudError("down")
        return {"updated_at": "2027-01-15T08:00:00+00:00"}

    client.async_update_album.side_effect = update
    # The frame would sleep through the art's slot: report it, so it is retried.
    with pytest.raises(delivery_module.FraimicCloudError):
        asyncio.run(delivery.async_deliver(b"bin", title="Art", preview_png=b"preview"))


def test_failed_alignment_on_an_interval_change_is_retried(delivery_module, monkeypatch):
    import asyncio

    now = 1_800_000_000.0
    delivery, client, _entry = _wake_delivery(delivery_module, monkeypatch, now)
    delivery.album_id, delivery.wake_album_id, delivery.wake_at = "album", "wake", now + 86400

    async def update(album_id, payload):
        if album_id == "wake":
            raise delivery_module.FraimicCloudError("down")
        return {"updated_at": "2027-01-15T08:00:00+00:00"}

    client.async_update_album.side_effect = update
    asyncio.run(delivery.async_sync_interval(3600))
    assert delivery.interval == 6 * 3600  # unchanged, so the next sync tries again
    client.async_update_album.side_effect = None
    asyncio.run(delivery.async_sync_interval(3600))
    assert delivery.interval == 3600
    assert client.async_update_album.await_args.args[0] == "wake"


def test_a_wake_album_alone_still_needs_cleanup(delivery_module, monkeypatch):
    delivery, _client, _entry = _wake_delivery(delivery_module, monkeypatch, 1_800_000_000.0)
    assert not delivery.holds_account_state
    delivery.wake_album_id = "wake"
    assert delivery.holds_account_state


def test_release_deletes_the_wake_album(delivery_module, monkeypatch):
    import asyncio

    delivery, client, _entry = _wake_delivery(delivery_module, monkeypatch, 1_800_000_000.0)
    delivery.wake_album_id = "wake"
    client.async_delete_album.side_effect = delivery_module.FraimicCloudError("gone", status=404)
    assert asyncio.run(delivery.async_release()) is True
    assert delivery.wake_album_id is None


def test_account_times_without_a_zone_are_utc(cloud):
    assert cloud.cloud_timestamp("2026-10-19T12:51:25") == 1792414285.0
    assert cloud.cloud_timestamp("2026-10-19T14:51:25+02:00") == 1792414285.0


def test_awake_window_keep_awake_survives_a_cloud_fallback(delivery_module):
    import asyncio
    from unittest.mock import AsyncMock

    client = types.SimpleNamespace(async_set_keep_awake=AsyncMock())
    entry = types.SimpleNamespace(entry_id="frame", title="Frame")
    delivery = delivery_module.FraimicCloudDelivery(None, entry, client, "canvas")
    delivery._store = types.SimpleNamespace(async_save=AsyncMock())
    assert delivery.keep_awake_released is False

    asyncio.run(delivery.async_set_keep_awake(True))
    # The one-time release after a cloud delivery would now turn it off.
    assert delivery.keep_awake_released is True
