"""Gallery previews use panel pixels and isolate render settings in the cache."""

import asyncio
import io
import sys
from importlib.util import module_from_spec, spec_from_file_location
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from conftest import PKG_DIR, load
from test_render_display import _load_display


@pytest.fixture
def gallery(monkeypatch):
    _load_display(monkeypatch)
    imports = {
        "homeassistant.components.http": "KEY_HASS HomeAssistantView",
        "homeassistant.exceptions": "HomeAssistantError",
        "fraimic.artwork_cache": "get_artwork_cache",
        "fraimic.http_helpers": "require_loaded_entry",
        "fraimic.library": "FraimicLibrary get_library",
        "fraimic.playlists": "DATA_PLAYLISTS PlaylistManager",
        "fraimic.providers": "PROVIDERS available_provider_keys get_provider",
        "fraimic.providers.ha": (
            "ArtFetchError async_art_by_media_id async_fetch_art "
            "async_browse_candidates async_browse_provider async_candidate_by_media_id"
        ),
        "fraimic.source": "async_get_source_bytes",
    }
    for name, attributes in imports.items():
        stub = ModuleType(name)
        if name == "fraimic.providers":
            stub.__path__ = [str(PKG_DIR / "providers")]
        for attribute in attributes.split():
            base = Exception if attribute.endswith("Error") else object
            setattr(stub, attribute, type(attribute, (base,), {}))
        monkeypatch.setitem(sys.modules, name, stub)
    # A tiny HTTP surface keeps these tests independent of a HA installation.
    web = SimpleNamespace(
        Response=lambda **kwargs: SimpleNamespace(**kwargs),
        HTTPBadRequest=type("HTTPBadRequest", (Exception,), {}),
        HTTPBadGateway=type("HTTPBadGateway", (Exception,), {}),
        HTTPInternalServerError=type("HTTPInternalServerError", (Exception,), {}),
    )
    aiohttp = ModuleType("aiohttp")
    aiohttp.web = web
    monkeypatch.setitem(sys.modules, "aiohttp", aiohttp)
    spec = spec_from_file_location("fraimic.gallery_http", PKG_DIR / "gallery_http.py")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_native_preview_decodes_upload_buffer_and_keys_every_setting(
    gallery, monkeypatch
):
    ic = load("image_convert")
    import numpy as np

    packed = ic._pack_nibbles(np.arange(32, dtype=np.uint8) % 6, 8, 4)
    convert = AsyncMock(return_value=(packed, b"small-preview", "bayer"))
    services = ModuleType("fraimic.services")
    services.async_convert_for_entry = convert
    monkeypatch.setitem(sys.modules, "fraimic.services", services)
    entry = SimpleNamespace(entry_id="frame", data={"width": 8, "height": 4}, options={"rotation": 270})
    monkeypatch.setattr(gallery, "require_loaded_entry", lambda *_: entry)
    monkeypatch.setattr(
        sys.modules["fraimic.providers.ha"],
        "async_art_by_media_id",
        AsyncMock(return_value=SimpleNamespace(data=b"original", candidate=SimpleNamespace(attribution=None))),
    )

    async def executor(function, *args):
        return function(*args)

    hass = SimpleNamespace(data={}, async_add_executor_job=executor)
    query = dict(
        entry_id="frame",
        source="met",
        item_id="art",
        mode="bayer",
        tone="soft",
        crop="[0,0,0.5,1]",
        resolution="native",
    )

    async def run():
        view = gallery.GalleryPreviewView()
        request = SimpleNamespace(app={gallery.KEY_HASS: hass}, query=query)
        first, second = await asyncio.gather(view.get(request), view.get(request))
        assert first.body == second.body
        assert convert.await_count == 1
        preview = Image.open(io.BytesIO(first.body))
        assert preview.size == (4, 8)
        assert first.body == ic.bin_to_png(packed, 8, 4, 90)
        assert convert.call_args.args[3] == {
            "fit": "cover",
            "mode": "bayer",
            "tone": 0.0,
            "crop": (0, 0, 0.5, 1),
        }
        # Each visible control and the panel settings must invalidate the result.
        for field, value in (
            ("tone", "vivid"),
            ("mode", "none"),
            ("fit", "contain"),
            ("crop", "[0,0,1,1]"),
        ):
            query[field] = value
            await view.get(request)
        assert convert.await_count == 5
        entry.options["rotation"] = 0
        assert Image.open(io.BytesIO((await view.get(request)).body)).size == (8, 4)
        query["resolution"] = "thumbnail"
        assert (await view.get(request)).body == load("render.display").thumbnail_preview(
            ic.bin_to_png(packed, 8, 4)
        )
        assert convert.await_count == 7

    asyncio.run(run())


