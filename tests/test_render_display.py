"""Tests for screen display orchestration without importing Home Assistant."""

from __future__ import annotations

import asyncio
import sys
import types
from collections.abc import Callable
from datetime import datetime

import pytest

from conftest import load


def _install_ha_stubs(monkeypatch: pytest.MonkeyPatch) -> type[Exception]:
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

    class HomeAssistantError(Exception):
        pass

    class TemplateError(Exception):
        pass

    class Template:
        def __init__(self, value: str, hass: object) -> None:
            self._value = value

        def async_render(self, *, parse_result: bool = False) -> str:
            return self._value

    core.HomeAssistant = HomeAssistant
    core.State = State
    exceptions.HomeAssistantError = HomeAssistantError
    exceptions.TemplateError = TemplateError
    template.Template = Template
    template.TemplateError = TemplateError
    dt.now = lambda: datetime(2026, 7, 3, 14, 5)
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
    return HomeAssistantError


def _load_display(monkeypatch: pytest.MonkeyPatch) -> tuple[types.ModuleType, type[Exception]]:
    error = _install_ha_stubs(monkeypatch)
    for name in ("fraimic.render.display", "fraimic.render.fetch"):
        sys.modules.pop(name, None)
    return load("render.display"), error


class _Hass:
    async def async_add_executor_job(
        self, func: Callable[..., object], *args: object
    ) -> object:
        return func(*args)


class _PreviewImage:
    def __init__(self) -> None:
        self.calls: list[tuple[bytes, str]] = []

    def set_preview(self, png: bytes, mode: str) -> None:
        self.calls.append((png, mode))


def _entry(rotation: int = 0) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        data={"width": 800, "height": 480},
        options={"rotation": rotation},
        runtime_data=types.SimpleNamespace(
            last_preview=None,
            screen_preview_image=_PreviewImage(),
        ),
    )


def _screen() -> types.SimpleNamespace:
    return types.SimpleNamespace(name="Dashboard")


def _install_services(monkeypatch: pytest.MonkeyPatch, **attrs: object) -> None:
    services = types.ModuleType("fraimic.services")
    for name, value in attrs.items():
        setattr(services, name, value)
    monkeypatch.setitem(sys.modules, "fraimic.services", services)


def test_preview_only_converts_without_upload(monkeypatch: pytest.MonkeyPatch) -> None:
    display, _ = _load_display(monkeypatch)
    calls: list[tuple[str, bytes, dict, bool]] = []

    async def build_context(hass: object, screen: object) -> object:
        return object()

    def render_screen_png(screen: object, ctx: object, width: int, height: int) -> bytes:
        assert (width, height) == (480, 800)
        return b"screen-png"

    async def convert_for_entry(
        hass: object,
        entry: object,
        png: bytes,
        overrides: dict,
        *,
        preprocess: bool,
    ) -> tuple[bytes, bytes, str]:
        calls.append(("convert", png, overrides, preprocess))
        return b"bin-data", b"preview-png", "none"

    async def render_and_upload(*args: object, **kwargs: object) -> dict:
        raise AssertionError("preview-only must not upload")

    monkeypatch.setattr(display, "async_build_context", build_context)
    monkeypatch.setattr(display, "render_screen_png", render_screen_png)
    _install_services(
        monkeypatch,
        async_convert_for_entry=convert_for_entry,
        async_render_and_upload=render_and_upload,
    )

    entry = _entry(rotation=90)
    result = asyncio.run(
        display.async_show_screen(_Hass(), entry, _screen(), preview_only=True)
    )

    assert result["uploaded"] is False
    assert result["width"] == 480
    assert result["height"] == 800
    assert calls == [("convert", b"screen-png", display._NEUTRAL_OVERRIDES, False)]
    assert entry.runtime_data.screen_preview_image.calls == [(b"preview-png", "none")]


def test_upload_path_uploads_and_updates_screen_preview(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    display, _ = _load_display(monkeypatch)
    calls: list[tuple[str, bytes, dict, bool]] = []

    async def build_context(hass: object, screen: object) -> object:
        return object()

    def render_screen_png(screen: object, ctx: object, width: int, height: int) -> bytes:
        return b"screen-png"

    async def convert_for_entry(*args: object, **kwargs: object) -> tuple[bytes, bytes, str]:
        raise AssertionError("upload path must use async_render_and_upload")

    async def render_and_upload(
        hass: object,
        entry: object,
        png: bytes,
        overrides: dict,
        *,
        preprocess: bool,
    ) -> dict:
        calls.append(("upload", png, overrides, preprocess))
        entry.runtime_data.last_preview = b"uploaded-preview"
        return {"content_hash": "abc123", "mode": "none"}

    monkeypatch.setattr(display, "async_build_context", build_context)
    monkeypatch.setattr(display, "render_screen_png", render_screen_png)
    _install_services(
        monkeypatch,
        async_convert_for_entry=convert_for_entry,
        async_render_and_upload=render_and_upload,
    )

    entry = _entry()
    result = asyncio.run(
        display.async_show_screen(_Hass(), entry, _screen(), preview_only=False)
    )

    assert result == {
        "uploaded": True,
        "width": 800,
        "height": 480,
        "content_hash": "abc123",
        "mode": "none",
    }
    assert calls == [("upload", b"screen-png", display._NEUTRAL_OVERRIDES, False)]
    assert entry.runtime_data.screen_preview_image.calls == [(b"uploaded-preview", "none")]


def test_render_errors_become_home_assistant_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    display, error = _load_display(monkeypatch)

    async def build_context(hass: object, screen: object) -> object:
        return object()

    def render_screen_png(screen: object, ctx: object, width: int, height: int) -> bytes:
        raise ValueError("bad svg")

    monkeypatch.setattr(display, "async_build_context", build_context)
    monkeypatch.setattr(display, "render_screen_png", render_screen_png)

    with pytest.raises(error, match="Failed to render screen 'Dashboard': bad svg"):
        asyncio.run(display.async_render_screen(_Hass(), _entry(), _screen()))


def test_set_screen_preview_requires_preview_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    display, _ = _load_display(monkeypatch)
    image = _PreviewImage()
    runtime = types.SimpleNamespace(screen_preview_image=image)

    display._set_screen_preview(runtime, None, "none")
    assert image.calls == []

    runtime.screen_preview_image = None
    display._set_screen_preview(runtime, b"preview-png", "none")
    assert image.calls == []
