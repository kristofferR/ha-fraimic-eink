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
    api.FraimicConnectionError = type("FraimicConnectionError", (api.FraimicError,), {})
    api.FraimicTimeoutError = type("FraimicTimeoutError", (api.FraimicConnectionError,), {})
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
    previous_delivery = sys.modules.pop("fraimic.delivery", None)
    try:
        yield load("library")
    finally:
        sys.modules.pop("fraimic.library", None)
        sys.modules.pop("fraimic.delivery", None)
        if previous_delivery is not None:
            sys.modules["fraimic.delivery"] = previous_delivery
        if previous_library is not None:
            sys.modules["fraimic.library"] = previous_library


def test_prerendered_cloud_send_bypasses_lan_policy(library_module, monkeypatch):
    from unittest.mock import AsyncMock, Mock

    library = library_module
    deliver = AsyncMock()
    services = types.ModuleType("fraimic.services")
    services.async_deliver_cloud = deliver
    monkeypatch.setitem(sys.modules, "fraimic.services", services)
    power = types.SimpleNamespace(begin=Mock(), finish=Mock())
    runtime = types.SimpleNamespace(cloud=object(), power=power, upload_lock=asyncio.Lock())
    entry = types.SimpleNamespace(options={}, runtime_data=runtime)
    assert asyncio.run(library.async_upload_rendered(
        entry, b"panel", b"preview", "none", media_title="Art", queue_if_asleep=True
    )) is False
    deliver.assert_awaited_once_with(entry, b"panel", title="Art", preview_png=b"preview")
    power.finish.assert_called_once()


@pytest.mark.parametrize("cached", [False, True])
def test_native_adhoc_preview_preserves_panel_pixels(library_module, monkeypatch, tmp_path, cached):
    from unittest.mock import AsyncMock, Mock
    import numpy as np

    library = library_module
    ic = load("image_convert")
    packed = ic._pack_nibbles(np.arange(32, dtype=np.uint8) % 6, 8, 4)
    convert = Mock(return_value=(packed, b"thumbnail", "bayer"))
    monkeypatch.setattr(library, "convert_image", convert)
    params = {"width": 8, "height": 4, "rotate": 90, "preview_rotate": 270}
    monkeypatch.setattr(library, "resolve_render_params", lambda _: params.copy())

    class Hass:
        async def async_add_executor_job(self, function, *args):
            return function(*args)

    manager = object.__new__(library.FraimicLibrary)
    manager.hass = Hass()
    manager.originals_dir = tmp_path
    image = library.LibraryImage("art", "art.png", "image/png", 1.0)
    manager.images = {image.image_id: image}
    manager.original_path(image).write_bytes(b"original")
    manager.async_render_for_entry = AsyncMock(return_value=(packed, b"thumbnail", "bayer"))
    overrides = None if cached else {"fit": "contain", "mode": "bayer", "tone_name": "soft"}
    png = asyncio.run(manager.async_render_adhoc_preview(
        image.image_id, object(), None, overrides=overrides, full_resolution=True
    ))
    assert png == ic.bin_to_png(packed, 8, 4, 270)
    if cached:
        convert.assert_not_called()
    else:
        assert convert.call_args.kwargs["tone"] == 0
        assert convert.call_args.kwargs["fit"] == "contain"
        assert convert.call_args.kwargs["mode"] == "bayer"


@pytest.mark.parametrize("fit", ["cover", "contain", "stretch"])
def test_library_send_crop_matches_preview_fit(library_module, monkeypatch, tmp_path, fit):
    from unittest.mock import Mock

    library = library_module
    monkeypatch.setattr(library, "resolve_render_params", lambda *_: {
        "width": 8, "height": 4, "rotate": 0, "fit": fit,
    })
    convert = Mock(return_value=(b"panel", b"preview", "none"))
    monkeypatch.setattr(library, "convert_image", convert)

    class Hass:
        async def async_add_executor_job(self, function, *args):
            return function(*args)

    manager = object.__new__(library.FraimicLibrary)
    manager.hass = Hass()
    manager.originals_dir = manager.renders_dir = tmp_path
    manager._read_render_sync = lambda *_: None
    manager._write_render_sync = lambda *_: None
    image = library.LibraryImage("art", "art.png", "image/png", 1.0, crops={"8x4": [0, 0, .5, 1]})
    manager.images = {image.image_id: image}
    manager.original_path(image).write_bytes(b"original")
    asyncio.run(manager.async_render_for_entry("art", object(), {"fit": fit}))
    assert convert.call_args.kwargs["crop"] == ((0, 0, .5, 1) if fit == "cover" else None)