def test_saved_gallery_and_queue_preview_match_and_invalidate_transforms(gallery, monkeypatch):
    services = ModuleType("fraimic.services")
    services.async_convert_for_entry = AsyncMock()
    monkeypatch.setitem(sys.modules, "fraimic.services", services)
    packed = bytes(8 * 4 // 2)
    render = AsyncMock(return_value=(packed, b"unused-thumbnail", "atkinson"))
    image = SimpleNamespace(crops={"8x4": [0, 0, .5, 1]}, rotations={})
    library = SimpleNamespace(async_render_for_entry=render, get=lambda _: image)
    monkeypatch.setattr(
        sys.modules["fraimic.library"], "get_library", lambda _: library,
    )
    entry = SimpleNamespace(entry_id="frame", data={"width": 8, "height": 4}, options={})
    monkeypatch.setattr(gallery, "require_loaded_entry", lambda *_: entry)

    async def executor(function, *args):
        return function(*args)

    hass = SimpleNamespace(data={}, async_add_executor_job=executor)
    query = dict(entry_id="frame", source="saved", item_id="art", fit="cover",
                 mode="atkinson", tone="vivid", crop="[0,0,0.5,1]", resolution="native")
    request = SimpleNamespace(app={gallery.KEY_HASS: hass}, query=query)

    async def run():
        view = gallery.GalleryPreviewView()
        result = await view.get(request)
        render.assert_awaited_once_with("art", entry, {
            "fit": "cover", "mode": "atkinson", "tone": load("const").PLAYLIST_TONE_VALUES["vivid"],
            "crop": (0, 0, .5, 1),
        })
        screen = gallery.screen_from_dict(gallery._slide_data(
            {"source": "saved", "id": "art", "title": "Queued art"},
            fit="cover", mode="atkinson", tone="vivid", crop=(0, 0, .5, 1),
        ))
        display = load("render.display")
        queued, _ = await display.async_preview_screen(hass, entry, screen)
        assert result.body == queued == await display.async_prepared_preview(hass, entry, screen)
        count = render.await_count
        await view.get(request)
        assert render.await_count == count
        image.rotations["8x4"] = 90
        await view.get(request)
        image.crops["8x4"] = [0, 0, 1, 1]
        await view.get(request)
        assert render.await_count == count + 2

    asyncio.run(run())


def test_detail_includes_saved_rotation_in_original_crop_coordinates(gallery, monkeypatch):
    entry = SimpleNamespace(entry_id="frame", data={"width": 1440, "height": 2560}, options={"rotation": 90})
    monkeypatch.setattr(gallery, "require_loaded_entry", lambda *_: entry)
    monkeypatch.setattr(gallery, "_resolve_item", AsyncMock(return_value={"id": "art"}))
    crop = (0, .25, 1, .75)
    image = SimpleNamespace(crop_for=lambda *_: crop, rotation_for=lambda *_: 90)
    monkeypatch.setattr(gallery, "_library", lambda _: SimpleNamespace(get=lambda _: image))
    view = gallery.GalleryDetailView()
    view.json = lambda body: body
    result = asyncio.run(view.get(SimpleNamespace(
        app={gallery.KEY_HASS: object()}, query={"entry_id": "frame", "source": "saved", "item_id": "art"}
    )))
    assert result["saved_rotation"] == 90
    assert result["saved_crop"] == crop


@pytest.mark.parametrize("source,cache_mode,expected", [
    ("met", "off", False), ("met", "30_days", True),
    ("met", "forever", True), ("saved", "off", True),
])
def test_detail_warms_alternatives_only_with_reusable_source(
    gallery, monkeypatch, source, cache_mode, expected
):
    entry = SimpleNamespace(entry_id="frame", data={}, options={"artwork_cache": cache_mode})
    monkeypatch.setattr(gallery, "require_loaded_entry", lambda *_: entry)
    monkeypatch.setattr(gallery, "_resolve_item", AsyncMock(return_value={"id": "art"}))
    image = SimpleNamespace(crop_for=lambda *_: None, rotation_for=lambda *_: 0)
    monkeypatch.setattr(gallery, "_library", lambda _: SimpleNamespace(get=lambda _: image))
    view = gallery.GalleryDetailView()
    view.json = lambda body: body
    result = asyncio.run(view.get(SimpleNamespace(
        app={gallery.KEY_HASS: object()}, query={"entry_id": "frame", "source": source, "item_id": "art"}
    )))
    assert result["warm_previews"] is expected
