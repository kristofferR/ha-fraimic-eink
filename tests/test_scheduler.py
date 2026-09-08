"""Tests for playlist scheduler retry state without importing Home Assistant."""

from __future__ import annotations

import asyncio
import sys
import types
from collections.abc import Callable
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from conftest import load


def _install_scheduler_stubs(monkeypatch: pytest.MonkeyPatch) -> type[Exception]:
    homeassistant = types.ModuleType("homeassistant")
    core = types.ModuleType("homeassistant.core")
    exceptions = types.ModuleType("homeassistant.exceptions")
    helpers = types.ModuleType("homeassistant.helpers")
    event = types.ModuleType("homeassistant.helpers.event")
    storage = types.ModuleType("homeassistant.helpers.storage")
    util = types.ModuleType("homeassistant.util")
    dt = types.ModuleType("homeassistant.util.dt")
    display = types.ModuleType("fraimic.render.display")
    playlist = types.ModuleType("fraimic.render.playlist")
    schema = types.ModuleType("fraimic.render.schema")
    coordinator = types.ModuleType("fraimic.coordinator")
    screens = types.ModuleType("fraimic.screens")
    services = types.ModuleType("fraimic.services")
    # scheduler imports ArtFetchError from providers.ha, which pulls aiohttp —
    # stub it like the other HA-touching neighbours.
    providers = types.ModuleType("fraimic.providers")
    providers_ha = types.ModuleType("fraimic.providers.ha")

    class HomeAssistant:
        pass

    class HomeAssistantError(Exception):
        pass

    class ArtFetchError(HomeAssistantError):
        pass

    class Store:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def async_load(self) -> dict:
            return {}

        async def async_save(self, _data: dict) -> None:
            return None

    class FrameUploadError(Exception):
        pass

    class CloudDeliveryError(Exception):
        pass

    def callback(func: Callable[..., object]) -> Callable[..., object]:
        return func

    def async_track_time_interval(
        _hass: object, _action: Callable[..., object], _interval: timedelta
    ) -> Callable[[], None]:
        return lambda: None

    async def async_show_screen(*_args: object, **_kwargs: object) -> dict:
        raise FrameUploadError("frame asleep")

    core.HomeAssistant = HomeAssistant
    core.callback = callback
    exceptions.HomeAssistantError = HomeAssistantError
    event.async_track_time_interval = async_track_time_interval
    storage.Store = Store
    dt.now = lambda: datetime(2026, 7, 3, 14, 5)
    dt.utcnow = lambda: datetime(2026, 7, 3, 12, 5)
    display.async_show_screen = async_show_screen
    display.discard_prepared_thumbnails = lambda *_args, **_kwargs: None
    display.prepared_thumbnail_fingerprint = (
        lambda _hass, _entry, screen: repr(getattr(screen, "source", None))
    )
    playlist.eligible = lambda *_args, **_kwargs: True
    playlist.next_screen = lambda *_args, **_kwargs: None
    schema.ScreenConfig = SimpleNamespace
    schema.KIND_PICTURE = "picture"
    coordinator.FraimicConfigEntry = SimpleNamespace
    screens.screens_from_entry = lambda _entry: []
    services.FrameUploadError = FrameUploadError
    services.CloudDeliveryError = CloudDeliveryError
    providers.ha = providers_ha
    providers_ha.ArtFetchError = ArtFetchError
    homeassistant.core = core
    homeassistant.exceptions = exceptions
    homeassistant.helpers = helpers
    homeassistant.util = util
    helpers.event = event
    helpers.storage = storage
    util.dt = dt

    for name, module in {
        "homeassistant": homeassistant,
        "homeassistant.core": core,
        "homeassistant.exceptions": exceptions,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.event": event,
        "homeassistant.helpers.storage": storage,
        "homeassistant.util": util,
        "homeassistant.util.dt": dt,
        "fraimic.render.display": display,
        "fraimic.render.playlist": playlist,
        "fraimic.render.schema": schema,
        "fraimic.coordinator": coordinator,
        "fraimic.screens": screens,
        "fraimic.services": services,
        "fraimic.providers": providers,
        "fraimic.providers.ha": providers_ha,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)

    return FrameUploadError


def _load_scheduler(monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    _install_scheduler_stubs(monkeypatch)
    sys.modules.pop("fraimic.scheduler", None)
    return load("scheduler")


def _entry(created: list[tuple[object, str]] | None = None) -> object:
    class Entry:
        entry_id = "entry"
        runtime_data = SimpleNamespace(
            coordinator=SimpleNamespace(
                last_update_success=True,
                async_add_listener=lambda _listener: lambda: None,
                async_set_frame_online=lambda _online: None,
            )
        )

        def async_create_task(
            self, _hass: object, coro: object, name: str
        ) -> None:
            if created is None:
                raise AssertionError("async_create_task was not expected")
            created.append((coro, name))

    return Entry()


def test_prefetch_prepares_only_configured_queue_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    entry = _entry()
    entry.options = {scheduler_mod.CONF_PLAYLIST_PREFETCH: 2}
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), entry)
    screens = [
        SimpleNamespace(
            screen_id=f"screen-{index}",
            name=f"Screen {index}",
            kind="picture",
            source={"provider": "museum", "provider_item": str(index)},
        )
        for index in range(3)
    ]
    scheduler._external_queue = {screen.screen_id: screen for screen in screens}
    scheduler._queued_ids = [screen.screen_id for screen in screens]
    prepared: list[str] = []

    async def prepare(_hass: object, _entry: object, screen: object) -> bool:
        prepared.append(screen.screen_id)
        return True

    sys.modules["fraimic.render.display"].async_prepare_screen = prepare
    asyncio.run(scheduler._async_prefetch())

    assert prepared == ["screen-0", "screen-1"]


def test_prefetch_limit_counts_only_fixed_pictures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    entry = _entry()
    entry.options = {scheduler_mod.CONF_PLAYLIST_PREFETCH: 2}
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), entry)
    screens = [
        SimpleNamespace(
            screen_id="dashboard", name="Dashboard", kind="dashboard", source=None
        ),
        SimpleNamespace(
            screen_id="url",
            name="Live URL",
            kind="picture",
            source={"url": "https://example.test/live.png"},
        ),
        SimpleNamespace(
            screen_id="library",
            name="Library",
            kind="picture",
            source={"library_image": "image-1"},
        ),
        SimpleNamespace(
            screen_id="provider",
            name="Provider",
            kind="picture",
            source={"provider": "museum", "provider_item": "art-1"},
        ),
    ]
    scheduler._external_queue = {screen.screen_id: screen for screen in screens}
    scheduler._queued_ids = [screen.screen_id for screen in screens]

    assert [screen.screen_id for screen in scheduler._prefetch_screens()] == [
        "library",
        "provider",
    ]


def test_assigned_playlist_preprocesses_every_fixed_picture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    entry = _entry()
    entry.options = {scheduler_mod.CONF_PLAYLIST_PREFETCH: 1}
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), entry)
    scheduler.screens = [
        SimpleNamespace(
            screen_id="dashboard", name="Dashboard", kind="dashboard", source=None
        ),
        SimpleNamespace(
            screen_id="library",
            name="Library",
            kind="picture",
            source={"library_image": "image-1"},
        ),
        SimpleNamespace(
            screen_id="live",
            name="Live",
            kind="picture",
            source={"provider": "museum"},
        ),
        SimpleNamespace(
            screen_id="provider",
            name="Provider",
            kind="picture",
            source={"provider": "museum", "provider_item": "art-1"},
        ),
    ]
    prepared: list[str] = []

    async def prepare(_hass: object, _entry: object, screen: object) -> bool:
        prepared.append(screen.screen_id)
        return True

    sys.modules["fraimic.render.display"].async_prepare_screen = prepare
    asyncio.run(scheduler._async_prefetch())
    asyncio.run(scheduler._async_prefetch())

    assert prepared == ["library", "provider"]


def test_prefetch_is_rescheduled_when_external_upload_finishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    scheduled: list[bool] = []
    scheduler._schedule_prefetch = lambda: scheduled.append(True)

    scheduler.begin_external_upload()
    scheduler.finish_external_upload(uploaded=False)

    assert scheduler.external_upload_active is False
    assert scheduled == [True]


