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


@pytest.fixture
def gallery(monkeypatch):
    load("const")
    imports = {
        "homeassistant.components.http": "KEY_HASS HomeAssistantView",
        "homeassistant.exceptions": "HomeAssistantError",
        "fraimic.artwork_cache": "get_artwork_cache",
        "fraimic.helpers": "resolve_render_params",
        "fraimic.http_helpers": "require_loaded_entry",
        "fraimic.library": "FraimicLibrary get_library",
        "fraimic.playlists": "DATA_PLAYLISTS PlaylistManager",
        "fraimic.providers": "PROVIDERS available_provider_keys get_provider",
        "fraimic.providers.ha": (
            "ArtFetchError artwork_source_cache_id async_art_by_media_id "
            "async_browse_candidates async_browse_provider async_candidate_by_media_id"
        ),
        "fraimic.render.schema": "SCREEN_SCHEMA screen_from_dict",
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
    entry = SimpleNamespace(entry_id="frame", data={}, options={})
    params = {"width": 8, "height": 4, "preview_rotate": 90}
    monkeypatch.setattr(gallery, "resolve_render_params", lambda *_: params.copy())
    monkeypatch.setattr(gallery, "require_loaded_entry", lambda *_: entry)
    monkeypatch.setattr(gallery, "artwork_source_cache_id", lambda *_: "source")
    monkeypatch.setattr(
        gallery,
        "async_art_by_media_id",
        AsyncMock(return_value=SimpleNamespace(data=b"original")),
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
            "tone_name": "soft",
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
        params["preview_rotate"] = 0
        assert Image.open(io.BytesIO((await view.get(request)).body)).size == (8, 4)
        query["resolution"] = "thumbnail"
        assert (await view.get(request)).body == b"small-preview"
        assert convert.await_count == 7

    asyncio.run(run())


def test_saved_gallery_preview_passes_native_size_and_tone(gallery, monkeypatch):
    services = ModuleType("fraimic.services")
    services.async_convert_for_entry = AsyncMock()
    monkeypatch.setitem(sys.modules, "fraimic.services", services)
    render = AsyncMock(return_value=b"native-preview")
    monkeypatch.setattr(
        gallery,
        "_library",
        lambda _: SimpleNamespace(async_render_adhoc_preview=render),
    )
    entry = object()
    result = asyncio.run(
        gallery.GalleryPreviewView()._render(
            object(),
            entry,
            "saved",
            "art",
            "cover",
            "atkinson",
            "vivid",
            (0, 0, 0.5, 1),
            "native",
        )
    )
    assert result == b"native-preview"
    render.assert_awaited_once_with(
        "art",
        entry,
        [0, 0, 0.5, 1],
        overrides={"fit": "cover", "mode": "atkinson", "tone_name": "vivid"},
        full_resolution=True,
    )
