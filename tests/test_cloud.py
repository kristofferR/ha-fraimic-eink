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

    asyncio.run(delivery._async_point_album("upload"))
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
    monkeypatch.setattr(delivery_module.time, "time", lambda: deadline - 1)
    asyncio.run(delivery.async_expire_delivery())
    client.async_update_album.assert_not_awaited()
    monkeypatch.setattr(delivery_module.time, "time", lambda: deadline + 1)
    asyncio.run(delivery.async_expire_delivery())
    asyncio.run(delivery.async_expire_delivery())
    client.async_update_album.assert_awaited_once_with("album", {"active": False})
    assert not delivery.has_image
    asyncio.run(delivery._async_point_album("next"))
    assert client.async_update_album.call_args.args == (
        "album", {"upload_ids": ["next"], "active": True}
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
    from unittest.mock import AsyncMock, Mock

    class GenericStub:
        def __class_getitem__(cls, _item):
            return cls

    stubs = {
        "homeassistant.config_entries": {"ConfigEntry": GenericStub},
        "homeassistant.const": {"CONF_HOST": "host"},
        "homeassistant.core": {"HomeAssistant": object, "callback": lambda fn: fn},
        "homeassistant.helpers.aiohttp_client": {"async_get_clientsession": Mock()},
        "homeassistant.helpers.update_coordinator": {
            "DataUpdateCoordinator": GenericStub, "UpdateFailed": RuntimeError,
        },
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
    coordinator.client = types.SimpleNamespace(get_info=AsyncMock(side_effect=[
        {"battery_pct": 80}, coordinator_module.FraimicConnectionError("asleep"),
    ]))
    coordinator._cloud_snapshot = (time.time(), {"battery": {"percent": 20}})
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
