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

    class HomeAssistant:
        pass

    class HomeAssistantError(Exception):
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

    async def async_show_screen(*_args: object, **_kwargs: object) -> dict:
        return {"uploaded": True, "content_hash": "hash123"}

    monkeypatch.setattr(scheduler_mod, "async_show_screen", async_show_screen)
    scheduler = scheduler_mod.FraimicScheduler(SimpleNamespace(), _entry())
    scheduler._pending = screen
    scheduler._pending_requires_enabled = False

    asyncio.run(scheduler._async_retry_pending(screen))

    assert scheduler._pending is None
    assert scheduler.current_id == "screen-1"
    assert scheduler.displayed_hash == "hash123"


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
