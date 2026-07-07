"""Tests for service orchestration without importing Home Assistant."""

from __future__ import annotations

import asyncio
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
    monkeypatch.setitem(sys.modules, "fraimic.coordinator", coordinator)
    monkeypatch.setitem(sys.modules, "fraimic.library", library)
    monkeypatch.setitem(sys.modules, "fraimic.render.display", render_display)
    monkeypatch.setitem(sys.modules, "fraimic.render.schema", render_schema)
    monkeypatch.setitem(sys.modules, "fraimic.source", source)
    monkeypatch.setitem(sys.modules, "fraimic.screens", screens)
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
        ) -> None:
            calls.append((image_id, target_entry, overrides))

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
