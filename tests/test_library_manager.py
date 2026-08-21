"""Focused transactional tests for the Home Assistant-backed library manager."""

from __future__ import annotations

import asyncio
import sys
import types

import pytest
from conftest import load


@pytest.fixture
def library_module(monkeypatch: pytest.MonkeyPatch):
    """Load the library module with the small HA surface it imports stubbed."""
    homeassistant = types.ModuleType("homeassistant")
    homeassistant.__path__ = []
    config_entries = types.ModuleType("homeassistant.config_entries")
    config_entries.ConfigEntry = object
    core = types.ModuleType("homeassistant.core")
    core.HomeAssistant = object

    def callback(function):
        return function

    core.callback = callback
    exceptions = types.ModuleType("homeassistant.exceptions")
    exceptions.HomeAssistantError = type("HomeAssistantError", (Exception,), {})
    api = types.ModuleType("fraimic.api")
    api.FraimicError = type("FraimicError", (Exception,), {})
    helpers = types.ModuleType("fraimic.helpers")
    helpers.loaded_fraimic_entries = lambda _hass: []
    helpers.resolve_render_params = lambda _entry, _overrides=None: {}

    monkeypatch.setitem(sys.modules, "homeassistant", homeassistant)
    monkeypatch.setitem(sys.modules, "homeassistant.config_entries", config_entries)
    monkeypatch.setitem(sys.modules, "homeassistant.core", core)
    monkeypatch.setitem(sys.modules, "homeassistant.exceptions", exceptions)
    monkeypatch.setitem(sys.modules, "fraimic.api", api)
    monkeypatch.setitem(sys.modules, "fraimic.helpers", helpers)
    previous_library = sys.modules.pop("fraimic.library", None)
    try:
        yield load("library")
    finally:
        sys.modules.pop("fraimic.library", None)
        if previous_library is not None:
            sys.modules["fraimic.library"] = previous_library


def test_rename_rolls_back_file_and_metadata_when_manifest_save_fails(
    library_module, tmp_path
) -> None:
    library = library_module

    class Hass:
        def async_create_task(self, target):
            return asyncio.create_task(target)

        async def async_add_executor_job(self, target, *args):
            return target(*args)

    manager = object.__new__(library.FraimicLibrary)
    manager.hass = Hass()
    manager.originals_dir = tmp_path
    image = library.LibraryImage(
        "abc123def456", "Old Name.jpg", "image/jpeg", 1.0
    )
    manager.images = {image.image_id: image}
    old_path = manager.original_path(image)
    old_path.write_bytes(b"original")

    async def fail_save() -> None:
        raise OSError("disk full")

    manager._async_save_manifest = fail_save

    with pytest.raises(library.HomeAssistantError, match="disk full"):
        asyncio.run(manager.async_rename_image(image.image_id, "New Name.png"))

    assert image.filename == "Old Name.jpg"
    assert image.content_type == "image/jpeg"
    assert old_path.read_bytes() == b"original"
    assert not (tmp_path / f"{image.image_id}_New Name.png").exists()


def test_rename_keeps_new_metadata_when_failed_manifest_cannot_roll_back(
    library_module, tmp_path
) -> None:
    library = library_module

    class Hass:
        rollback_source = None

        def async_create_task(self, target):
            return asyncio.create_task(target)

        async def async_add_executor_job(self, target, *args):
            if getattr(target, "__self__", None) == self.rollback_source:
                raise OSError("restore failed")
            return target(*args)

    manager = object.__new__(library.FraimicLibrary)
    manager.hass = Hass()
    manager.originals_dir = tmp_path
    image = library.LibraryImage(
        "abc123def456", "Old Name.jpg", "image/jpeg", 1.0
    )
    manager.images = {image.image_id: image}
    old_path = manager.original_path(image)
    new_path = tmp_path / f"{image.image_id}_New Name.png"
    manager.hass.rollback_source = new_path
    old_path.write_bytes(b"original")

    async def fail_save() -> None:
        raise OSError("disk full")

    manager._async_save_manifest = fail_save

    with pytest.raises(
        library.HomeAssistantError,
        match="disk full.*staged copy could not be removed.*restore failed",
    ):
        asyncio.run(manager.async_rename_image(image.image_id, "New Name.png"))

    assert image.filename == "Old Name.jpg"
    assert image.content_type == "image/jpeg"
    assert old_path.read_bytes() == b"original"
    assert new_path.read_bytes() == b"original"


def test_rename_waits_for_manifest_commit_before_propagating_cancellation(
    library_module, tmp_path
) -> None:
    library = library_module

    async def scenario() -> None:
        class Hass:
            def async_create_task(self, target):
                return asyncio.create_task(target)

            async def async_add_executor_job(self, target, *args):
                return target(*args)

        manager = object.__new__(library.FraimicLibrary)
        manager.hass = Hass()
        manager.originals_dir = tmp_path
        image = library.LibraryImage(
            "abc123def456", "Old Name.jpg", "image/jpeg", 1.0
        )
        manager.images = {image.image_id: image}
        old_path = manager.original_path(image)
        old_path.write_bytes(b"original")
        started = asyncio.Event()
        release = asyncio.Event()
        committed: dict[str, object] = {}

        async def controlled_save() -> None:
            started.set()
            await release.wait()
            committed["filename"] = image.filename
            committed["path_exists"] = manager.original_path(image).exists()
            committed["old_path_exists"] = old_path.exists()

        manager._async_save_manifest = controlled_save
        rename_task = asyncio.create_task(
            manager.async_rename_image(image.image_id, "New Name.png")
        )
        await started.wait()
        rename_task.cancel()
        await asyncio.sleep(0)

        assert not rename_task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await rename_task

        assert committed == {
            "filename": "New Name.png",
            "path_exists": True,
            "old_path_exists": True,
        }
        assert image.filename == "New Name.png"
        assert image.content_type == "image/png"
        assert not old_path.exists()
        assert manager.original_path(image).read_bytes() == b"original"

    asyncio.run(scenario())


def test_cancelled_rename_rolls_back_when_manifest_commit_fails(
    library_module, tmp_path
) -> None:
    library = library_module

    async def scenario() -> None:
        class Hass:
            def async_create_task(self, target):
                return asyncio.create_task(target)

            async def async_add_executor_job(self, target, *args):
                return target(*args)

        manager = object.__new__(library.FraimicLibrary)
        manager.hass = Hass()
        manager.originals_dir = tmp_path
        image = library.LibraryImage(
            "abc123def456", "Old Name.jpg", "image/jpeg", 1.0
        )
        manager.images = {image.image_id: image}
        old_path = manager.original_path(image)
        old_path.write_bytes(b"original")
        started = asyncio.Event()
        release = asyncio.Event()

        async def controlled_save() -> None:
            started.set()
            await release.wait()
            raise OSError("disk full")

        manager._async_save_manifest = controlled_save
        rename_task = asyncio.create_task(
            manager.async_rename_image(image.image_id, "New Name.png")
        )
        await started.wait()
        rename_task.cancel()
        await asyncio.sleep(0)

        assert not rename_task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await rename_task

        assert image.filename == "Old Name.jpg"
        assert image.content_type == "image/jpeg"
        assert old_path.read_bytes() == b"original"
        assert not (tmp_path / f"{image.image_id}_New Name.png").exists()

    asyncio.run(scenario())
