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

    class ServiceValidationError(HomeAssistantError):
        pass

    class TemplateError(Exception):
        pass

    class Template:
        def __init__(self, value: str, _hass: object) -> None:
            self._value = value

        def async_render(self, *, parse_result: bool = False) -> str:
            if parse_result:
                return self._value
            return self._value

    core.HomeAssistant = HomeAssistant
    core.State = State
    exceptions.HomeAssistantError = HomeAssistantError
    exceptions.ServiceValidationError = ServiceValidationError
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


def _load_display(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[types.ModuleType, type[Exception]]:
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
    return types.SimpleNamespace(name="Dashboard", kind="dashboard")


def _install_services(monkeypatch: pytest.MonkeyPatch, **attrs: object) -> None:
    services = types.ModuleType("fraimic.services")
    services.begin_external_upload = lambda _entry: None
    services.finish_external_upload = lambda _scheduler, *, uploaded: None
    for name, value in attrs.items():
        setattr(services, name, value)
    monkeypatch.setitem(sys.modules, "fraimic.services", services)


def test_preview_only_converts_without_upload(monkeypatch: pytest.MonkeyPatch) -> None:
    display, _ = _load_display(monkeypatch)
    calls: list[tuple[str, bytes, dict, bool]] = []

    async def build_context(_hass: object, _screen: object) -> object:
        return object()

    def render_screen(
        _screen: object, _ctx: object, width: int, height: int
    ) -> tuple[bytes, str]:
        assert (width, height) == (480, 800)
        return b"screen-png", "none"

    async def convert_for_entry(
        _hass: object,
        _entry: object,
        png: bytes,
        overrides: dict,
        *,
        preprocess: bool,
    ) -> tuple[bytes, bytes, str]:
        calls.append(("convert", png, overrides, preprocess))
        return b"bin-data", b"preview-png", "none"

    async def render_and_upload(*_args: object, **_kwargs: object) -> dict:
        raise AssertionError("preview-only must not upload")

    monkeypatch.setattr(display, "async_build_context", build_context)
    monkeypatch.setattr(display, "render_screen", render_screen)
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
    calls: list[tuple[str, bytes, dict, bool, bool]] = []

    async def build_context(_hass: object, _screen: object) -> object:
        return object()

    def render_screen(
        _screen: object, _ctx: object, _width: int, _height: int
    ) -> tuple[bytes, str]:
        return b"screen-png", "none"

    async def convert_for_entry(
        *_args: object, **_kwargs: object
    ) -> tuple[bytes, bytes, str]:
        raise AssertionError("upload path must use async_render_and_upload")

    async def render_and_upload(
        _hass: object,
        entry: object,
        png: bytes,
        overrides: dict,
        *,
        preprocess: bool,
        skip_if_hash: str | None,
        hold_playlist: bool,
    ) -> dict:
        assert skip_if_hash is None
        calls.append(("upload", png, overrides, preprocess, hold_playlist))
        entry.runtime_data.last_preview = b"uploaded-preview"
        return {
            "uploaded": True,
            "content_hash": "abc123",
            "mode": "none",
            "preview_png": b"uploaded-preview",
        }

    monkeypatch.setattr(display, "async_build_context", build_context)
    monkeypatch.setattr(display, "render_screen", render_screen)
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
    assert calls == [("upload", b"screen-png", display._NEUTRAL_OVERRIDES, False, True)]
    assert entry.runtime_data.screen_preview_image.calls == [
        (b"uploaded-preview", "none")
    ]


def test_upload_path_holds_playlist_before_rendering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    display, _ = _load_display(monkeypatch)
    events: list[object] = []
    scheduler = object()

    async def build_context(_hass: object, _screen: object) -> object:
        events.append("build")
        return object()

    def render_screen(
        _screen: object, _ctx: object, _width: int, _height: int
    ) -> tuple[bytes, str]:
        events.append("render")
        return b"screen-png", "none"

    async def convert_for_entry(
        *_args: object, **_kwargs: object
    ) -> tuple[bytes, bytes, str]:
        raise AssertionError("upload path must use async_render_and_upload")

    async def render_and_upload(
        _hass: object,
        entry: object,
        png: bytes,
        overrides: dict,
        *,
        preprocess: bool,
        skip_if_hash: str | None,
        hold_playlist: bool,
    ) -> dict:
        events.append(("upload", hold_playlist))
        assert png == b"screen-png"
        assert skip_if_hash is None
        assert not hold_playlist
        entry.runtime_data.last_preview = b"uploaded-preview"
        return {
            "uploaded": True,
            "content_hash": "abc123",
            "mode": "none",
            "preview_png": b"uploaded-preview",
        }

    def begin_external_upload(_entry: object) -> object:
        events.append("begin")
        return scheduler

    def finish_external_upload(_scheduler: object, *, uploaded: bool) -> None:
        assert _scheduler is scheduler
        events.append(("finish", uploaded))

    monkeypatch.setattr(display, "async_build_context", build_context)
    monkeypatch.setattr(display, "render_screen", render_screen)
    _install_services(
        monkeypatch,
        async_convert_for_entry=convert_for_entry,
        async_render_and_upload=render_and_upload,
        begin_external_upload=begin_external_upload,
        finish_external_upload=finish_external_upload,
    )

    result = asyncio.run(display.async_show_screen(_Hass(), _entry(), _screen()))

    assert result["uploaded"] is True
    assert events == ["begin", "build", "render", ("upload", False), ("finish", True)]


def test_render_errors_become_home_assistant_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    display, error = _load_display(monkeypatch)

    async def build_context(_hass: object, _screen: object) -> object:
        return object()

    def render_screen(
        _screen: object, _ctx: object, _width: int, _height: int
    ) -> tuple[bytes, str]:
        raise ValueError("bad svg")

    monkeypatch.setattr(display, "async_build_context", build_context)
    monkeypatch.setattr(display, "render_screen", render_screen)

    with pytest.raises(error, match="Failed to render screen 'Dashboard': bad svg"):
        asyncio.run(display.async_render_screen(_Hass(), _entry(), _screen()))


def test_picture_source_redacts_url_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    display, error = _load_display(monkeypatch)

    aiohttp = types.ModuleType("aiohttp")
    aiohttp_client = types.ModuleType("homeassistant.helpers.aiohttp_client")

    class ClientTimeout:
        def __init__(self, *, total: int) -> None:
            self.total = total

    class Session:
        async def get(self, _url: str, *, timeout: ClientTimeout) -> object:
            assert timeout.total == 30
            raise OSError("network down")

    def async_get_clientsession(_hass: object) -> Session:
        return Session()

    aiohttp.ClientTimeout = ClientTimeout
    aiohttp_client.async_get_clientsession = async_get_clientsession
    monkeypatch.setitem(sys.modules, "aiohttp", aiohttp)
    monkeypatch.setitem(
        sys.modules, "homeassistant.helpers.aiohttp_client", aiohttp_client
    )
    sys.modules.pop("fraimic.source", None)

    screen = types.SimpleNamespace(
        source={"url": "https://example.test/screenshot.png?token=secret"}
    )

    with pytest.raises(error) as err:
        asyncio.run(display._async_picture_source(_Hass(), screen))

    message = str(err.value)
    assert "Could not download image URL: network down" in message
    assert "token=secret" not in message


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
