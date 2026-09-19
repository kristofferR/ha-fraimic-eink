"""Tests for service orchestration without importing Home Assistant."""

from __future__ import annotations

import asyncio
import hashlib
import sys
import types
from types import SimpleNamespace

import pytest
from conftest import load


def _install_ha_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    aiohttp = types.ModuleType("aiohttp")
    homeassistant = types.ModuleType("homeassistant")
    config_entries = types.ModuleType("homeassistant.config_entries")
    core = types.ModuleType("homeassistant.core")
    exceptions = types.ModuleType("homeassistant.exceptions")
    helpers = types.ModuleType("homeassistant.helpers")
    config_validation = types.ModuleType("homeassistant.helpers.config_validation")

    class ConfigEntryState:
        LOADED = object()

    class HomeAssistant:
        pass

    class ServiceCall:
        pass

    class SupportsResponse:
        OPTIONAL = object()
        ONLY = object()

    class HomeAssistantError(Exception):
        pass

    class ServiceValidationError(HomeAssistantError):
        pass

    config_entries.ConfigEntryState = ConfigEntryState
    core.HomeAssistant = HomeAssistant
    core.ServiceCall = ServiceCall
    core.ServiceResponse = dict
    core.SupportsResponse = SupportsResponse
    exceptions.HomeAssistantError = HomeAssistantError
    exceptions.ServiceValidationError = ServiceValidationError
    config_validation.string = str
    config_validation.url = str
    config_validation.entity_id = str
    config_validation.boolean = bool
    config_validation.datetime = lambda value: value
    helpers.config_validation = config_validation
    homeassistant.config_entries = config_entries
    homeassistant.core = core
    homeassistant.exceptions = exceptions
    homeassistant.helpers = helpers
    aiohttp.ClientError = OSError
    aiohttp.ClientTimeout = object

    monkeypatch.setitem(sys.modules, "aiohttp", aiohttp)
    monkeypatch.setitem(sys.modules, "homeassistant", homeassistant)
    monkeypatch.setitem(sys.modules, "homeassistant.config_entries", config_entries)
    monkeypatch.setitem(sys.modules, "homeassistant.core", core)
    monkeypatch.setitem(sys.modules, "homeassistant.exceptions", exceptions)
    monkeypatch.setitem(sys.modules, "homeassistant.helpers", helpers)
    monkeypatch.setitem(
        sys.modules, "homeassistant.helpers.config_validation", config_validation
    )


def _load_services(monkeypatch: pytest.MonkeyPatch):
    _install_ha_stubs(monkeypatch)
    coordinator = types.ModuleType("fraimic.coordinator")
    coordinator.FraimicConfigEntry = object
    library = types.ModuleType("fraimic.library")
    library.get_library = lambda _hass: None
    render_display = types.ModuleType("fraimic.render.display")
    render_display.async_show_screen = None
    render_schema = types.ModuleType("fraimic.render.schema")
    render_schema.SCREEN_SCHEMA = lambda data: data
    render_schema.ScreenConfig = object
    render_schema.screen_from_dict = lambda data: data
    source = types.ModuleType("fraimic.source")
    source.async_get_source_bytes = None
    screens = types.ModuleType("fraimic.screens")
    screens.AmbiguousScreenNameError = ValueError
    screens.screen_by_key = lambda _entry, _key: None
    scenes = types.ModuleType("fraimic.scenes")
    scenes.get_scene_manager = lambda _hass: None
    scheduled_events = types.ModuleType("fraimic.scheduled_events")
    scheduled_events.RECURRENCE_NONE = "none"
    scheduled_events.RECURRENCES = ("none", "daily", "weekly", "monthly")
    scheduled_events.get_scheduled_events = lambda _hass: None
    monkeypatch.setitem(sys.modules, "fraimic.coordinator", coordinator)
    monkeypatch.setitem(sys.modules, "fraimic.library", library)
    monkeypatch.setitem(sys.modules, "fraimic.render.display", render_display)
    monkeypatch.setitem(sys.modules, "fraimic.render.schema", render_schema)
    monkeypatch.setitem(sys.modules, "fraimic.source", source)
    monkeypatch.setitem(sys.modules, "fraimic.screens", screens)
    monkeypatch.setitem(sys.modules, "fraimic.scenes", scenes)
    monkeypatch.setitem(sys.modules, "fraimic.scheduled_events", scheduled_events)
    for name in (
        "fraimic.services",
    ):
        sys.modules.pop(name, None)
    return load("services")


