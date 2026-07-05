"""Tests for Home Assistant data fetch helpers with small HA stubs."""

from __future__ import annotations

import asyncio
import sys
import types
from datetime import datetime

import pytest

from conftest import load


def _install_ha_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    homeassistant = types.ModuleType("homeassistant")
    core = types.ModuleType("homeassistant.core")
    exceptions = types.ModuleType("homeassistant.exceptions")
    helpers = types.ModuleType("homeassistant.helpers")
    template = types.ModuleType("homeassistant.helpers.template")
    util = types.ModuleType("homeassistant.util")
    dt = types.ModuleType("homeassistant.util.dt")

    class HomeAssistant:
        pass

    class State:
        pass

    class TemplateError(Exception):
        pass

    class Template:
        def __init__(self, value: str, hass: object) -> None:
            self._value = value

        def async_render(self, *, parse_result: bool = False) -> str:
            return self._value

    def parse_date(value: str):
        return datetime.fromisoformat(value).date()

    def parse_datetime(value: str):
        return datetime.fromisoformat(value)

    core.HomeAssistant = HomeAssistant
    core.State = State
    exceptions.TemplateError = TemplateError
    template.Template = Template
    template.TemplateError = TemplateError
    dt.as_local = lambda value: value
    dt.now = lambda: datetime(2026, 7, 3, 14, 5)
    dt.parse_date = parse_date
    dt.parse_datetime = parse_datetime
    homeassistant.core = core
    homeassistant.exceptions = exceptions
    homeassistant.helpers = helpers
    homeassistant.util = util
    helpers.template = template
    util.dt = dt

    monkeypatch.setitem(sys.modules, "homeassistant", homeassistant)
    monkeypatch.setitem(sys.modules, "homeassistant.core", core)
    monkeypatch.setitem(sys.modules, "homeassistant.exceptions", exceptions)
    monkeypatch.setitem(sys.modules, "homeassistant.helpers", helpers)
    monkeypatch.setitem(sys.modules, "homeassistant.helpers.template", template)
    monkeypatch.setitem(sys.modules, "homeassistant.util", util)
    monkeypatch.setitem(sys.modules, "homeassistant.util.dt", dt)


def _load_fetch(monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    _install_ha_stubs(monkeypatch)
    sys.modules.pop("fraimic.render.fetch", None)
    return load("render.fetch")


class _Services:
    async def async_call(
        self,
        _domain: str,
        _service: str,
        _data: dict[str, object],
        *,
        target: dict[str, object],
        blocking: bool,
        return_response: bool,
    ) -> dict[str, object]:
        return {
            "calendar.family": {
                "events": [
                    {"summary": "All day", "start": "2026-07-04"},
                    {"summary": "Timed", "start": "2026-07-04 09:30:00"},
                ]
            }
        }


class _Hass:
    services = _Services()


def test_calendar_fetch_only_treats_bare_dates_as_all_day(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fetch = _load_fetch(monkeypatch)
    context = load("render.context")
    ctx = context.RenderContext(now=datetime(2026, 7, 3, 14, 5))

    result = asyncio.run(
        fetch._async_fetch_calendar(
            _Hass(),
            {"entities": ["calendar.family"], "days": 2},
            ctx,
        )
    )

    assert result == {
        "events": [
            {"day": "Tomorrow", "time": "", "title": "All day"},
            {"day": "Tomorrow", "time": "09:30", "title": "Timed"},
        ]
    }