@pytest.mark.parametrize("invalid_entry", [False, True])
def test_crop_invalidates_only_matching_frame_playlists(library_module, monkeypatch, invalid_entry):
    library = library_module
    invalidated = []
    evicted = []
    backfilled = []
    image = library.LibraryImage("abc123def456", "Art.jpg", "image/jpeg", 1.0)

    class Hass:
        async def async_add_executor_job(self, target, *args):
            return target(*args)

    manager = object.__new__(library.FraimicLibrary)
    manager.hass = Hass()
    manager.images = {image.image_id: image}

    async def save():
        pass

    manager._async_save_manifest = save
    manager._invalidate_renders_sync = lambda *_args: None
    manager.schedule_backfill = backfilled.append
    entries = []
    for entry_id, size, queued, referenced in (
        ("assigned", (800, 480), False, True),
        ("queued", (800, 480), True, True),
        ("other-image", (800, 480), False, False),
        ("other-size", (480, 800), False, True),
    ):
        screen = types.SimpleNamespace(source={
            "library_image": image.image_id if referenced else "other"
        })
        scheduler = types.SimpleNamespace(
            screens=[] if queued else [screen],
            queued_slides=[screen] if queued else [],
            invalidate_preprocessing=lambda key=entry_id: invalidated.append(key),
        )
        entries.append(types.SimpleNamespace(
            entry_id=entry_id, size=size,
            runtime_data=types.SimpleNamespace(scheduler=scheduler),
        ))
    monkeypatch.setattr(library, "loaded_fraimic_entries", lambda _hass: entries)
    if invalid_entry:
        entries.insert(0, types.SimpleNamespace(entry_id="invalid"))

    def resolve_params(entry):
        if entry.entry_id == "invalid":
            raise library.HomeAssistantError("Resolution exceeds maximum size")
        return {"width": entry.size[0], "height": entry.size[1], "rotate": 0}

    monkeypatch.setattr(library, "resolve_render_params", resolve_params)
    display = types.ModuleType("fraimic.render.display")
    display.discard_prepared_thumbnails = lambda _hass, **kwargs: evicted.append(kwargs)
    monkeypatch.setitem(sys.modules, "fraimic.render.display", display)

    asyncio.run(manager.async_set_crop(image.image_id, 800, 480, None, rotate=90))

    assert invalidated == ["assigned", "queued"]
    assert backfilled == [image.image_id]
    assert {item["entry_id"] for item in evicted} == {"assigned", "queued", "other-image"}


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


def test_delete_prunes_every_loaded_scheduler_before_original(
    library_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = library_module
    events: list[str] = []

    class Library:
        async def async_delete_image(self, image_id: str) -> None:
            events.append(f"delete:{image_id}")

    class Scheduler:
        def __init__(self, entry_id: str) -> None:
            self.entry_id = entry_id

        async def async_prune_library_image(self, image_id: str) -> None:
            events.append(f"prune:{self.entry_id}:{image_id}")

        async def async_refresh_playlist(self) -> None:
            events.append(f"refresh:{self.entry_id}")

    class PlaylistManager:
        assignments: dict[str, str] = {}

        async def async_prune_image(self, _image_id: str) -> set[str]:
            return set()

    entries = [
        types.SimpleNamespace(
            entry_id=entry_id,
            runtime_data=types.SimpleNamespace(scheduler=Scheduler(entry_id)),
        )
        for entry_id in ("frame-1", "frame-2")
    ]
    playlists = types.ModuleType("fraimic.playlists")
    playlists.DATA_PLAYLISTS = "playlists"
    playlists.PlaylistManager = PlaylistManager
    scenes = types.ModuleType("fraimic.scenes")
    scenes.get_scene_manager = lambda _hass: None
    monkeypatch.setitem(sys.modules, "fraimic.playlists", playlists)
    monkeypatch.setitem(sys.modules, "fraimic.scenes", scenes)
    monkeypatch.setattr(library, "loaded_fraimic_entries", lambda _hass: entries)
    hass = types.SimpleNamespace(
        data={
            library.DOMAIN: {
                library.DATA_LIBRARY: Library(),
                playlists.DATA_PLAYLISTS: PlaylistManager(),
            }
        }
    )

    asyncio.run(library.async_delete_library_image(hass, "image-1"))

    assert events == [
        "prune:frame-1:image-1",
        "prune:frame-2:image-1",
        "delete:image-1",
    ]


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


@pytest.mark.parametrize('outcome', ['awake', 'asleep', 'timeout', 'deferred'])
def test_prerendered_hybrid_uses_same_transport_selection(library_module, monkeypatch, outcome):
    from unittest.mock import AsyncMock, Mock
    from fraimic.api import FraimicConnectionError

    library = library_module
    services = types.ModuleType('fraimic.services')
    services.async_deliver_cloud = AsyncMock()
    services.async_prepare_local_delivery = AsyncMock()
    monkeypatch.setitem(sys.modules, 'fraimic.services', services)
    client = types.SimpleNamespace(
        get_battery=AsyncMock(return_value={'battery': {'percent': 90}}, side_effect=FraimicConnectionError('asleep') if outcome == 'asleep' else None),
        upload_image=AsyncMock(side_effect=library.FraimicTimeoutError('accepted') if outcome == 'timeout' else None),
    )
    power = types.SimpleNamespace(
        begin=Mock(return_value=1), finish=Mock(), skip_reason=Mock(return_value='low_battery' if outcome == 'deferred' else None),
        async_record_upload=AsyncMock(), schedule_sleep=Mock(),
    )
    runtime = types.SimpleNamespace(
        cloud=types.SimpleNamespace(has_image=False), client=client, power=power, upload_lock=asyncio.Lock(),
        coordinator=types.SimpleNamespace(data={}, async_update_listeners=Mock(), async_set_frame_online=Mock()),
        send_queue=Mock(), set_displayed_preview=Mock(),
    )
    entry = types.SimpleNamespace(options={'delivery_mode': 'hybrid'}, runtime_data=runtime)
    displayed = asyncio.run(library.async_upload_rendered(
        entry, b'packed', b'preview', 'none', queue_if_asleep=True,
    ))
    local = outcome not in ('asleep', 'deferred')
    assert displayed is local
    assert client.upload_image.await_count == int(local)
    assert services.async_prepare_local_delivery.await_count == int(local)
    assert services.async_deliver_cloud.await_count == int(not local)
    assert runtime.set_displayed_preview.call_count == int(local)
    runtime.send_queue.async_upload_or_queue.assert_not_called()