def test_prune_library_image_removes_scheduler_owned_references(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    removed = SimpleNamespace(
        screen_id="removed",
        name="Removed",
        kind="picture",
        source={"library_image": "image-1"},
    )
    kept = SimpleNamespace(
        screen_id="kept",
        name="Kept",
        kind="picture",
        source={"library_image": "image-2"},
    )
    scheduler._external_queue = {"removed": removed, "kept": kept}
    scheduler._external_queue_data = {
        "removed": {"library_image": "image-1"},
        "kept": {"library_image": "image-2"},
    }
    scheduler._queued_ids = ["removed", "kept", "removed"]
    scheduler.current_id = "removed"
    scheduler._playlist_cursor_id = "removed"
    scheduler._pending = removed
    scheduler._pending_from_queue = True

    changed = asyncio.run(scheduler.async_prune_library_image("image-1"))

    assert changed is True
    assert scheduler._queued_ids == ["kept"]
    assert scheduler.current_id is None
    assert scheduler._playlist_cursor_id is None
    assert scheduler._pending is None
    assert scheduler._pending_from_queue is False
    assert scheduler._external_queue == {"kept": kept}
    assert scheduler._external_queue_data == {
        "kept": {"library_image": "image-2"}
    }


def test_prune_library_image_removes_legacy_screen_subentry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    removed_subentries: list[str] = []
    hass = SimpleNamespace(
        config_entries=SimpleNamespace(
            async_remove_subentry=lambda _entry, screen_id: removed_subentries.append(
                screen_id
            )
        )
    )
    entry = _entry()
    entry.subentries = {"legacy": object()}
    scheduler = scheduler_mod.FraimicScheduler(hass, entry)
    legacy = SimpleNamespace(
        screen_id="legacy",
        name="Legacy",
        kind="picture",
        source={"library_image": "image-1"},
    )
    kept = SimpleNamespace(
        screen_id="kept",
        name="Kept",
        kind="dashboard",
        source=None,
    )
    scheduler.screens = [legacy, kept]
    scheduler._playback_order = ["legacy", "kept"]
    scheduler._playlist_order = ["legacy", "kept"]

    changed = asyncio.run(scheduler.async_prune_library_image("image-1"))

    assert changed is True
    assert removed_subentries == ["legacy"]
    assert scheduler.screens == [kept]
    assert scheduler._playback_order == ["kept"]
    assert scheduler._playlist_order == ["kept"]


@pytest.mark.parametrize("queued", [False, True])
def test_cloud_acceptance_advances_delivery_without_claiming_display(monkeypatch, queued):
    scheduler_mod = _load_scheduler(monkeypatch)
    entry = _entry()
    entry.runtime_data.cloud = SimpleNamespace(wake_interval=1920)
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), entry)
    old = SimpleNamespace(screen_id="old", name="Old", interval=1800)
    new = SimpleNamespace(screen_id="new", name="New", interval=1800)
    scheduler.screens = [old, new]
    scheduler.enabled = True
    scheduler.current_id = "old"
    scheduler.displayed_hash = "old-hash"
    scheduler._playlist_cursor_id = "old"
    if queued:
        scheduler._queued_ids = ["new"]
    deliveries = []

    async def show(*_args, **_kwargs):
        deliveries.append("accepted")
        await scheduler.async_cloud_delivery_accepted()
        return {"uploaded": False, "displayed": False, "cloud_queued": True}

    monkeypatch.setattr(scheduler_mod, "async_show_screen", show)

    async def scenario():
        if queued:
            await scheduler._async_show_queued(new, manual=False)
        else:
            await scheduler._async_show(new)
        await scheduler._async_rotate(force=False)

    asyncio.run(scenario())
    assert deliveries == ["accepted"]
    assert scheduler.current_id == "old"
    assert scheduler.displayed_hash == "old-hash"
    assert scheduler._last_rotation is None
    assert scheduler._playlist_cursor_id == ("old" if queued else "new")
    assert scheduler._queued_ids == []
    assert scheduler._hold_until == scheduler_mod.dt_util.utcnow() + timedelta(seconds=1980)


def test_paused_scheduler_still_retires_cloud_images(monkeypatch):
    from unittest.mock import AsyncMock

    scheduler_mod = _load_scheduler(monkeypatch)
    entry = _entry()
    expire = AsyncMock()
    entry.runtime_data.cloud = SimpleNamespace(async_expire_delivery=expire)
    entry.runtime_data.upload_lock = asyncio.Lock()
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), entry)
    scheduler.enabled = False
    asyncio.run(scheduler._async_tick())
    expire.assert_awaited_once()


def test_cloud_interval_sync_rebases_existing_hold(monkeypatch):
    scheduler_mod = _load_scheduler(monkeypatch)
    entry = _entry()
    cloud = SimpleNamespace(delivery_deadline=1000)

    async def sync(_interval):
        cloud.delivery_deadline = 2000

    cloud.async_sync_interval = sync
    entry.runtime_data.cloud = cloud
    monkeypatch.setattr(scheduler_mod.dt_util, "utc_from_timestamp", datetime.fromtimestamp, raising=False)
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), entry)
    scheduler._hold_until = datetime.fromtimestamp(1000)
    asyncio.run(scheduler._async_sync_cloud_interval())
    assert scheduler._hold_until == datetime.fromtimestamp(2000)


def test_wake_retry_keeps_manual_pending_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    created: list[tuple[object, str]] = []

    screen = SimpleNamespace(screen_id="screen-1", name="Manual")
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry(created))
    scheduler.enabled = False
    scheduler._pending = screen
    scheduler._pending_requires_enabled = False

    scheduler._coordinator_updated()

    assert [name for _, name in created] == ["fraimic_playlist_wake_push"]
    asyncio.run(created[0][0])
    assert scheduler._pending is screen
    assert scheduler._pending_requires_enabled is False


def test_named_playlist_assignment_and_global_queue_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    assigned = SimpleNamespace(
        playlist_id="playlist-1",
        name="Weekends",
        interval=1800,
        shuffle=False,
    )
    active = SimpleNamespace(screen_id="active", name="Active", interval=1800)
    second = SimpleNamespace(screen_id="second", name="Second", interval=1800)
    queued = SimpleNamespace(screen_id="queued", name="Queued", interval=1800)

    class Playlists:
        def assigned_to(self, entry_id: str) -> object:
            assert entry_id == "entry"
            return assigned

        def render_slides(self, playlist_id: str) -> list[object]:
            assert playlist_id == "playlist-1"
            return [active, second]

        def get(self, playlist_id: str) -> object:
            assert playlist_id == "playlist-1"
            return assigned

        def render_slide_by_id(self, slide_id: str) -> object | None:
            return queued if slide_id == "queued" else None

    scheduler = scheduler_mod.FraimicScheduler(
        SimpleNamespace(), _entry(), Playlists()
    )
    scheduler._queued_ids = ["queued"]

    assert scheduler.playlist_id == "playlist-1"
    assert scheduler.playlist_name == "Weekends"
    assert scheduler.playlist_interval == 1800
    assert scheduler.queued_slides == [queued]
    assert scheduler.shuffle is False
    assert scheduler.screens == [active, second]

    scheduler._queued_ids.append("missing")
    scheduler._playlist_preprocess_done = "prepared"
    asyncio.run(scheduler.async_refresh_playlist())
    assert scheduler._queued_ids == ["queued"]
    assert scheduler._playlist_preprocess_done == "prepared"

    assigned.shuffle = True
    monkeypatch.setattr(scheduler_mod.random, "shuffle", lambda items: items.reverse())
    scheduler._load_assigned_playlist()

    assert scheduler.shuffle is True
    assert scheduler.screens == [active, second]
    assert scheduler._rotation_screens() == [second, active]

    # A settings refresh must not reshuffle the session order.
    scheduler._load_assigned_playlist()
    assert scheduler._rotation_screens() == [second, active]


