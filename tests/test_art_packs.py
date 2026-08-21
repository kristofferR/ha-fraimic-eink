"""Focused transactional tests for art-pack installs."""

from __future__ import annotations

import asyncio
import sys
import types

import pytest
from conftest import load


@pytest.fixture
def art_packs_module(monkeypatch: pytest.MonkeyPatch):
    """Load art_packs with its Home Assistant boundary stubbed."""
    homeassistant = types.ModuleType("homeassistant")
    homeassistant.__path__ = []
    core = types.ModuleType("homeassistant.core")
    core.HomeAssistant = object
    core.callback = lambda function: function
    exceptions = types.ModuleType("homeassistant.exceptions")
    exceptions.HomeAssistantError = type("HomeAssistantError", (Exception,), {})
    helpers_pkg = types.ModuleType("homeassistant.helpers")
    helpers_pkg.__path__ = []
    aiohttp_client = types.ModuleType("homeassistant.helpers.aiohttp_client")
    aiohttp_client.async_get_clientsession = lambda _hass: None
    storage = types.ModuleType("homeassistant.helpers.storage")
    storage.Store = lambda *_args, **_kwargs: object()

    integration_helpers = types.ModuleType("fraimic.helpers")
    integration_helpers.loaded_fraimic_entries = lambda _hass: []
    library = types.ModuleType("fraimic.library")
    library.FraimicLibrary = object
    provider_ha = types.ModuleType("fraimic.providers.ha")
    provider_ha.ArtFetchError = exceptions.HomeAssistantError
    provider_ha.async_browse_provider = None
    scenes = types.ModuleType("fraimic.scenes")
    scenes.SceneManager = object

    for name, module in {
        "homeassistant": homeassistant,
        "homeassistant.core": core,
        "homeassistant.exceptions": exceptions,
        "homeassistant.helpers": helpers_pkg,
        "homeassistant.helpers.aiohttp_client": aiohttp_client,
        "homeassistant.helpers.storage": storage,
        "fraimic.helpers": integration_helpers,
        "fraimic.library": library,
        "fraimic.providers.ha": provider_ha,
        "fraimic.scenes": scenes,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)

    previous = sys.modules.pop("fraimic.art_packs", None)
    try:
        yield load("art_packs")
    finally:
        sys.modules.pop("fraimic.art_packs", None)
        if previous is not None:
            sys.modules["fraimic.art_packs"] = previous


def test_failed_replacement_keeps_stale_images_and_scene(
    art_packs_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    art_packs = art_packs_module
    monkeypatch.setattr(art_packs, "DOWNLOAD_DELAY_DEFAULT", 0)

    class Library:
        def __init__(self) -> None:
            self.images = {"old-image": types.SimpleNamespace()}
            self.deleted: list[str] = []

        async def async_add_image(self, _data, _filename, **_kwargs):
            image = types.SimpleNamespace(image_id="new-image")
            self.images[image.image_id] = image
            return image

        async def async_delete_image(self, image_id: str) -> None:
            self.deleted.append(image_id)
            self.images.pop(image_id, None)

    library = Library()
    manager = art_packs.ArtPackManager(object(), library, object())
    manager.packs = [
        {
            "id": "changing-pack",
            "name": "Changing Pack",
            "images": [
                {
                    "title": "New one",
                    "url": "https://example.com/new-one.jpg",
                    "filename": "New one.jpg",
                },
                {
                    "title": "New two",
                    "url": "https://example.com/new-two.jpg",
                    "filename": "New two.jpg",
                },
            ],
        }
    ]
    manager.installed = {
        "changing-pack": {
            "name": "Changing Pack",
            "images": {"https://example.com/old.jpg": "old-image"},
            "metadata": {"https://example.com/old.jpg": {"title": "Old"}},
            "total": 1,
            "scene_id": "working-scene",
        }
    }

    async def download(_session, url: str) -> bytes:
        if url.endswith("new-two.jpg"):
            raise art_packs.HomeAssistantError("host unavailable")
        return b"image"

    async def save() -> None:
        return None

    async def unexpected_scene_sync(*_args):
        raise AssertionError("a partial replacement must keep the existing scene")

    manager._async_download = download
    manager._async_save = save
    manager._async_sync_pack_scene = unexpected_scene_sync

    result = asyncio.run(manager.async_install("changing-pack"))

    assert result["installed_count"] == 1
    assert result["scene_id"] == "working-scene"
    assert len(result["failed"]) == 1
    assert library.deleted == []
    assert manager.installed["changing-pack"]["images"] == {
        "https://example.com/old.jpg": "old-image",
        "https://example.com/new-one.jpg": "new-image",
    }
    assert manager._active_install_progress == {}
