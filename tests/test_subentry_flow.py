"""Tests for screen subentry flow validation with lightweight HA stubs."""

from __future__ import annotations

import asyncio
import sys
import types
from types import SimpleNamespace

from conftest import load


def _install_ha_stubs(monkeypatch) -> None:
    homeassistant = types.ModuleType("homeassistant")
    config_entries = types.ModuleType("homeassistant.config_entries")
    helpers = types.ModuleType("homeassistant.helpers")
    selector = types.ModuleType("homeassistant.helpers.selector")

    class ConfigSubentryFlow:
        def add_suggested_values_to_schema(self, schema, _suggested):
            return schema

        def async_show_form(self, **kwargs):
            return {"type": "form", **kwargs}

        def async_create_entry(self, **kwargs):
            return {"type": "create_entry", **kwargs}

        def async_update_and_abort(self, *args, **kwargs):
            return {"type": "abort", "args": args, **kwargs}

    class Selector:
        def __init__(self, *args, **kwargs) -> None:
            self.args = args
            self.kwargs = kwargs

        def __call__(self, value):
            return value

    class SelectOptionDict(dict):
        def __init__(self, **kwargs) -> None:
            super().__init__(**kwargs)

    for name in (
        "BooleanSelector",
        "EntitySelector",
        "EntitySelectorConfig",
        "IconSelector",
        "NumberSelector",
        "NumberSelectorConfig",
        "SelectSelector",
        "SelectSelectorConfig",
        "TemplateSelector",
        "TextSelector",
        "TimeSelector",
    ):
        setattr(selector, name, Selector)

    class NumberSelectorMode:
        BOX = "box"

    class SelectSelectorMode:
        DROPDOWN = "dropdown"

    config_entries.ConfigSubentryFlow = ConfigSubentryFlow
    config_entries.SubentryFlowResult = dict
    selector.NumberSelectorMode = NumberSelectorMode
    selector.SelectOptionDict = SelectOptionDict
    selector.SelectSelectorMode = SelectSelectorMode
    homeassistant.config_entries = config_entries
    homeassistant.helpers = helpers
    helpers.selector = selector

    monkeypatch.setitem(sys.modules, "homeassistant", homeassistant)
    monkeypatch.setitem(sys.modules, "homeassistant.config_entries", config_entries)
    monkeypatch.setitem(sys.modules, "homeassistant.helpers", helpers)
    monkeypatch.setitem(sys.modules, "homeassistant.helpers.selector", selector)


def _load_flow(monkeypatch):
    _install_ha_stubs(monkeypatch)
    sys.modules.pop("fraimic.subentry_flow", None)
    return load("subentry_flow")


def test_finish_returns_picture_form_for_invalid_url(monkeypatch) -> None:
    flow = _load_flow(monkeypatch)
    handler = flow.ScreenSubentryFlowHandler()
    handler._basics = {"name": "Bad picture", "layout": "picture"}
    # The picture form's provider dropdown reads the entry options; outside a
    # real flow the base class has no _get_entry, so stub an optionless entry.
    handler._get_entry = lambda: SimpleNamespace(options={})

    result = handler._finish({"kind": "picture", "url": "ftp://example.test/x.png"})

    assert result["type"] == "form"
    assert result["step_id"] == "picture"
    assert result["errors"] == {"url": "invalid_screen"}


def test_finish_returns_widget_form_for_invalid_format(monkeypatch) -> None:
    flow = _load_flow(monkeypatch)
    handler = flow.ScreenSubentryFlowHandler()
    handler._basics = {"name": "Clock", "layout": "full"}
    handler._slots = ["main"]
    handler._slot_index = 0
    handler._current_type = "clock"
    handler._widgets = [
        {"type": "clock", "slot": "main", "format": "%H:%M:%S"}
    ]

    result = asyncio.run(handler._advance_slot())

    assert result["type"] == "form"
    assert result["step_id"] == "widget_options"
    assert result["errors"] == {"base": "invalid_screen"}


def test_finish_schedules_reload_after_create(monkeypatch) -> None:
    flow = _load_flow(monkeypatch)
    reloads: list[str] = []
    handler = flow.ScreenSubentryFlowHandler()
    handler.handler = ("entry-1", "screen")
    handler.hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_schedule_reload=reloads.append)
    )
    handler._basics = {"name": "Dashboard", "layout": "full"}

    result = handler._finish(
        {"layout": "full", "widgets": [{"type": "clock", "slot": "main"}]}
    )

    assert result["type"] == "create_entry"
    assert reloads == ["entry-1"]


def test_finish_schedules_reload_after_reconfigure(monkeypatch) -> None:
    flow = _load_flow(monkeypatch)
    reloads: list[str] = []
    handler = flow.ScreenSubentryFlowHandler()
    handler.handler = ("entry-1", "screen")
    handler.hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_schedule_reload=reloads.append)
    )
    handler._existing = {"name": "Old"}
    handler._basics = {"name": "Dashboard", "layout": "full"}
    handler._get_entry = lambda: SimpleNamespace(entry_id="entry-1")
    handler._get_reconfigure_subentry = lambda: SimpleNamespace(subentry_id="screen-1")

    result = handler._finish(
        {"layout": "full", "widgets": [{"type": "clock", "slot": "main"}]}
    )

    assert result["type"] == "abort"
    assert reloads == ["entry-1"]
