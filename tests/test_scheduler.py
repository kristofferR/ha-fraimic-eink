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
    playlist.eligible = lambda *_args, **_kwargs: True
    playlist.next_screen = lambda *_args, **_kwargs: None
    schema.ScreenConfig = SimpleNamespace
    coordinator.FraimicConfigEntry = SimpleNamespace
    screens.screens_from_entry = lambda _entry: []
    services.FrameUploadError = FrameUploadError
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
            )
        )

        def async_create_task(
            self, _hass: object, coro: object, name: str
        ) -> None:
            if created is None:
                raise AssertionError("async_create_task was not expected")
            created.append((coro, name))

    return Entry()


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
    asyncio.run(scheduler.async_refresh_playlist())
    assert scheduler._queued_ids == ["queued"]

    assigned.shuffle = True
    monkeypatch.setattr(scheduler_mod.random, "shuffle", lambda items: items.reverse())
    scheduler._load_assigned_playlist()

    assert scheduler.shuffle is True
    assert scheduler.screens == [second, active]


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

    def next_screen(screens: list, current_id: str | None, *_args, **_kwargs):
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


def test_sleeping_queued_slide_is_consumed_only_after_wake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    current = SimpleNamespace(screen_id="current", name="Current", interval=1800)
    queued = SimpleNamespace(screen_id="queued", name="Queued", interval=1800)
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    scheduler.screens = [current, queued]
    scheduler.current_id = current.screen_id
    scheduler._playlist_cursor_id = current.screen_id
    scheduler._queued_ids = [queued.screen_id]

    asyncio.run(scheduler.async_next())

    assert scheduler._pending is queued
    assert scheduler._pending_from_queue is True
    assert [slide.screen_id for slide in scheduler.queued_slides] == [queued.screen_id]

    async def async_show_screen(*_args: object, **_kwargs: object) -> dict:
        return {"uploaded": True, "content_hash": "shown"}

    monkeypatch.setattr(scheduler_mod, "async_show_screen", async_show_screen)
    asyncio.run(scheduler._async_retry_pending(queued))

    assert scheduler._pending is None
    assert scheduler.queued_slides == []
    assert scheduler.current_id == queued.screen_id
    assert scheduler._playlist_cursor_id == current.screen_id


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


def test_reorder_upcoming_changes_only_visible_playlist_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler_mod = _load_scheduler(monkeypatch)
    current = SimpleNamespace(screen_id="current", name="Current")
    first = SimpleNamespace(screen_id="first", name="First")
    second = SimpleNamespace(screen_id="second", name="Second")
    hidden = SimpleNamespace(screen_id="hidden", name="Hidden")

    def next_screen(screens: list, current_id: str | None, *_args, **_kwargs):
        visible = [slide for slide in screens if slide.screen_id != "hidden"]
        ids = [slide.screen_id for slide in visible]
        start = ids.index(current_id) if current_id in ids else -1
        return visible[(start + 1) % len(visible)]

    monkeypatch.setattr(scheduler_mod, "next_screen", next_screen)
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    scheduler.screens = [first, second, hidden, current]
    scheduler.current_id = current.screen_id
    scheduler._playlist_cursor_id = current.screen_id

    asyncio.run(scheduler.async_reorder_upcoming([second.screen_id, first.screen_id]))

    assert [slide.screen_id for slide in scheduler.screens] == [
        second.screen_id,
        first.screen_id,
        hidden.screen_id,
        current.screen_id,
    ]
