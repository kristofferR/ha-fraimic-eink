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


def test_reframed_refresh_without_loaded_frame_is_rate_limited(
    art_packs_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    art_packs = art_packs_module
    monkeypatch.setattr(art_packs.time, "time", lambda: 1_000.0)
    manager = art_packs.ArtPackManager(object(), types.SimpleNamespace(), object())

    asyncio.run(manager.async_refresh_reframed())

    assert manager._reframed_fetched_at == 1_000.0
    assert manager.reframed_refreshing is False


def test_failed_reframed_refresh_uses_failure_ttl_with_cached_packs(
    art_packs_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    art_packs = art_packs_module
    now = 1_000.0
    monkeypatch.setattr(art_packs.time, "time", lambda: now)
    monkeypatch.setattr(art_packs, "loaded_fraimic_entries", lambda _hass: [object()])

    async def fail_refresh(*_args: object) -> None:
        raise art_packs.ArtFetchError("offline")

    monkeypatch.setattr(art_packs, "async_browse_provider", fail_refresh)
    manager = art_packs.ArtPackManager(object(), types.SimpleNamespace(), object())
    manager.reframed_packs = [{"id": "cached-pack"}]
    manager._reframed_last_refresh_succeeded = True

    asyncio.run(manager.async_refresh_reframed())

    assert manager.reframed_packs == [{"id": "cached-pack"}]
    assert manager._reframed_last_refresh_succeeded is False
    now += art_packs.REFRAMED_PACK_FAILURE_TTL + 1
    assert manager._reframed_refresh_due() is True


def test_wallhaven_catalog_exposes_all_lazy_pack_groups(art_packs_module) -> None:
    manager = art_packs_module.ArtPackManager(
        object(), types.SimpleNamespace(), object()
    )

    assert len(manager.wallhaven_packs) == 43
    assert {pack["category"] for pack in manager.wallhaven_packs} == {
        "Wallhaven Feeds",
        "Wallhaven Top",
        "Wallhaven Categories",
        "Wallhaven Colors",
    }
    assert {pack["id"] for pack in manager.wallhaven_packs} >= {
        "wh-latest",
        "wh-top-1m",
        "wh-category-100",
        "wh-color-000000",
    }
    assert all(pack["provider_key"] == "wallhaven" for pack in manager.wallhaven_packs)


def test_wallhaven_pack_materializes_through_provider(
    art_packs_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    art_packs = art_packs_module
    entry = types.SimpleNamespace(
        data={art_packs.CONF_WIDTH: 1600, art_packs.CONF_HEIGHT: 1200},
        options={},
    )
    monkeypatch.setattr(art_packs, "loaded_fraimic_entries", lambda _hass: [entry])
    candidate = types.SimpleNamespace(
        item_id="mlg7qm",
        image_url="https://w.wallhaven.cc/full/ml/wallhaven-mlg7qm.jpg",
        thumb_url="https://th.wallhaven.cc/lg/ml/mlg7qm.jpg",
        title="General Wallpaper mlg7qm",
        artist=None,
        license=None,
        attribution="General Wallpaper mlg7qm, Wallhaven",
        width=3840,
        height=2160,
        extra={"source_url": "https://wallhaven.cc/w/mlg7qm"},
    )

    async def browse(
        _hass, actual_entry, provider_key, provider_path
    ) -> types.SimpleNamespace:
        assert actual_entry is entry
        assert provider_key == "wallhaven"
        assert provider_path == "top/1M"
        return types.SimpleNamespace(candidates=(candidate,), folders=())

    monkeypatch.setattr(art_packs, "async_browse_provider", browse)
    manager = art_packs.ArtPackManager(object(), types.SimpleNamespace(), object())

    pack = asyncio.run(manager.async_gallery("wh-top-1m"))

    assert pack["image_count"] == 1
    assert pack["images"][0]["filename"] == "General Wallpaper mlg7qm.jpg"


def test_wallhaven_pack_rejects_extreme_aspect_candidates(
    art_packs_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    art_packs = art_packs_module
    entry = types.SimpleNamespace(
        data={art_packs.CONF_WIDTH: 1600, art_packs.CONF_HEIGHT: 1200},
        options={},
    )
    monkeypatch.setattr(art_packs, "loaded_fraimic_entries", lambda _hass: [entry])

    def candidate(item_id: str, width: int, height: int) -> types.SimpleNamespace:
        return types.SimpleNamespace(
            item_id=item_id,
            image_url=f"https://w.wallhaven.cc/full/aa/wallhaven-{item_id}.jpg",
            thumb_url=None,
            title=f"Wallpaper {item_id}",
            artist=None,
            license=None,
            attribution=f"Wallpaper {item_id}, Wallhaven",
            width=width,
            height=height,
            extra={"source_url": f"https://wallhaven.cc/w/{item_id}"},
        )

    async def browse(
        _hass, _entry, _provider_key, _provider_path
    ) -> types.SimpleNamespace:
        return types.SimpleNamespace(
            candidates=(
                candidate("aaaaaa", 6000, 1500),
                candidate("bbbbbb", 2400, 1600),
            ),
            folders=(),
        )

    monkeypatch.setattr(art_packs, "async_browse_provider", browse)
    manager = art_packs.ArtPackManager(object(), types.SimpleNamespace(), object())

    pack = asyncio.run(manager.async_gallery("wh-top-1m"))

    assert [image["title"] for image in pack["images"]] == ["Wallpaper bbbbbb"]


def test_wallhaven_pack_balances_loaded_frame_orientations(
    art_packs_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    art_packs = art_packs_module
    landscape = types.SimpleNamespace(
        data={art_packs.CONF_WIDTH: 1600, art_packs.CONF_HEIGHT: 1200},
        options={},
    )
    portrait = types.SimpleNamespace(
        data={art_packs.CONF_WIDTH: 1600, art_packs.CONF_HEIGHT: 1200},
        options={art_packs.CONF_ROTATION: 90},
    )
    monkeypatch.setattr(
        art_packs,
        "loaded_fraimic_entries",
        lambda _hass: [landscape, portrait],
    )
    calls: list[object] = []

    async def browse(
        _hass, entry, provider_key, provider_path
    ) -> types.SimpleNamespace:
        calls.append(entry)
        is_portrait = entry is portrait
        item_id = "pppppp" if is_portrait else "llllll"
        width, height = (1600, 2400) if is_portrait else (2400, 1600)
        candidate = types.SimpleNamespace(
            item_id=item_id,
            image_url=f"https://w.wallhaven.cc/full/aa/wallhaven-{item_id}.jpg",
            thumb_url=None,
            title="Portrait" if is_portrait else "Landscape",
            artist=None,
            license=None,
            attribution="Wallhaven",
            width=width,
            height=height,
            extra={"source_url": f"https://wallhaven.cc/w/{item_id}"},
        )
        assert provider_key == "wallhaven"
        assert provider_path == "top/1M"
        return types.SimpleNamespace(candidates=(candidate,), folders=())

    monkeypatch.setattr(art_packs, "async_browse_provider", browse)
    manager = art_packs.ArtPackManager(object(), types.SimpleNamespace(), object())

    pack = asyncio.run(manager.async_gallery("wh-top-1m"))

    assert calls == [landscape, portrait]
    assert [image["title"] for image in pack["images"]] == [
        "Landscape",
        "Portrait",
    ]