def test_new_pending_screen_requires_enabled_after_upload_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    old_screen = SimpleNamespace(screen_id="screen-1", name="Old")
    new_screen = SimpleNamespace(screen_id="screen-2", name="New")
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    scheduler._pending = old_screen
    scheduler._pending_requires_enabled = False

    asyncio.run(scheduler._async_show(new_screen, manual=False))

    assert scheduler._pending is new_screen
    assert scheduler._pending_requires_enabled is True


def test_direct_send_suppresses_automatic_wake_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    screen = SimpleNamespace(screen_id="screen-1", name="Automatic")
    entry = _entry()
    entry.runtime_data.send_queue = SimpleNamespace(pending={"title": "Direct send"})
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), entry)

    asyncio.run(scheduler._async_show(screen, manual=False))

    assert scheduler._pending is None


def test_manual_queue_retry_is_persisted_while_frame_sleeps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    screen = SimpleNamespace(screen_id="screen-1", name="Manual")
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    scheduler.screens = [screen]
    scheduler._queued_ids = [screen.screen_id]
    saved: list[dict] = []

    class Store:
        async def async_save(self, data: dict) -> None:
            saved.append(dict(data))

    scheduler._store = Store()

    asyncio.run(scheduler._async_show_queued(screen, manual=True))

    assert saved[-1]["pending_queue_id"] == screen.screen_id
    assert saved[-1]["pending_requires_enabled"] is False


def test_start_restores_manual_queue_retry_while_paused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    screen = SimpleNamespace(screen_id="screen-1", name="Manual")
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    scheduler.screens = [screen]

    class Store:
        async def async_load(self) -> dict:
            return {
                "enabled": False,
                "queued_slide_ids": [screen.screen_id],
                "pending_queue_id": screen.screen_id,
                "pending_requires_enabled": False,
            }

    scheduler._store = Store()

    asyncio.run(scheduler.async_start())

    assert scheduler._pending is screen
    assert scheduler._pending_from_queue is True
    assert scheduler._pending_requires_enabled is False


def test_successful_wake_retry_clears_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    screen = SimpleNamespace(screen_id="screen-1", name="Manual")
    hold_until = datetime(2026, 7, 3, 12, 35)

    async def async_show_screen(*_args: object, **_kwargs: object) -> dict:
        return {"uploaded": True, "content_hash": "hash123"}

    monkeypatch.setattr(scheduler_mod, "async_show_screen", async_show_screen)
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    scheduler._pending = screen
    scheduler._pending_requires_enabled = False
    scheduler._hold_until = hold_until

    asyncio.run(scheduler._async_retry_pending(screen))

    assert scheduler._pending is None
    assert scheduler.current_id == "screen-1"
    assert scheduler.displayed_hash == "hash123"
    assert scheduler._hold_until is None


def test_external_one_off_holds_without_advancing_playlist_cursor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    catalog = SimpleNamespace(screen_id="catalog", name="Catalog", interval=1800)
    external = SimpleNamespace(screen_id="external", name="External", interval=900)

    async def async_show_screen(*_args: object, **_kwargs: object) -> dict:
        return {"uploaded": True, "content_hash": "external-hash"}

    monkeypatch.setattr(scheduler_mod, "async_show_screen", async_show_screen)
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    scheduler.screens = [catalog]
    scheduler._playlist_cursor_id = catalog.screen_id

    asyncio.run(scheduler.async_select(external, hold=True))

    assert scheduler.current_id == external.screen_id
    assert scheduler._playlist_cursor_id == catalog.screen_id
    assert scheduler._hold_until == datetime(2026, 7, 3, 12, 20)


def test_external_one_off_remains_current_during_hold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    catalog = SimpleNamespace(screen_id="catalog", name="Catalog", interval=1800)
    external = SimpleNamespace(screen_id="external", name="External", interval=900)
    playlists = SimpleNamespace(
        assigned_to=lambda _entry_id: None,
        render_slides=lambda _playlist_id: [],
        render_slide_by_id=lambda slide_id: external if slide_id == "external" else None,
        get=lambda _playlist_id: None,
    )

    async def async_show_screen(*_args: object, **_kwargs: object) -> dict:
        return {"uploaded": True, "content_hash": "external-hash"}

    monkeypatch.setattr(scheduler_mod, "async_show_screen", async_show_screen)
    scheduler = scheduler_mod.FraimicScheduler(
        SimpleNamespace(), _entry(), playlists=playlists
    )
    scheduler.screens = [catalog]
    scheduler._playlist_cursor_id = catalog.screen_id

    asyncio.run(scheduler.async_select(external, hold=True))

    assert scheduler.current_screen is external


