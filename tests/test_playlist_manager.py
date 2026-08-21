"""Tests for named playlist persistence, migration, and mutations."""

from __future__ import annotations

import asyncio
import copy
import sys
import types
from types import SimpleNamespace
from typing import ClassVar

import pytest
from conftest import load


def _load_playlists(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[types.ModuleType, type]:
    homeassistant = types.ModuleType("homeassistant")
    core = types.ModuleType("homeassistant.core")
    helpers = types.ModuleType("homeassistant.helpers")
    storage = types.ModuleType("homeassistant.helpers.storage")

    class HomeAssistant:
        pass

    class Store:
        loaded: ClassVar[object] = None
        saved: ClassVar[list[dict]] = []

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def async_load(self) -> object:
            return copy.deepcopy(self.loaded)

        async def async_save(self, data: dict) -> None:
            self.saved.append(copy.deepcopy(data))

    Store.loaded = None
    Store.saved = []

    core.HomeAssistant = HomeAssistant
    storage.Store = Store
    helpers.storage = storage
    homeassistant.core = core
    homeassistant.helpers = helpers
    monkeypatch.setitem(sys.modules, "homeassistant", homeassistant)
    monkeypatch.setitem(sys.modules, "homeassistant.core", core)
    monkeypatch.setitem(sys.modules, "homeassistant.helpers", helpers)
    monkeypatch.setitem(sys.modules, "homeassistant.helpers.storage", storage)
    sys.modules.pop("fraimic.playlists", None)
    return load("playlists"), Store


def _subentry(slide_id: str, title: str, data: dict) -> SimpleNamespace:
    return SimpleNamespace(
        subentry_id=slide_id,
        title=title,
        data=data,
        subentry_type="screen",
    )


def test_migrates_each_frame_once_and_materializes_playlist_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playlists, store = _load_playlists(monkeypatch)
    store.saved = []
    manager = playlists.PlaylistManager(SimpleNamespace())
    asyncio.run(manager.async_setup())
    entry = SimpleNamespace(
        entry_id="frame-1",
        title="Living room",
        subentries={
            "photo": _subentry(
                "photo",
                "Morning",
                {
                    "kind": "picture",
                    "url": "https://example.com/morning.jpg",
                    "fit": "contain",
                    "interval": 900,
                },
            ),
            "clock": _subentry(
                "clock",
                "Clock",
                {
                    "layout": "full",
                    "widgets": [{"type": "clock", "slot": "main"}],
                    "interval": 3600,
                },
            ),
        },
    )

    asyncio.run(manager.async_migrate_entry(entry))
    asyncio.run(manager.async_migrate_entry(entry))

    assert len(manager.playlists) == 1
    playlist = manager.playlists[0]
    assert playlist.name == "Living room"
    assert playlist.interval == 900
    assert [slide.slide_id for slide in playlist.slides] == ["photo", "clock"]
    assert manager.assignments == {"frame-1": playlist.playlist_id}

    asyncio.run(
        manager.async_update_slide(
            playlist.playlist_id,
            "photo",
            tone="vivid",
            overlays="none",
        )
    )
    rendered = manager.render_slides(playlist.playlist_id)
    assert [slide.interval for slide in rendered] == [900, 900]
    assert rendered[0].source["tone"] == "vivid"
    assert rendered[0].overlay_mode == "none"
    assert len(store.saved) == 2

    store.loaded = store.saved[-1]
    restored = playlists.PlaylistManager(SimpleNamespace())
    asyncio.run(restored.async_setup())
    assert [slide.name for slide in restored.render_slides(playlist.playlist_id)] == [
        "Morning",
        "Clock",
    ]
    assert restored.render_slides(playlist.playlist_id)[0].source["tone"] == "vivid"


def test_add_duplicate_reorder_remove_and_undo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playlists, store = _load_playlists(monkeypatch)
    store.saved = []
    manager = playlists.PlaylistManager(SimpleNamespace())
    asyncio.run(manager.async_setup())
    playlist = asyncio.run(manager.async_create("Weekends"))
    asyncio.run(
        manager.async_add_slides(
            playlist.playlist_id,
            [
                {
                    "name": "Library picture",
                    "kind": "picture",
                    "library_image": "image-1",
                },
                {
                    "name": "Daily art",
                    "kind": "picture",
                    "provider": "wikimedia",
                },
            ],
        )
    )
    original_ids = [slide.slide_id for slide in playlist.slides]

    duplicate = asyncio.run(manager.async_duplicate(playlist.playlist_id))
    assert [slide.slide_id for slide in duplicate.slides] != original_ids
    assert [slide.data for slide in duplicate.slides] == [
        slide.data for slide in playlist.slides
    ]

    asyncio.run(
        manager.async_reorder(playlist.playlist_id, list(reversed(original_ids)))
    )
    assert [slide.slide_id for slide in playlist.slides] == list(reversed(original_ids))
    with pytest.raises(playlists.PlaylistChangedError):
        asyncio.run(manager.async_reorder(playlist.playlist_id, [original_ids[0]]))

    removed_id = playlist.slides[0].slide_id
    token = asyncio.run(manager.async_remove_slide(playlist.playlist_id, removed_id))
    with pytest.raises(playlists.PlaylistChangedError, match="another playlist"):
        asyncio.run(manager.async_undo_remove(duplicate.playlist_id, token))
    asyncio.run(manager.async_undo_remove(playlist.playlist_id, token))
    assert playlist.slides[0].slide_id == removed_id

    asyncio.run(manager.async_assign("frame-1", duplicate.playlist_id))
    assert manager.assigned_to("frame-1") is duplicate
    assert manager.assigned_frames(duplicate.playlist_id) == ["frame-1"]
    with pytest.raises(ValueError, match="too short"):
        asyncio.run(
            manager.async_set_options(
                playlist.playlist_id,
                interval=playlists.MIN_SCREEN_INTERVAL - 1,
            )
        )
    affected = asyncio.run(manager.async_delete(duplicate.playlist_id))
    assert affected == ["frame-1"]
    assert manager.assigned_to("frame-1") is None
    assert manager.assignments == {}


def test_add_rejects_non_mapping_and_prunes_deleted_images(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playlists, _store = _load_playlists(monkeypatch)
    manager = playlists.PlaylistManager(SimpleNamespace())
    playlist = asyncio.run(manager.async_create("Gallery"))

    with pytest.raises(ValueError, match="expected a mapping"):
        asyncio.run(manager.async_add_slides(playlist.playlist_id, ["bad"]))

    asyncio.run(
        manager.async_add_slides(
            playlist.playlist_id,
            [
                {
                    "name": "Stored",
                    "kind": "picture",
                    "library_image": "image-1",
                },
                {
                    "name": "Remote",
                    "kind": "picture",
                    "url": "https://example.com/remote.jpg",
                },
            ],
        )
    )
    affected = asyncio.run(manager.async_prune_image("image-1"))

    assert affected == {playlist.playlist_id}
    assert [slide.data["name"] for slide in playlist.slides] == ["Remote"]


def test_migration_refreshes_edited_legacy_slide(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playlists, _store = _load_playlists(monkeypatch)
    manager = playlists.PlaylistManager(SimpleNamespace())
    subentry = _subentry(
        "photo",
        "Morning",
        {"kind": "picture", "url": "https://example.com/one.jpg"},
    )
    entry = SimpleNamespace(
        entry_id="frame-1",
        title="Living room",
        subentries={"photo": subentry},
    )
    asyncio.run(manager.async_migrate_entry(entry))
    subentry.data = {
        "kind": "picture",
        "url": "https://example.com/two.jpg",
    }

    asyncio.run(manager.async_sync_legacy_slide(entry, "photo"))

    assert manager.playlists[0].slides[0].data["url"].endswith("two.jpg")


def test_corrupt_store_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    playlists, store = _load_playlists(monkeypatch)
    store.loaded = ["not", "a", "mapping"]
    manager = playlists.PlaylistManager(SimpleNamespace())
    asyncio.run(manager.async_setup())
    assert manager.playlists == []
    assert manager.assignments == {}

    store.loaded = {"playlists": None, "assignments": []}
    manager = playlists.PlaylistManager(SimpleNamespace())
    asyncio.run(manager.async_setup())
    assert manager.playlists == []
    assert manager.assignments == {}
