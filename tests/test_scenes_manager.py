"""Tests for scene manager validation and activation behavior."""

from __future__ import annotations

import asyncio
import sys
import types
from types import SimpleNamespace

import pytest
from conftest import load


def _load_scenes(monkeypatch: pytest.MonkeyPatch):
    homeassistant = types.ModuleType("homeassistant")
    core = types.ModuleType("homeassistant.core")
    exceptions = types.ModuleType("homeassistant.exceptions")
    helpers = types.ModuleType("homeassistant.helpers")
    dispatcher = types.ModuleType("homeassistant.helpers.dispatcher")
    storage = types.ModuleType("homeassistant.helpers.storage")

    class HomeAssistant:
        pass

    class HomeAssistantError(Exception):
        pass

    class Store:
        def __init__(self, *_args, **_kwargs) -> None:
            self.saved = None

        async def async_load(self):
            return None

        async def async_save(self, data):
            self.saved = data

    core.HomeAssistant = HomeAssistant
    core.callback = lambda func: func
    exceptions.HomeAssistantError = HomeAssistantError
    dispatcher.async_dispatcher_send = lambda *_args: None
    storage.Store = Store
    helpers.dispatcher = dispatcher
    helpers.storage = storage
    homeassistant.core = core
    homeassistant.exceptions = exceptions
    homeassistant.helpers = helpers

    library = types.ModuleType("fraimic.library")
    library.FraimicLibrary = object

    async def async_upload_rendered(*_args, **_kwargs) -> None:
        return None

    library.async_upload_rendered = async_upload_rendered
    helper_mod = types.ModuleType("fraimic.helpers")
    helper_mod.loaded_fraimic_entries = lambda hass: hass.entries

    monkeypatch.setitem(sys.modules, "homeassistant", homeassistant)
    monkeypatch.setitem(sys.modules, "homeassistant.core", core)
    monkeypatch.setitem(sys.modules, "homeassistant.exceptions", exceptions)
    monkeypatch.setitem(sys.modules, "homeassistant.helpers", helpers)
    monkeypatch.setitem(sys.modules, "homeassistant.helpers.dispatcher", dispatcher)
    monkeypatch.setitem(sys.modules, "homeassistant.helpers.storage", storage)
    monkeypatch.setitem(sys.modules, "fraimic.library", library)
    monkeypatch.setitem(sys.modules, "fraimic.helpers", helper_mod)
    sys.modules.pop("fraimic.scenes", None)
    return load("scenes")


class _Library:
    def __init__(self) -> None:
        self.images = {"img-1", "img-2", "img-3", "missing"}

    def get(self, image_id: str) -> str:
        if image_id not in self.images:
            raise ValueError(image_id)
        return image_id


def test_scene_names_are_case_insensitive_unique(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenes = _load_scenes(monkeypatch)
    manager = scenes.SceneManager(SimpleNamespace(entries=[]), _Library())

    first = asyncio.run(manager.async_create("Gallery", {"entry-1": "img-1"}))

    with pytest.raises(scenes.HomeAssistantError, match="already exists"):
        asyncio.run(manager.async_create("gallery", {"entry-1": "img-1"}))

    manager.scenes["legacy"] = scenes.Scene(
        scene_id="legacy", name="GALLERY", mappings={"entry-1": "img-1"}
    )
    with pytest.raises(scenes.HomeAssistantError, match="Multiple"):
        manager.find_by_name(first.name)


def test_scene_update_validates_before_mutating(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenes = _load_scenes(monkeypatch)
    manager = scenes.SceneManager(SimpleNamespace(entries=[]), _Library())
    scene = asyncio.run(manager.async_create("Morning", {"entry-1": "img-1"}))

    with pytest.raises(scenes.HomeAssistantError, match="at least one"):
        asyncio.run(manager.async_update(scene.scene_id, name="Evening", mappings={}))

    assert scene.name == "Morning"
    assert scene.mappings == {"entry-1": "img-1"}


class _Scheduler:
    busy = False

    def __init__(self) -> None:
        self.events: list[tuple[str, bool | None]] = []

    def begin_external_upload(self) -> None:
        self.events.append(("begin", None))

    def finish_external_upload(self, *, uploaded: bool, hold: bool = True) -> None:
        self.events.append(("finish", uploaded))


def _entry(entry_id: str) -> SimpleNamespace:
    scheduler = _Scheduler()
    return SimpleNamespace(
        entry_id=entry_id,
        title=entry_id,
        runtime_data=SimpleNamespace(scheduler=scheduler),
        scheduler=scheduler,
    )


def test_scene_send_snapshots_mappings_and_isolates_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenes = _load_scenes(monkeypatch)
    entries = [_entry("entry-1"), _entry("entry-2"), _entry("entry-3")]
    manager = scenes.SceneManager(SimpleNamespace(entries=entries), _Library())
    scene = asyncio.run(
        manager.async_create(
            "Wall",
            {
                "entry-1": "img-1",
                "entry-2": "missing",
                "entry-3": "img-3",
                "entry-4": "img-2",
            },
        )
    )
    render_calls: list[tuple[str, str]] = []
    upload_calls: list[tuple[str, str | None]] = []

    async def render(image_id: str, entry: SimpleNamespace):
        render_calls.append((entry.entry_id, image_id))
        if image_id == "img-1":
            manager.scenes[scene.scene_id].mappings.clear()
        if image_id == "missing":
            raise OSError("source disappeared")
        return (b"bin", b"png", "auto")

    async def upload(entry: SimpleNamespace, *_args, media_title=None) -> None:
        upload_calls.append((entry.entry_id, media_title))

    monkeypatch.setattr(
        manager.library, "async_render_for_entry", render, raising=False
    )
    monkeypatch.setattr(scenes, "async_upload_rendered", upload)

    results = asyncio.run(manager.async_send(scene.scene_id))

    assert render_calls == [
        ("entry-1", "img-1"),
        ("entry-2", "missing"),
        ("entry-3", "img-3"),
    ]
    assert upload_calls == [("entry-1", "Wall"), ("entry-3", "Wall")]
    assert results == {
        "entry-4": {"ok": False, "error": "Frame is not loaded"},
        "entry-2": {"ok": False, "error": "source disappeared"},
        "entry-1": {"ok": True, "error": None},
        "entry-3": {"ok": True, "error": None},
    }
    assert entries[0].scheduler.events == [("begin", None), ("finish", True)]
    assert entries[1].scheduler.events == [("begin", None), ("finish", False)]
    assert entries[2].scheduler.events == [("begin", None), ("finish", True)]