def test_playlist_refresh_replaces_or_clears_pending_slide(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    playlist = SimpleNamespace(
        playlist_id="playlist-1",
        name="Gallery",
        interval=1800,
        shuffle=False,
    )
    current = SimpleNamespace(screen_id="current", name="Current", interval=1800)
    pending = SimpleNamespace(screen_id="pending", name="Old", interval=1800)
    replacement = SimpleNamespace(
        screen_id="pending", name="Updated", interval=1800
    )

    class Playlists:
        slides = [current, pending]

        def assigned_to(self, _entry_id: str) -> object:
            return playlist

        def render_slides(self, _playlist_id: str) -> list[object]:
            return list(self.slides)

        def get(self, _playlist_id: str) -> object:
            return playlist

        def render_slide_by_id(self, slide_id: str) -> object | None:
            return next(
                (slide for slide in self.slides if slide.screen_id == slide_id),
                None,
            )

    playlists = Playlists()
    scheduler = scheduler_mod.FraimicScheduler(
        SimpleNamespace(), _entry(), playlists
    )
    scheduler.current_id = current.screen_id
    scheduler._pending = pending
    playlists.slides = [current, replacement]

    asyncio.run(scheduler.async_refresh_playlist())
    assert scheduler._pending is replacement

    playlists.slides = [current]
    asyncio.run(scheduler.async_refresh_playlist())
    assert scheduler._pending is None


def test_playlist_refresh_preserves_displayed_external_slide(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    playlist = SimpleNamespace(
        playlist_id="playlist-1",
        name="Gallery",
        interval=1800,
        shuffle=False,
    )
    catalog = SimpleNamespace(screen_id="catalog", name="Catalog", interval=1800)
    external = SimpleNamespace(screen_id="external", name="External", interval=900)

    class Playlists:
        def assigned_to(self, _entry_id: str) -> object:
            return playlist

        def render_slides(self, _playlist_id: str) -> list[object]:
            return [catalog]

        def get(self, _playlist_id: str) -> object:
            return playlist

        def render_slide_by_id(self, _slide_id: str) -> None:
            return None

    scheduler = scheduler_mod.FraimicScheduler(
        SimpleNamespace(), _entry(), Playlists()
    )
    scheduler._external_queue[external.screen_id] = external
    scheduler._external_queue_data[external.screen_id] = {"name": "External"}
    scheduler.current_id = external.screen_id
    scheduler._playlist_cursor_id = catalog.screen_id

    asyncio.run(scheduler.async_refresh_playlist())

    assert scheduler.current_screen is external
    assert scheduler.current_id == external.screen_id
    assert scheduler._playlist_cursor_id == catalog.screen_id


def test_power_deferred_screen_does_not_replace_displayed_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    current = SimpleNamespace(screen_id="current", name="Current", interval=1800)
    deferred = SimpleNamespace(screen_id="next", name="Next", interval=1800)

    async def async_show_screen(*_args: object, **_kwargs: object) -> dict:
        return {
            "uploaded": False,
            "displayed": False,
            "content_hash": "not-on-glass",
            "skip_reason": "low_battery",
        }

    monkeypatch.setattr(scheduler_mod, "async_show_screen", async_show_screen)
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    scheduler.screens = [current, deferred]
    scheduler.current_id = current.screen_id
    scheduler.displayed_hash = "on-glass"
    original_rotation = datetime(2026, 7, 3, 11, 0)
    scheduler._last_rotation = original_rotation

    asyncio.run(scheduler._async_show(deferred))

    assert scheduler.current_id == current.screen_id
    assert scheduler.displayed_hash == "on-glass"
    assert scheduler._last_rotation == original_rotation


def test_rejected_automatic_slide_keeps_displayed_screen_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    current = SimpleNamespace(screen_id="current", name="Current", interval=1800)
    rejected = SimpleNamespace(screen_id="rejected", name="Rejected", interval=1800)

    async def async_show_screen(*_args: object, **_kwargs: object) -> dict:
        raise scheduler_mod.HomeAssistantError("render failed")

    monkeypatch.setattr(scheduler_mod, "async_show_screen", async_show_screen)
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    scheduler.screens = [current, rejected]
    scheduler.current_id = current.screen_id
    scheduler._playlist_cursor_id = current.screen_id
    scheduler.displayed_hash = "on-glass"

    displayed = asyncio.run(scheduler._async_show(rejected, manual=False))

    assert displayed is False
    assert scheduler.current_id == current.screen_id
    assert scheduler._playlist_cursor_id == rejected.screen_id
    assert scheduler.displayed_hash == "on-glass"


def test_queue_success_is_consumed_in_display_state_save(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    queued = SimpleNamespace(screen_id="queued", name="Queued", interval=1800)

    async def async_show_screen(*_args: object, **_kwargs: object) -> dict:
        return {"uploaded": True, "content_hash": "queued-hash"}

    monkeypatch.setattr(scheduler_mod, "async_show_screen", async_show_screen)
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    scheduler.screens = [queued]
    scheduler._queued_ids = [queued.screen_id]
    saved: list[dict] = []

    class Store:
        async def async_save(self, data: dict) -> None:
            saved.append(dict(data))

    scheduler._store = Store()

    asyncio.run(scheduler._async_show_queued(queued, manual=False))

    assert len(saved) == 1
    assert saved[0]["current_screen_id"] == queued.screen_id
    assert saved[0]["queued_slide_ids"] == []


def test_wake_retry_rechecks_enabled_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    screen = SimpleNamespace(screen_id="screen-1", name="Automatic")

    async def async_show_screen(*_args: object, **_kwargs: object) -> dict:
        raise AssertionError("disabled playlist should not retry upload")

    monkeypatch.setattr(scheduler_mod, "async_show_screen", async_show_screen)
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    scheduler.enabled = False
    scheduler._pending = screen
    scheduler._pending_requires_enabled = True

    asyncio.run(scheduler._async_retry_pending(screen))

    assert scheduler._pending is screen


def test_save_persists_manual_upload_hold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    hold_until = datetime(2026, 7, 3, 12, 35)
    saved: dict = {}

    class Store:
        async def async_save(self, data: dict) -> None:
            saved.update(data)

    scheduler._store = Store()
    scheduler._hold_until = hold_until

    asyncio.run(scheduler._async_save())

    assert saved["hold_until"] == hold_until.isoformat()


def test_set_enabled_can_preserve_manual_upload_hold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    hold_until = datetime(2026, 7, 3, 12, 35)
    scheduler.enabled = True
    scheduler._hold_until = hold_until

    asyncio.run(scheduler.async_set_enabled(False, clear_hold=False))
    assert scheduler.enabled is False
    assert scheduler._hold_until == hold_until

    asyncio.run(scheduler.async_set_enabled(True, rotate=False, clear_hold=False))
    assert scheduler.enabled is True
    assert scheduler._hold_until == hold_until


def test_set_enabled_can_skip_persistence_for_camera_pause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    saved: list[dict] = []
    scheduler.enabled = True
    scheduler._stored_enabled = True

    class Store:
        async def async_save(self, data: dict) -> None:
            saved.append(dict(data))

    scheduler._store = Store()

    asyncio.run(scheduler.async_set_enabled(False, persist=False))
    assert scheduler.enabled is False
    assert scheduler.stored_enabled is True
    assert saved == []

    asyncio.run(scheduler.async_set_enabled(False))
    assert saved[-1]["enabled"] is False
    assert scheduler.stored_enabled is False


def test_enabling_playlist_respects_fresh_current_screen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    current = SimpleNamespace(screen_id="screen-1", name="Current", interval=1800)
    other = SimpleNamespace(screen_id="screen-2", name="Other", interval=1800)

    async def async_show_screen(*_args: object, **_kwargs: object) -> dict:
        raise AssertionError("fresh current screen should not be overwritten")

    monkeypatch.setattr(scheduler_mod, "async_show_screen", async_show_screen)
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    scheduler.screens = [current, other]
    scheduler.enabled = False
    scheduler.current_id = "screen-1"
    scheduler.displayed_hash = "hash123"
    scheduler._last_rotation = datetime(2026, 7, 3, 12, 0)

    asyncio.run(scheduler.async_set_enabled(True))

    assert scheduler.enabled is True
    assert scheduler.current_id == "screen-1"


def test_pause_freezes_remaining_playlist_interval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    current = SimpleNamespace(screen_id="screen-1", name="Current", interval=1800)

    async def async_show_screen(*_args: object, **_kwargs: object) -> dict:
        raise AssertionError("resuming a paused interval must not advance")

    monkeypatch.setattr(scheduler_mod, "async_show_screen", async_show_screen)
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    scheduler.screens = [current]
    scheduler.enabled = True
    scheduler.current_id = current.screen_id
    scheduler.displayed_hash = "hash123"
    scheduler._last_rotation = datetime(2026, 7, 3, 12, 0)

    asyncio.run(scheduler.async_set_enabled(False))
    assert scheduler.last_rotation == datetime(2026, 7, 3, 12, 0)

    monkeypatch.setattr(
        scheduler_mod.dt_util,
        "utcnow",
        lambda: datetime(2026, 7, 3, 13, 5),
    )
    asyncio.run(scheduler.async_set_enabled(True))

    assert scheduler.enabled is True
    assert scheduler._last_rotation == datetime(2026, 7, 3, 13, 0)


def test_enabling_playlist_retries_pending_wake_push(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    screen = SimpleNamespace(screen_id="screen-1", name="Pending", interval=1800)
    uploads: list[str] = []

    async def async_show_screen(
        _hass: object, _entry: object, screen: object, **_kwargs: object
    ) -> dict:
        uploads.append(screen.screen_id)
        return {"uploaded": True, "content_hash": "hash456"}

    monkeypatch.setattr(scheduler_mod, "async_show_screen", async_show_screen)
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    scheduler.screens = [screen]
    scheduler.enabled = False
    scheduler._pending = screen
    scheduler._pending_requires_enabled = True

    asyncio.run(scheduler.async_set_enabled(True))

    assert uploads == ["screen-1"]
    assert scheduler._pending is None
    assert scheduler.displayed_hash == "hash456"


def test_enabling_playlist_retakes_unknown_displayed_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    current = SimpleNamespace(screen_id="screen-1", name="Current", interval=1800)
    uploads: list[str] = []

    async def async_show_screen(
        _hass: object, _entry: object, screen: object, **_kwargs: object
    ) -> dict:
        uploads.append(screen.screen_id)
        return {"uploaded": True, "content_hash": "hash456"}

    monkeypatch.setattr(scheduler_mod, "async_show_screen", async_show_screen)
    monkeypatch.setattr(
        scheduler_mod, "next_screen", lambda screens, *_args, **_kwargs: screens[0]
    )
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    scheduler.screens = [current]
    scheduler.enabled = False
    scheduler.current_id = "screen-1"
    scheduler.displayed_hash = None
    scheduler._last_rotation = datetime(2026, 7, 3, 12, 0)

    asyncio.run(scheduler.async_set_enabled(True))

    assert uploads == ["screen-1"]
    assert scheduler.displayed_hash == "hash456"


def test_external_upload_can_invalidate_hash_without_hold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    created: list[tuple[object, str]] = []
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry(created))
    saved: list[dict] = []
    scheduler.enabled = True
    scheduler._stored_enabled = True
    scheduler.displayed_hash = "hash123"

    class Store:
        async def async_save(self, data: dict) -> None:
            saved.append(dict(data))

    scheduler._store = Store()
    asyncio.run(scheduler.async_set_enabled(False, persist=False))
    scheduler.begin_external_upload()

    scheduler.finish_external_upload(uploaded=True, hold=False)

    assert scheduler.external_upload_active is False
    assert scheduler.displayed_hash is None
    assert scheduler._hold_until is None
    asyncio.run(created[0][0])
    assert saved[-1]["enabled"] is True


def test_new_direct_send_discards_pending_scheduler_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    scheduler._pending = SimpleNamespace(screen_id="older")
    scheduler._pending_from_queue = True
    scheduler._pending_hold_on_success = True
    saved: list[dict] = []

    class Store:
        async def async_save(self, data: dict) -> None:
            saved.append(dict(data))

    scheduler._store = Store()

    asyncio.run(scheduler.async_discard_pending_retry())

    assert scheduler._pending is None
    assert scheduler._pending_from_queue is False
    assert scheduler._pending_hold_on_success is False
    assert saved[-1]["pending_queue_id"] is None


def test_deferred_external_delivery_resets_scheduler_durably(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    current = SimpleNamespace(screen_id="current", interval=900)
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    scheduler.screens = [current]
    scheduler.current_id = current.screen_id
    scheduler.displayed_hash = "old-hash"
    scheduler._pending_hold_on_success = True
    saved: list[dict] = []

    class Store:
        async def async_save(self, data: dict) -> None:
            saved.append(dict(data))

    scheduler._store = Store()

    asyncio.run(scheduler.async_notify_external_upload())

    assert scheduler.displayed_hash is None
    assert scheduler._pending_hold_on_success is False
    assert scheduler.hold_until == datetime(2026, 7, 3, 12, 20)
    assert saved[-1]["displayed_hash"] is None


def test_manual_screen_control_blocked_during_external_upload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    hold_until = datetime(2026, 7, 3, 12, 35)
    screen = SimpleNamespace(screen_id="screen-1", name="Manual")
    scheduler._hold_until = hold_until
    scheduler.begin_external_upload()

    with pytest.raises(scheduler_mod.HomeAssistantError, match="upload"):
        asyncio.run(scheduler.async_select(screen))

    assert scheduler._hold_until == hold_until


def test_upload_guard_raises_during_external_upload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    scheduler.begin_external_upload()

    with pytest.raises(scheduler_mod.HomeAssistantError, match="upload"):
        scheduler.raise_if_upload_active()


def test_failed_manual_screen_render_preserves_hold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    hold_until = datetime(2026, 7, 3, 12, 35)
    screen = SimpleNamespace(screen_id="screen-1", name="Broken")

    async def async_show_screen(*_args: object, **_kwargs: object) -> dict:
        raise scheduler_mod.HomeAssistantError("render failed")

    monkeypatch.setattr(scheduler_mod, "async_show_screen", async_show_screen)
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    scheduler._hold_until = hold_until

    with pytest.raises(scheduler_mod.HomeAssistantError, match="render failed"):
        asyncio.run(scheduler.async_select(screen))

    assert scheduler._hold_until == hold_until


def test_failed_manual_online_fetch_preserves_hold_and_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    hold_until = datetime(2026, 7, 3, 12, 35)
    screen = SimpleNamespace(screen_id="screen-1", name="Broken online")

    async def async_show_screen(*_args: object, **_kwargs: object) -> dict:
        raise scheduler_mod.ArtFetchError("provider failed")

    monkeypatch.setattr(scheduler_mod, "async_show_screen", async_show_screen)
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    scheduler._hold_until = hold_until

    with pytest.raises(scheduler_mod.ArtFetchError, match="provider failed"):
        asyncio.run(scheduler.async_select(screen))

    assert scheduler._hold_until == hold_until


def test_automatic_wake_retry_skips_closed_screen_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    screen = SimpleNamespace(screen_id="screen-1", name="Closed")

    async def async_show_screen(*_args: object, **_kwargs: object) -> dict:
        raise AssertionError("closed screen window should not upload")

    monkeypatch.setattr(scheduler_mod, "async_show_screen", async_show_screen)
    monkeypatch.setattr(scheduler_mod, "eligible", lambda *_args: False)
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    scheduler.enabled = True
    scheduler._pending = screen
    scheduler._pending_requires_enabled = True

    asyncio.run(scheduler._async_retry_pending(screen))

    assert scheduler._pending is None


def test_queue_and_playlist_order_restore_from_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    first = SimpleNamespace(screen_id="first", name="First")
    second = SimpleNamespace(screen_id="second", name="Second")
    third = SimpleNamespace(screen_id="third", name="Third")
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    scheduler.screens = [first, second, third]

    class Store:
        async def async_load(self) -> dict:
            return {
                "queued_slide_ids": ["third", "missing", "third"],
                "playlist_order": ["second", "first"],
            }

        async def async_save(self, _data: dict) -> None:
            return None

    scheduler._store = Store()
    asyncio.run(scheduler.async_start())

    assert [slide.screen_id for slide in scheduler.screens] == [
        "second",
        "first",
        "third",
    ]
    assert [slide.screen_id for slide in scheduler.queued_slides] == [
        "third",
        "third",
    ]


def test_hand_queue_consumes_once_without_moving_playlist_cursor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    first = SimpleNamespace(screen_id="first", name="First", interval=1800)
    second = SimpleNamespace(screen_id="second", name="Second", interval=1800)
    queued = SimpleNamespace(screen_id="queued", name="Queued", interval=1800)
    saved: list[dict] = []

    def next_screen(
        screens: list[SimpleNamespace],
        current_id: str | None,
        *_args: object,
        **_kwargs: object,
    ) -> SimpleNamespace:
        ids = [slide.screen_id for slide in screens]
        start = ids.index(current_id) if current_id in ids else -1
        return screens[(start + 1) % len(screens)]

    async def async_show_screen(*_args: object, **_kwargs: object) -> dict:
        return {"uploaded": True, "content_hash": "shown"}

    class Store:
        async def async_save(self, data: dict) -> None:
            saved.append(dict(data))

    monkeypatch.setattr(scheduler_mod, "next_screen", next_screen)
    monkeypatch.setattr(scheduler_mod, "async_show_screen", async_show_screen)
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    scheduler.screens = [first, second, queued]
    scheduler.current_id = first.screen_id
    scheduler._playlist_cursor_id = first.screen_id
    scheduler._queued_ids = [queued.screen_id]
    scheduler._store = Store()

    asyncio.run(scheduler.async_next())

    assert scheduler.current_id == queued.screen_id
    assert scheduler._playlist_cursor_id == first.screen_id
    assert scheduler.queued_slides == []
    assert [slide.screen_id for slide in scheduler.playlist_up_next()] == [
        second.screen_id,
        queued.screen_id,
    ]
    assert saved[-1]["playlist_cursor_id"] == first.screen_id
    assert saved[-1]["queued_slide_ids"] == []

    asyncio.run(scheduler.async_previous())

    assert scheduler.current_id == first.screen_id
    assert scheduler._playlist_cursor_id == first.screen_id


def test_sleeping_queued_slide_is_consumed_only_after_wake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    current = SimpleNamespace(screen_id="current", name="Current", interval=1800)
    queued = SimpleNamespace(screen_id="queued", name="Queued", interval=1800)
    entry = _entry()
    discarded: list[bool] = []

    class SendQueue:
        pending = {"title": "Older picture"}

        async def async_discard(self) -> None:
            discarded.append(True)

    entry.runtime_data.send_queue = SendQueue()
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), entry)
    scheduler.screens = [current, queued]
    scheduler.current_id = current.screen_id
    scheduler._playlist_cursor_id = current.screen_id
    scheduler._queued_ids = [queued.screen_id]

    asyncio.run(scheduler.async_next())

    assert scheduler._pending is queued
    assert scheduler._pending_from_queue is True
    assert discarded == [True]
    assert [slide.screen_id for slide in scheduler.queued_slides] == [queued.screen_id]

    async def async_show_screen(*_args: object, **_kwargs: object) -> dict:
        return {"uploaded": True, "content_hash": "shown"}

    monkeypatch.setattr(scheduler_mod, "async_show_screen", async_show_screen)
    asyncio.run(scheduler._async_retry_pending(queued))

    assert scheduler._pending is None
    assert scheduler.queued_slides == []
    assert scheduler.current_id == queued.screen_id


def test_play_next_supersedes_automatic_wake_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    automatic = SimpleNamespace(screen_id="automatic", name="Automatic", interval=1800)
    requested = SimpleNamespace(screen_id="requested", name="Requested", interval=1800)
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    scheduler.screens = [automatic, requested]
    scheduler._pending = automatic
    scheduler._pending_requires_enabled = True

    asyncio.run(scheduler.async_add_to_queue(requested, play_next=True))

    assert scheduler._pending is requested
    assert scheduler._pending_from_queue is True
    assert scheduler.queued_slides == [requested]


def test_invalid_queued_slide_is_dropped_without_moving_playlist_cursor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    current = SimpleNamespace(screen_id="current", name="Current", interval=1800)
    queued = SimpleNamespace(screen_id="queued", name="Queued", interval=1800)

    async def async_show_screen(*_args: object, **_kwargs: object) -> dict:
        raise scheduler_mod.HomeAssistantError("invalid slide")

    monkeypatch.setattr(scheduler_mod, "async_show_screen", async_show_screen)
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    scheduler.screens = [current, queued]
    scheduler.current_id = current.screen_id
    scheduler._playlist_cursor_id = current.screen_id
    scheduler._queued_ids = [queued.screen_id]

    displayed = asyncio.run(scheduler._async_show_queued(queued, manual=False))

    assert displayed is False
    assert scheduler.queued_slides == []
    assert scheduler.current_id == current.screen_id
    assert scheduler._playlist_cursor_id == current.screen_id


def test_manual_next_drops_permanently_rejected_queue_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    current = SimpleNamespace(screen_id="current", name="Current", interval=1800)
    queued = SimpleNamespace(screen_id="queued", name="Queued", interval=1800)

    async def async_show_screen(*_args: object, **_kwargs: object) -> dict:
        raise scheduler_mod.HomeAssistantError("invalid slide")

    monkeypatch.setattr(scheduler_mod, "async_show_screen", async_show_screen)
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    scheduler.screens = [current, queued]
    scheduler.current_id = current.screen_id
    scheduler._playlist_cursor_id = current.screen_id
    scheduler._queued_ids = [queued.screen_id]

    with pytest.raises(scheduler_mod.HomeAssistantError, match="invalid slide"):
        asyncio.run(scheduler.async_next())

    assert scheduler.queued_slides == []
    assert scheduler.current_id == current.screen_id


def test_power_deferred_queued_slide_stays_at_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    current = SimpleNamespace(screen_id="current", name="Current", interval=1800)
    queued = SimpleNamespace(screen_id="queued", name="Queued", interval=1800)

    async def async_show_screen(*_args: object, **_kwargs: object) -> dict:
        return {
            "uploaded": False,
            "displayed": False,
            "skip_reason": "low_battery",
        }

    monkeypatch.setattr(scheduler_mod, "async_show_screen", async_show_screen)
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    scheduler.screens = [current, queued]
    scheduler.current_id = current.screen_id
    scheduler._playlist_cursor_id = current.screen_id
    scheduler._queued_ids = [queued.screen_id]

    displayed = asyncio.run(scheduler._async_show_queued(queued, manual=False))

    assert displayed is False
    assert [slide.screen_id for slide in scheduler.queued_slides] == ["queued"]
    assert scheduler.current_id == current.screen_id
    assert scheduler._pending_from_queue is False


def test_transient_art_fetch_failure_keeps_queued_slide(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    current = SimpleNamespace(screen_id="current", name="Current", interval=1800)
    queued = SimpleNamespace(screen_id="queued", name="Queued", interval=1800)

    async def async_show_screen(*_args: object, **_kwargs: object) -> dict:
        raise scheduler_mod.ArtFetchError("provider unavailable")

    monkeypatch.setattr(scheduler_mod, "async_show_screen", async_show_screen)
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    scheduler.screens = [current, queued]
    scheduler.current_id = current.screen_id
    scheduler._playlist_cursor_id = current.screen_id
    scheduler._queued_ids = [queued.screen_id]

    displayed = asyncio.run(scheduler._async_show_queued(queued, manual=False))

    assert displayed is False
    assert [slide.screen_id for slide in scheduler.queued_slides] == ["queued"]
    assert scheduler.current_id == current.screen_id
    assert scheduler._hold_until == datetime(2026, 7, 3, 12, 10)
    assert scheduler._pending_from_queue is False


def test_queue_mutations_reject_stale_input_and_clear_pending_item(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    queued = SimpleNamespace(screen_id="queued", name="Queued")
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    scheduler.screens = [queued]
    scheduler._queued_ids = [queued.screen_id]
    scheduler._pending = queued
    scheduler._pending_from_queue = True

    with pytest.raises(scheduler_mod.HomeAssistantError):
        asyncio.run(scheduler.async_remove_from_queue(1, queued.screen_id))
    with pytest.raises(scheduler_mod.HomeAssistantError):
        asyncio.run(scheduler.async_reorder_queue(["stale"]))
    with pytest.raises(scheduler_mod.HomeAssistantError):
        asyncio.run(scheduler.async_remove_from_queue(0, "stale"))

    asyncio.run(scheduler.async_remove_from_queue(0, queued.screen_id))

    assert scheduler._pending is None
    assert scheduler._pending_from_queue is False
    assert scheduler.queued_slides == []


def test_play_queue_item_targets_selected_hand_or_playlist_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    first = SimpleNamespace(screen_id="first", name="First")
    second = SimpleNamespace(screen_id="second", name="Second")
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    scheduler.screens = [first, second]
    scheduler._queued_ids = [first.screen_id, second.screen_id]
    played: list[tuple[str, str]] = []

    async def show_queued(slide: object, *, manual: bool) -> bool:
        assert manual is True
        played.append(("queue", slide.screen_id))
        return True

    async def select(slide: object, *, hold: bool = False) -> None:
        assert hold is False
        played.append(("playlist", slide.screen_id))

    monkeypatch.setattr(scheduler, "_async_show_queued", show_queued)
    monkeypatch.setattr(
        scheduler, "playlist_up_next", lambda *, limit: [first, second][:limit]
    )
    monkeypatch.setattr(scheduler, "async_select", select)

    asyncio.run(scheduler.async_play_queue_item("queue", 1, "second"))
    asyncio.run(scheduler.async_play_queue_item("playlist", 0, "first"))

    assert played == [("queue", "second"), ("playlist", "first")]


def test_play_queue_item_rejects_stale_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    slide = SimpleNamespace(screen_id="current", name="Current")
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    scheduler.screens = [slide]
    scheduler._queued_ids = [slide.screen_id]

    with pytest.raises(scheduler_mod.HomeAssistantError):
        asyncio.run(scheduler.async_play_queue_item("queue", 0, "stale"))
    with pytest.raises(scheduler_mod.HomeAssistantError):
        asyncio.run(scheduler.async_play_queue_item("other", 0, slide.screen_id))


def test_play_later_duplicate_consumes_selected_occurrence_after_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    duplicate = SimpleNamespace(screen_id="duplicate", name="Duplicate", interval=1800)
    other = SimpleNamespace(screen_id="other", name="Other", interval=1800)
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    scheduler.screens = [duplicate, other]
    scheduler._queued_ids = [duplicate.screen_id, other.screen_id, duplicate.screen_id]

    displayed = asyncio.run(
        scheduler.async_play_queue_item("queue", 2, duplicate.screen_id)
    )

    assert displayed is None
    assert scheduler._queued_ids == ["duplicate", "duplicate", "other"]
    assert scheduler._pending is duplicate
    assert scheduler._pending_from_queue is True

    async def show_success(*_args: object, **_kwargs: object) -> dict:
        return {}

    monkeypatch.setattr(scheduler_mod, "async_show_screen", show_success)
    asyncio.run(scheduler._async_retry_pending(duplicate))

    assert scheduler._queued_ids == ["duplicate", "other"]
    assert scheduler._pending_from_queue is False


def test_play_playlist_item_clears_queue_retry_without_consuming_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    queued = SimpleNamespace(screen_id="queued", name="Queued", interval=1800)
    playlist = SimpleNamespace(screen_id="playlist", name="Playlist", interval=1800)
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    scheduler.screens = [queued, playlist]
    scheduler._queued_ids = [queued.screen_id]
    scheduler._pending = queued
    scheduler._pending_from_queue = True
    scheduler._pending_hold_on_success = True
    played: list[str] = []

    monkeypatch.setattr(
        scheduler, "playlist_up_next", lambda *, limit: [playlist][:limit]
    )

    async def select(slide: object, *, hold: bool = False) -> None:
        assert hold is False
        assert scheduler._pending is None
        assert scheduler._pending_from_queue is False
        assert scheduler._pending_hold_on_success is False
        played.append(slide.screen_id)

    monkeypatch.setattr(scheduler, "async_select", select)

    asyncio.run(scheduler.async_play_queue_item("playlist", 0, playlist.screen_id))

    assert played == ["playlist"]
    assert scheduler._queued_ids == ["queued"]


def test_play_queue_item_rejects_active_upload_without_mutating_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    first = SimpleNamespace(screen_id="first", name="First", interval=1800)
    second = SimpleNamespace(screen_id="second", name="Second", interval=1800)
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    scheduler.screens = [first, second]
    scheduler._queued_ids = [first.screen_id, second.screen_id]
    scheduler._pending = first
    scheduler._pending_from_queue = True
    scheduler._pending_hold_on_success = True
    scheduler._busy = True
    monkeypatch.setattr(
        scheduler, "playlist_up_next", lambda *, limit: [second][:limit]
    )
    before = (
        list(scheduler._queued_ids),
        scheduler._pending,
        scheduler._pending_from_queue,
        scheduler._pending_hold_on_success,
    )

    for section, index, slide_id in (
        ("queue", 1, second.screen_id),
        ("playlist", 0, second.screen_id),
    ):
        with pytest.raises(scheduler_mod.HomeAssistantError):
            asyncio.run(scheduler.async_play_queue_item(section, index, slide_id))
        assert (
            list(scheduler._queued_ids),
            scheduler._pending,
            scheduler._pending_from_queue,
            scheduler._pending_hold_on_success,
        ) == before


def test_queue_mutations_replace_sleeping_pending_item_with_new_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    first = SimpleNamespace(screen_id="first", name="First")
    second = SimpleNamespace(screen_id="second", name="Second")
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    scheduler.screens = [first, second]
    scheduler._queued_ids = [first.screen_id]
    scheduler._pending = first
    scheduler._pending_from_queue = True
    scheduler._pending_requires_enabled = False

    asyncio.run(scheduler.async_add_to_queue(second, play_next=True))

    assert scheduler._pending is second
    assert scheduler._pending_requires_enabled is False

    asyncio.run(scheduler.async_reorder_queue([first.screen_id, second.screen_id]))

    assert scheduler._pending is first


def _circular_next_screen(
    screens: list[SimpleNamespace],
    current_id: str | None,
    *_args: object,
    **_kwargs: object,
) -> SimpleNamespace:
    ids = [slide.screen_id for slide in screens]
    start = ids.index(current_id) if current_id in ids else -1
    return screens[(start + 1) % len(screens)]


def test_reorder_upcoming_edits_session_order_not_playlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    current = SimpleNamespace(screen_id="current", name="Current")
    first = SimpleNamespace(screen_id="first", name="First")
    second = SimpleNamespace(screen_id="second", name="Second")
    third = SimpleNamespace(screen_id="third", name="Third")

    monkeypatch.setattr(scheduler_mod, "next_screen", _circular_next_screen)
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    scheduler.screens = [first, second, third, current]
    scheduler.current_id = current.screen_id
    scheduler._playlist_cursor_id = current.screen_id
    # No async_reorder attribute: touching the playlist would AttributeError.
    scheduler._playlists = SimpleNamespace()
    scheduler.playlist_id = "playlist-1"

    asyncio.run(scheduler.async_reorder_upcoming([second.screen_id, first.screen_id]))

    assert scheduler.screens == [first, second, third, current]
    assert scheduler._playback_order == ["second", "first", "third", "current"]
    assert scheduler._order_custom is True
    assert [slide.screen_id for slide in scheduler.playlist_up_next()] == [
        "second",
        "first",
        "third",
    ]


def test_reorder_upcoming_allowed_when_shuffled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    first = SimpleNamespace(screen_id="first", name="First")
    second = SimpleNamespace(screen_id="second", name="Second")

    monkeypatch.setattr(scheduler_mod, "next_screen", _circular_next_screen)
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    scheduler.screens = [first, second]
    scheduler.shuffle = True

    asyncio.run(scheduler.async_reorder_upcoming([second.screen_id, first.screen_id]))

    assert scheduler._playback_order == ["second", "first"]


def test_reorder_upcoming_rejects_stale_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    first = SimpleNamespace(screen_id="first", name="First")
    second = SimpleNamespace(screen_id="second", name="Second")

    monkeypatch.setattr(scheduler_mod, "next_screen", _circular_next_screen)
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    scheduler.screens = [first, second]

    with pytest.raises(scheduler_mod.HomeAssistantError, match="changed"):
        asyncio.run(scheduler.async_reorder_upcoming(["second", "missing"]))

    assert scheduler._playback_order == []
    assert scheduler._order_custom is False


def test_skip_upcoming_defers_to_end_of_cycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    slides = [
        SimpleNamespace(screen_id=slide_id, name=slide_id.title())
        for slide_id in ("a", "b", "c", "d")
    ]

    monkeypatch.setattr(scheduler_mod, "next_screen", _circular_next_screen)
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    scheduler.screens = list(slides)
    scheduler.current_id = "a"
    scheduler._playlist_cursor_id = "a"

    asyncio.run(scheduler.async_skip_upcoming(0, "b"))

    assert scheduler._playback_order == ["b", "a", "c", "d"]
    assert scheduler._order_custom is True
    assert [slide.screen_id for slide in scheduler.playlist_up_next()] == [
        "c",
        "d",
        "b",
    ]

    with pytest.raises(scheduler_mod.HomeAssistantError, match="no longer"):
        asyncio.run(scheduler.async_skip_upcoming(0, "b"))


@pytest.mark.parametrize("pending_manual", [None, False, True])
def test_move_playlist_item_into_hand_queue(
    monkeypatch: pytest.MonkeyPatch,
    pending_manual,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    slides = [
        SimpleNamespace(screen_id=slide_id, name=slide_id.title())
        for slide_id in ("a", "b", "c")
    ]

    monkeypatch.setattr(scheduler_mod, "next_screen", _circular_next_screen)
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    scheduler.screens = list(slides)
    scheduler.current_id = "a"
    scheduler._playlist_cursor_id = "a"

    if pending_manual is not None:
        scheduler._pending = slides[2]
        scheduler._pending_requires_enabled = not pending_manual

    asyncio.run(scheduler.async_move_queue_item("playlist", 0, "b", "queue", 0))

    assert scheduler._queued_ids == ["b"]
    if pending_manual is False:
        assert scheduler._pending is slides[1]
        assert scheduler._pending_from_queue is True
    elif pending_manual is True:
        assert scheduler._pending is slides[2]
        assert scheduler._pending_from_queue is False
    # Deferred in the session so it does not play twice back to back.
    assert scheduler._playback_order == ["b", "a", "c"]
    assert [slide.screen_id for slide in scheduler.playlist_up_next()] == ["c", "b"]


@pytest.mark.parametrize("source", ["gallery", "catalog"])
@pytest.mark.parametrize("pending", [False, True])
def test_move_hand_queue_one_off_into_session(
    monkeypatch: pytest.MonkeyPatch, source: str, pending: bool,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    first = SimpleNamespace(screen_id="a", name="A")
    second = SimpleNamespace(screen_id="b", name="B")
    one_off = SimpleNamespace(screen_id="x", name="X")

    monkeypatch.setattr(scheduler_mod, "next_screen", _circular_next_screen)
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    scheduler.screens = [first, second]
    scheduler.current_id = "a"
    scheduler._playlist_cursor_id = "a"
    if source == "gallery":
        scheduler._external_queue["x"] = one_off
        scheduler._external_queue_data["x"] = {"name": "X"}
    else:
        scheduler._playlists = SimpleNamespace(
            render_slide_by_id=lambda slide_id: one_off if slide_id == "x" else None
        )
    scheduler._queued_ids = ["x"]
    if pending:
        scheduler._pending = one_off
        scheduler._pending_from_queue = True
        scheduler._pending_requires_enabled = True
        scheduler._pending_hold_on_success = True

    asyncio.run(scheduler.async_move_queue_item("queue", 0, "x", "playlist", 0))

    assert scheduler._queued_ids == []
    assert scheduler._playback_order == ["a", "x", "b"]
    assert [slide.screen_id for slide in scheduler.playlist_up_next()] == ["x", "b"]

    if pending:
        assert scheduler._pending is one_off
        assert scheduler._pending_from_queue is False
        assert scheduler._pending_hold_on_success is False

    # Session membership survives a catalog refresh and definition pruning.
    scheduler._rebase_playback_order(fresh=False)
    scheduler._prune_external()
    assert [slide.screen_id for slide in scheduler.playlist_up_next()] == ["x", "b"]
    if source == "gallery":
        assert "x" in scheduler._external_queue


def test_session_order_restores_from_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    assigned = SimpleNamespace(
        playlist_id="playlist-1", name="Gallery", interval=1800, shuffle=False
    )
    slides = [
        SimpleNamespace(screen_id="a", name="A"),
        SimpleNamespace(screen_id="b", name="B"),
    ]

    class Playlists:
        def assigned_to(self, _entry_id: str) -> object:
            return assigned

        def render_slides(self, _playlist_id: str) -> list[object]:
            return list(slides)

        def get(self, _playlist_id: str) -> object:
            return assigned

        def render_slide_by_id(self, _slide_id: str) -> None:
            return None

    class Store:
        def __init__(self, session: dict) -> None:
            self._session = session

        async def async_load(self) -> dict:
            return {"session": self._session}

        async def async_save(self, _data: dict) -> None:
            return None

    def start_with(session: dict) -> object:
        scheduler = scheduler_mod.FraimicScheduler(
            SimpleNamespace(), _entry(), Playlists()
        )
        scheduler._store = Store(session)
        asyncio.run(scheduler.async_start())
        return scheduler

    matching = start_with(
        {"playlist_id": "playlist-1", "shuffle": False, "order": ["b", "a"], "custom": True}
    )
    assert matching._playback_order == ["b", "a"]
    assert matching._order_custom is True

    shuffle_mismatch = start_with(
        {"playlist_id": "playlist-1", "shuffle": True, "order": ["b", "a"], "custom": True}
    )
    assert shuffle_mismatch._playback_order == ["a", "b"]
    assert shuffle_mismatch._order_custom is False

    empty_order = start_with(
        {"playlist_id": "playlist-1", "shuffle": False, "order": [], "custom": True}
    )
    assert empty_order._playback_order == ["a", "b"]
    assert empty_order._order_custom is False


def test_session_order_survives_playlist_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    assigned = SimpleNamespace(
        playlist_id="playlist-1", name="Gallery", interval=1800, shuffle=False
    )
    slides = [
        SimpleNamespace(screen_id="a", name="A"),
        SimpleNamespace(screen_id="b", name="B"),
    ]

    class Playlists:
        def assigned_to(self, _entry_id: str) -> object:
            return assigned

        def render_slides(self, _playlist_id: str) -> list[object]:
            return list(slides)

        def get(self, _playlist_id: str) -> object:
            return assigned

        def render_slide_by_id(self, _slide_id: str) -> None:
            return None

    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry(), Playlists())
    assert scheduler._playback_order == ["a", "b"]

    scheduler._playback_order = ["b", "a"]
    scheduler._order_custom = True
    slides.append(SimpleNamespace(screen_id="c", name="C"))
    asyncio.run(scheduler.async_refresh_playlist())

    assert scheduler._playback_order == ["b", "a", "c"]
    assert scheduler._order_custom is True

    asyncio.run(scheduler.async_refresh_playlist(reset=True))

    assert scheduler._playback_order == ["a", "b", "c"]
    assert scheduler._order_custom is False


def test_uncapped_upcoming_includes_all_promoted_slides(monkeypatch):
    scheduler_mod = _load_scheduler(monkeypatch)
    monkeypatch.setattr(scheduler_mod, "next_screen", _circular_next_screen)
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    scheduler.screens = [SimpleNamespace(screen_id="a", name="A")]
    scheduler._external_queue = {
        str(i): SimpleNamespace(screen_id=str(i), name=str(i)) for i in range(12)
    }
    scheduler._playback_order = ["a", *scheduler._external_queue]
    scheduler.current_id = scheduler._playlist_cursor_id = "a"

    assert len(scheduler.playlist_up_next()) == 10
    assert len(scheduler.playlist_up_next(limit=None)) == 12


def test_previous_returns_to_promoted_cursor_after_hand_queue(monkeypatch):
    scheduler_mod = _load_scheduler(monkeypatch)
    monkeypatch.setattr(scheduler_mod, "next_screen", _circular_next_screen)
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    promoted = SimpleNamespace(screen_id="x", name="X")
    scheduler.screens = [SimpleNamespace(screen_id="a", name="A")]
    scheduler._external_queue = {"x": promoted}
    scheduler._playback_order = ["a", "x"]
    scheduler._playlist_cursor_id = "x"
    scheduler.current_id = "queued"
    shown = []

    async def show(screen, **kwargs):
        shown.append(screen.screen_id)
        return True

    scheduler._async_show = show
    asyncio.run(scheduler.async_previous())
    assert shown == ["x"]


@pytest.mark.parametrize("source", ["gallery", "catalog"])
@pytest.mark.parametrize("elapsed", [1790, 1800])
def test_promoted_slide_rotates_at_playlist_interval(monkeypatch, source, elapsed):
    scheduler_mod = _load_scheduler(monkeypatch)
    monkeypatch.setattr(scheduler_mod, "next_screen", _circular_next_screen)
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    scheduler.screens = [SimpleNamespace(screen_id="a", name="A", interval=1800)]
    promoted = SimpleNamespace(screen_id="x", name="X", interval=21600)
    if source == "gallery":
        scheduler._external_queue = {"x": promoted}
    else:
        scheduler._playlists = SimpleNamespace(
            get=lambda playlist_id: SimpleNamespace(interval=1800),
            render_slide_by_id=lambda slide_id: promoted if slide_id == "x" else None,
        )
    scheduler._playback_order = ["a", "x"]
    scheduler.current_id = scheduler._playlist_cursor_id = "x"
    scheduler.enabled = True
    scheduler.displayed_hash = "shown"
    scheduler._last_rotation = scheduler_mod.dt_util.utcnow() - timedelta(seconds=elapsed)
    shown = []

    async def show(screen, **kwargs):
        shown.append(screen.screen_id)
        return True

    scheduler._async_show = show
    asyncio.run(scheduler._async_rotate(force=False))
    assert shown == (["a"] if elapsed >= 1800 else [])


@pytest.mark.parametrize("action", ["skip", "reorder"])
def test_session_edit_retargets_automatic_wake_retry(monkeypatch, action):
    scheduler_mod = _load_scheduler(monkeypatch)
    monkeypatch.setattr(scheduler_mod, "next_screen", _circular_next_screen)
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    scheduler.screens = [SimpleNamespace(screen_id=i, name=i) for i in ("a", "b", "c")]
    scheduler._playback_order = ["a", "b", "c"]
    scheduler.current_id = scheduler._playlist_cursor_id = "a"
    scheduler._pending = scheduler.screens[1]
    scheduler._pending_requires_enabled = True
    if action == "skip":
        asyncio.run(scheduler.async_skip_upcoming(0, "b"))
    else:
        asyncio.run(scheduler.async_reorder_upcoming(["c", "b"]))
    assert scheduler._pending.screen_id == "c"


def test_promoted_slide_rotates_with_empty_catalog(monkeypatch):
    scheduler_mod = _load_scheduler(monkeypatch)
    monkeypatch.setattr(scheduler_mod, "next_screen", _circular_next_screen)
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    scheduler._external_queue = {"x": SimpleNamespace(screen_id="x", name="X")}
    scheduler._playback_order = ["x"]
    scheduler.enabled = True
    shown = []

    async def show(screen, **kwargs):
        shown.append(screen.screen_id)
        return True

    scheduler._async_show = show
    asyncio.run(scheduler._async_rotate(force=False))
    assert shown == ["x"]