class _Scheduler:
    busy = False

    def __init__(self) -> None:
        self.events: list[tuple[str, bool | None]] = []

    def begin_external_upload(self) -> None:
        self.events.append(("begin", None))

    def finish_external_upload(self, *, uploaded: bool, hold: bool = True) -> None:
        self.events.append(("finish", uploaded))


def _entry(services) -> SimpleNamespace:
    scheduler = _Scheduler()
    entry = SimpleNamespace(
        domain=services.DOMAIN,
        entry_id="entry-1",
        state=services.ConfigEntryState.LOADED,
        options={},
        runtime_data=SimpleNamespace(scheduler=scheduler),
    )
    entry.scheduler = scheduler
    return entry


def _call(hass: object, data: dict) -> SimpleNamespace:
    return SimpleNamespace(hass=hass, data=data)


def test_upload_image_library_branch_sends_and_releases_hold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    services = _load_services(monkeypatch)
    entry = _entry(services)
    calls: list[tuple[str, object, dict]] = []

    class Library:
        async def async_send_to_entry(
            self, image_id: str, target_entry: object, overrides: dict
        ) -> bool:
            calls.append((image_id, target_entry, overrides))
            return True

    hass = SimpleNamespace(
        config_entries=SimpleNamespace(
            async_entries=lambda _domain: [entry],
            async_get_entry=lambda _entry_id: entry,
        )
    )
    monkeypatch.setattr(services, "get_library", lambda _hass: Library())

    asyncio.run(
        services._async_handle_upload_image(
            _call(hass, {services.ATTR_LIBRARY_IMAGE: "img-1"})
        )
    )

    assert calls == [("img-1", entry, {services.ATTR_LIBRARY_IMAGE: "img-1"})]
    assert entry.scheduler.events == [("begin", None), ("finish", True)]


def test_upload_image_library_branch_releases_hold_when_library_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    services = _load_services(monkeypatch)
    entry = _entry(services)
    hass = SimpleNamespace(
        config_entries=SimpleNamespace(
            async_entries=lambda _domain: [entry],
            async_get_entry=lambda _entry_id: entry,
        )
    )
    monkeypatch.setattr(services, "get_library", lambda _hass: None)

    with pytest.raises(services.ServiceValidationError):
        asyncio.run(
            services._async_handle_upload_image(
                _call(hass, {services.ATTR_LIBRARY_IMAGE: "img-1"})
            )
        )

    assert entry.scheduler.events == [("begin", None), ("finish", False)]


@pytest.mark.parametrize("delivery", ["lan_timeout", "cloud"])
def test_accepted_delivery_updates_only_confirmed_display(
    monkeypatch: pytest.MonkeyPatch,
    delivery,
) -> None:
    services = _load_services(monkeypatch)

    async def convert(*_args: object, **_kwargs: object) -> tuple[bytes, bytes, str]:
        return b"packed", b"preview", "none"

    class Client:
        async def upload_image(self, _data: bytes) -> None:
            raise services.FraimicTimeoutError("redraw response timed out")

    class Power:
        def __init__(self) -> None:
            self.recorded: list[tuple[str, str]] = []

        def begin(self, _trigger: str) -> object:
            return object()

        def skip_reason(self, *_args: object) -> None:
            return None

        async def async_record_upload(self, content_hash: str, trigger: str) -> None:
            self.recorded.append((content_hash, trigger))

        def schedule_sleep(self) -> None:
            return None

        def finish(self, _token: object) -> None:
            return None

    power = Power()
    cloud_deliveries = []

    class Cloud:
        async def async_deliver(self, data, *, title, preview_png):
            cloud_deliveries.append((data, title))

    runtime = SimpleNamespace(
        scheduler=None,
        power=power,
        upload_lock=asyncio.Lock(),
        client=Client(),
        coordinator=SimpleNamespace(data={}),
        send_queue=None,
        last_preview=None,
        displayed_preview=None,
        preview_image=None,
        cloud=Cloud() if delivery == "cloud" else None,
    )

    def set_displayed_preview(preview: bytes, _mode: str) -> None:
        runtime.last_preview = preview
        runtime.displayed_preview = preview

    runtime.set_displayed_preview = set_displayed_preview
    entry = SimpleNamespace(data={}, options={}, runtime_data=runtime)
    monkeypatch.setattr(services, "async_convert_for_entry", convert)

    result = asyncio.run(
        services.async_render_and_upload(
            SimpleNamespace(), entry, b"source", hold_playlist=False
        )
    )

    if delivery == "cloud":
        assert cloud_deliveries == [(b"packed", "image")]
        assert result["uploaded"] is False
        assert result["displayed"] is False
        assert result["queued"] is True
        assert result["cloud_queued"] is True
        assert runtime.displayed_preview is None
        assert power.recorded == []
    else:
        assert result["uploaded"] is True
        assert result["displayed"] is True
        assert runtime.last_preview == b"preview"
        assert runtime.displayed_preview == b"preview"
        assert power.recorded == [(result["content_hash"], services.TRIGGER_MANUAL)]


