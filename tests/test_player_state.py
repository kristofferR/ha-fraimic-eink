"""Player state keeps confirmed manual artwork separate from playlist position."""

from importlib.util import module_from_spec, spec_from_file_location
import sys
from types import ModuleType, SimpleNamespace

import pytest
from conftest import PKG_DIR, load


@pytest.fixture
def player_api(monkeypatch):
    load("const")
    # These HTTP/HA collaborators are not involved in constructing player state.
    imports = {
        "aiohttp": "web",
        "homeassistant.components.http": "KEY_HASS HomeAssistantView",
        "homeassistant.config_entries": "ConfigEntry",
        "homeassistant.core": "HomeAssistant",
        "homeassistant.exceptions": "HomeAssistantError",
        "homeassistant.util": "dt",
        "fraimic.api": "FraimicError",
        "fraimic.art_packs": "ArtPackManager ArtPackNotFoundError get_pack_manager",
        "fraimic.coordinator": "REDISCOVERY_FAIL_THRESHOLD",
        "fraimic.frame_name": "frame_display_name",
        "fraimic.gallery_http": "FAVORITES_ALBUM LIBRARY_SOURCE gallery_views",
        "fraimic.helpers": "loaded_fraimic_entries",
        "fraimic.http_helpers": "require_loaded_entry",
        "fraimic.library": "FraimicLibrary async_delete_library_image get_library",
        "fraimic.overlays_http": "overlay_views",
        "fraimic.playlists": "DATA_PLAYLISTS PlaylistManager",
        "fraimic.playlists_http": "async_picture_thumbnail_response playlist_views",
        "fraimic.scenes": "SceneManager SceneNotFoundError get_scene_manager",
        "fraimic.screens_http": "screens_views",
        "fraimic.services": "begin_external_upload finish_external_upload",
    }
    for name, attributes in imports.items():
        stub = ModuleType(name)
        for attribute in attributes.split():
            setattr(stub, attribute, type(attribute, (), {}))
        monkeypatch.setitem(sys.modules, name, stub)
    spec = spec_from_file_location("fraimic.http_api", PKG_DIR / "http_api.py")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(
        module, "_frame_payload", lambda *_: {"unreachable": False, "asleep": False}
    )
    monkeypatch.setattr(module, "get_library", lambda _: None)
    return module


@pytest.mark.parametrize(
    ("media_title", "art", "preview", "expected_title", "expected_artist"),
    [
        ("camera.front_door", None, b"confirmed-camera", "camera.front_door", None),
        ("photo.jpg", None, b"confirmed-library", "photo.jpg", None),
        (
            "fallback",
            {"title": "Elk", "artist": "Bierstadt"},
            b"confirmed-art",
            "Elk",
            "Bierstadt",
        ),
        (None, None, None, None, None),
    ],
)
def test_manual_display_survives_cleared_scheduler_hash(
    player_api, media_title, art, preview, expected_title, expected_artist
):
    scheduler = SimpleNamespace(
        playlist_id="playlist-1",
        playlist_name="Evening art",
        current_screen=SimpleNamespace(name="Unconfirmed playlist slide"),
        displayed_hash=None,
        screens=[object()],
        playlist_interval=None,
        last_rotation=None,
        hold_until=None,
        busy=False,
        external_upload_active=False,
        queued_slides=[],
        playlist_up_next=lambda limit: [],
        sending_slide_name=None,
        enabled=True,
        shuffle=False,
    )
    runtime = SimpleNamespace(
        scheduler=scheduler,
        last_art=art,
        media_title=media_title,
        displayed_preview=preview,
        displayed_preview_version=3,
        send_queue=None,
        last_overlay_count=0,
    )
    entry = SimpleNamespace(entry_id="frame-1", runtime_data=runtime)

    payload = player_api._player_payload(SimpleNamespace(data={}), entry)

    assert payload["current"]["id"] is None
    assert payload["current"]["title"] == expected_title
    assert payload["current"]["artist"] == expected_artist
    assert payload["current"]["thumbnail_url"] == (
        "/api/fraimic/player/artwork/frame-1?v=3" if preview else None
    )
    assert payload["playlist_id"] == "playlist-1"
    assert payload["transport_available"] is True
