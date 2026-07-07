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
            coordinator=SimpleNamespace(last_update_success=True)
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