def test_deferred_render_does_not_replace_displayed_preview(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    services = _load_services(monkeypatch)

    async def convert(*_args: object, **_kwargs: object) -> tuple[bytes, bytes, str]:
        return b"packed", b"deferred-preview", "none"

    class Power:
        def begin(self, _trigger: str) -> object:
            return object()

        def skip_reason(self, *_args: object) -> str:
            return "low_battery"

        def finish(self, _token: object) -> None:
            return None

    entry = SimpleNamespace(
        data={},
        options={},
        runtime_data=SimpleNamespace(
            scheduler=None,
            power=Power(),
            upload_lock=asyncio.Lock(),
            client=SimpleNamespace(),
            coordinator=SimpleNamespace(data={}),
            send_queue=None,
            last_preview=b"current-preview",
            displayed_preview=b"current-preview",
            preview_image=None,
        )
    )
    monkeypatch.setattr(services, "async_convert_for_entry", convert)

    result = asyncio.run(
        services.async_render_and_upload(
            SimpleNamespace(),
            entry,
            b"source",
            hold_playlist=False,
            trigger="playlist",
        )
    )

    assert result["displayed"] is False
    assert entry.runtime_data.last_preview == b"deferred-preview"
    assert entry.runtime_data.displayed_preview == b"current-preview"


def test_duplicate_render_refreshes_versioned_displayed_preview(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    services = _load_services(monkeypatch)

    async def convert(*_args: object, **_kwargs: object) -> tuple[bytes, bytes, str]:
        return b"packed", b"fresh-preview", "none"

    class Power:
        def begin(self, _trigger: str) -> object:
            return object()

        def skip_reason(self, *_args: object) -> str:
            return services.SKIP_DUPLICATE

        def finish(self, _token: object) -> None:
            return None

    refreshed: list[tuple[bytes, str]] = []
    runtime = SimpleNamespace(
        scheduler=None,
        power=Power(),
        upload_lock=asyncio.Lock(),
        client=SimpleNamespace(),
        coordinator=SimpleNamespace(data={}),
        send_queue=None,
        last_preview=b"old-preview",
        displayed_preview=b"old-preview",
        preview_image=None,
    )

    def set_displayed_preview(preview: bytes, mode: str) -> None:
        refreshed.append((preview, mode))
        runtime.last_preview = preview
        runtime.displayed_preview = preview

    runtime.set_displayed_preview = set_displayed_preview
    entry = SimpleNamespace(data={}, options={}, runtime_data=runtime)
    monkeypatch.setattr(services, "async_convert_for_entry", convert)

    result = asyncio.run(
        services.async_render_and_upload(
            SimpleNamespace(), entry, b"source", hold_playlist=False
        )
    )

    assert result["displayed"] is True
    assert result["uploaded"] is False
    assert refreshed == [(b"fresh-preview", "none")]


def test_convert_rejects_invalid_height_before_rendering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    services = _load_services(monkeypatch)
    entry = SimpleNamespace(
        data={services.CONF_WIDTH: 1600, services.CONF_HEIGHT: 1201},
        options={},
    )

    with pytest.raises(services.HomeAssistantError, match="not divisible by 4"):
        asyncio.run(
            services.async_convert_for_entry(SimpleNamespace(), entry, b"source")
        )


@pytest.mark.parametrize('outcome', ['awake', 'asleep', 'probe_timeout', 'upload_timeout', 'upload_error', 'cleanup_error', 'deferred', 'cloud_pending'])
@pytest.mark.parametrize("one_shot", [True, False])
def test_hybrid_selects_once_before_upload(monkeypatch, outcome, one_shot):
    from unittest.mock import AsyncMock, Mock

    services = _load_services(monkeypatch)
    entry = SimpleNamespace(data={}, options={'delivery_mode': 'hybrid'})
    events = []

    async def probe():
        events.append('probe')
        if outcome == 'asleep':
            raise services.FraimicConnectionError('asleep')
        if outcome == 'probe_timeout':
            raise TimeoutError('probe timeout')
        return {'percent': 90}

    async def cancel():
        events.append('cancel')
        if outcome == 'cleanup_error':
            raise services.FraimicCloudError('cloud unavailable')

    async def upload(_data):
        events.append('local')
        assert runtime.sending_preview == (b'preview', 'Artwork')
        if outcome == 'upload_timeout':
            raise services.FraimicTimeoutError('redraw timeout')
        if outcome == 'upload_error':
            raise services.FraimicConnectionError('connection lost during upload')

    async def deliver(_data, *, title, preview_png):
        events.append('cloud')
        assert runtime.sending_preview == (b'preview', 'Artwork')

    power = SimpleNamespace(
        begin=Mock(return_value=1), finish=Mock(),
        skip_reason=Mock(return_value='low_battery' if outcome == 'deferred' else None),
        async_record_upload=AsyncMock(), async_invalidate_display=AsyncMock(),
        schedule_sleep=Mock(),
    )
    runtime = SimpleNamespace(
        power=power, cloud=SimpleNamespace(has_image=outcome == 'cloud_pending', async_deliver=deliver, async_cancel_delivery=cancel),
        client=SimpleNamespace(get_battery=probe, upload_image=upload),
        scheduler=None, coordinator=SimpleNamespace(
            data={'battery': {'percent': 1, 'cycles': 50}, 'device': {'name': 'Frame'}},
            async_set_frame_online=Mock(),
        ), upload_lock=asyncio.Lock(),
        send_queue=Mock(), set_displayed_preview=Mock(), last_preview=None, preview_image=None,
    )
    entry.runtime_data = runtime
    call = services.async_render_and_upload(
        None, entry, b'', rendered=(b'packed', b'preview', 'none'),
        queue_if_asleep=one_shot, hold_playlist=False,
        # A previous locally displayed scheduler hash must not bypass Hybrid's
        # shared power accounting after a cloud image could have replaced it.
        skip_if_hash=hashlib.sha256(b'packed').hexdigest(),
    )
    if outcome in ('upload_error', 'cleanup_error'):
        with pytest.raises(services.HomeAssistantError):
            asyncio.run(call)
        assert events == ['probe', 'cancel'] + (['local'] if outcome == 'upload_error' else [])
        runtime.set_displayed_preview.assert_not_called()
    else:
        result = asyncio.run(call)
        cloud = outcome in ('asleep', 'probe_timeout', 'cloud_pending') or (outcome == 'deferred' and one_shot)
        deferred = outcome == 'deferred' and not one_shot
        assert events == (['cloud'] if outcome == 'cloud_pending' else ['probe', 'cloud'] if cloud else ['probe'] if deferred else ['probe', 'cancel', 'local'])
        assert result['uploaded'] is (not cloud and not deferred)
        assert result['queued'] is cloud
        assert runtime.set_displayed_preview.call_count == int(not cloud and not deferred)
        assert power.async_invalidate_display.await_count == int(cloud)
        assert power.async_record_upload.await_count == int(not cloud and not deferred)
        if outcome in ('asleep', 'probe_timeout', 'cloud_pending'):
            power.skip_reason.assert_not_called()
    online = outcome not in ('asleep', 'probe_timeout')
    if outcome == 'cloud_pending':
        runtime.coordinator.async_set_frame_online.assert_not_called()
    else:
        runtime.coordinator.async_set_frame_online.assert_called_once_with(online)
    if online and outcome != 'cloud_pending':
        snapshot = power.skip_reason.call_args.args[3]
        assert snapshot == {'battery': {'percent': 90, 'cycles': 50}, 'device': {'name': 'Frame'}}
    assert runtime.sending_preview is None
    power.finish.assert_called_once_with(1)
    runtime.send_queue.async_upload_or_queue.assert_not_called()


@pytest.mark.parametrize("state", ["unchanged", "pending", "too_late", "expired_during_render", "briefing_stale_at_wake"])
def test_temporary_overlay_cloud_refresh_does_not_postpone_wake_or_send_stale_content(monkeypatch, state):
    from unittest.mock import AsyncMock, Mock

    services = _load_services(monkeypatch)
    packed = b"same pixels" if state == "unchanged" else b"new pixels"
    controller = SimpleNamespace(
        base=(b"clean art", b"clean preview", "none"), art=None, inherit=True, title="Art",
        submitted_hash=hashlib.sha256(b"same pixels").hexdigest(), submitted_via_cloud=True,
        composed_valid_until=1_120 if state == "briefing_stale_at_wake" else None,
        active=True, expires_at=1_200 if state == "too_late" else 4_000,
        signature=lambda *_: "expired" if state == "expired_during_render" else "active",
        async_compose=AsyncMock(return_value=((packed, b"png", "none"), "active", 1)),
        async_accept=AsyncMock(),
    )
    cloud = SimpleNamespace(
        has_image=state == "pending", delivery_deadline=1_500, wake_interval=300,
        async_deliver=AsyncMock(),
    )
    power = SimpleNamespace(begin=Mock(return_value=1), finish=Mock())
    runtime = SimpleNamespace(
        temporary_overlays=controller, scheduler=None, cloud=cloud, power=power,
        upload_lock=asyncio.Lock(), sending_preview=None,
    )
    monkeypatch.setattr(services.time, "time", lambda: 1_000)
    choose_transport = AsyncMock(return_value=True)
    monkeypatch.setattr(services, "async_use_cloud", choose_transport)
    entry = SimpleNamespace(data={}, options={}, runtime_data=runtime)
    result = asyncio.run(services.async_render_and_upload(
        SimpleNamespace(), entry, b"", hold_playlist=False, overlay_refresh=True,
    ))
    assert result["uploaded"] is False
    assert not result.get("displayed")
    cloud.async_deliver.assert_not_awaited()
    if state == "unchanged":
        assert result["unchanged"]
        controller.async_accept.assert_awaited_once()
        choose_transport.assert_not_awaited()
    else:
        assert result["deferred"]
        assert result["mode"] == "none"
        assert result["content_hash"] == hashlib.sha256(packed).hexdigest()
        controller.async_accept.assert_not_awaited()


def test_active_overlay_reads_updated_data_and_uploads_only_changed_pixels(monkeypatch):
    from unittest.mock import AsyncMock, Mock

    services = _load_services(monkeypatch)
    progress = {"completed": 1}
    power = SimpleNamespace(
        last_hash=None, begin=Mock(return_value=1), finish=Mock(), schedule_sleep=Mock(),
    )
    power.skip_reason = lambda content_hash, *_: services.SKIP_DUPLICATE if power.last_hash == content_hash else None

    async def record(content_hash, _trigger):
        power.last_hash = content_hash

    power.async_record_upload = record

    async def compose(*_args):
        return (f"routine {progress['completed']}/6".encode(), b"png", "none"), "config", 1

    controller = SimpleNamespace(
        base=(b"same art", b"preview", "none"), art=None, inherit=True, title="Art",
        async_compose=compose, async_accept=AsyncMock(), signature=lambda *_: "config",
    )
    client = SimpleNamespace(upload_image=AsyncMock())
    runtime = SimpleNamespace(
        temporary_overlays=controller, scheduler=None, cloud=None, power=power,
        client=client, upload_lock=asyncio.Lock(), coordinator=SimpleNamespace(data={}),
        send_queue=None, set_displayed_preview=Mock(),
    )
    monkeypatch.setattr(services, "async_use_cloud", AsyncMock(return_value=False))
    entry = SimpleNamespace(data={}, options={}, runtime_data=runtime)

    async def run():
        for value in (1, 1, 2):
            progress["completed"] = value
            await services.async_render_and_upload(
                SimpleNamespace(), entry, b"", hold_playlist=False, overlay_refresh=True,
            )

    asyncio.run(run())
    assert [call.args[0] for call in client.upload_image.await_args_list] == [b"routine 1/6", b"routine 2/6"]
    assert controller.base[0] == b"same art"
