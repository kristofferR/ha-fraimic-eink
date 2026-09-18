"""Player state keeps confirmed manual artwork separate from playlist position."""

import sys
from importlib.util import module_from_spec, spec_from_file_location
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


def _entry(media_title=None, art=None, preview=None):
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
        sending_started_at=None,
        enabled=True,
        shuffle=False,
        exhausted=False,
        blocked_reason=None,
        retry_at=None,
        queue=SimpleNamespace(repeat=False),
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

    return entry


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
    entry = _entry(media_title, art, preview)

    payload = player_api._player_payload(SimpleNamespace(data={}), entry)

    assert payload["current"]["id"] is None
    assert payload["current"]["title"] == expected_title
    assert payload["current"]["artist"] == expected_artist
    assert payload["current"]["thumbnail_url"] == (
        "/api/fraimic/player/artwork/frame-1?v=3" if preview else None
    )
    assert payload["playlist_id"] == "playlist-1"
    assert payload["transport_available"] is True


@pytest.mark.parametrize("kind", ["sending", "cloud", "rendering"])
def test_player_previews_submission_without_claiming_display(player_api, kind):
    entry = _entry("Old artwork", preview=b"old-preview")
    runtime = entry.runtime_data
    runtime.cloud = SimpleNamespace(preview_png=b"cloud-preview", preview_title="Cloud artwork", upload_id="upload-1")
    if kind == "sending":
        runtime.sending_preview = (b"new-preview", "New artwork")
    elif kind == "rendering":
        runtime.scheduler.sending_screen = SimpleNamespace(
            screen_id="slide-2", name="Rendering artwork", kind="picture",
            source={"library_image": "image-2"},
        )
    payload = player_api._player_payload(SimpleNamespace(data={}), entry)
    assert payload["current"]["title"] == "Old artwork"
    assert payload["current"]["thumbnail_url"] == "/api/fraimic/player/artwork/frame-1?v=3"
    preview = payload["preview"]
    if kind == "rendering":
        assert preview["thumbnail_url"] == "/api/fraimic/library/thumb/image-2"
        assert preview["title"] == "Rendering artwork"
    else:
        assert f"kind={kind}&v=" in preview["thumbnail_url"]
        assert preview["title"] == ("New artwork" if kind == "sending" else "Cloud artwork")
    assert preview["status"] == ("submitted" if kind == "cloud" else "sending")


@pytest.mark.parametrize("kind", ["confirmed", "cloud", "stale_cloud", "sending", "completed", "cloud_completed", "stale"])
def test_artwork_serves_selected_preview_without_mixing_sends(player_api, monkeypatch, kind):
    import asyncio
    import hashlib

    entry = _entry(preview=b"confirmed")
    runtime = entry.runtime_data
    runtime.cloud = SimpleNamespace(preview_png=b"cloud", upload_id="current-upload")
    runtime.sending_preview = (b"sending", "New artwork") if kind == "sending" else None
    monkeypatch.setattr(player_api, "require_loaded_entry", lambda *_: entry)
    class NotFound(Exception):
        def __init__(self, *, text):
            super().__init__(text)
    monkeypatch.setattr(player_api.web, "HTTPNotFound", NotFound, raising=False)
    monkeypatch.setattr(player_api.web, "Response", lambda **kwargs: kwargs, raising=False)
    query = {}
    expected = b"confirmed"
    if kind in ("cloud", "stale_cloud"):
        query["kind"] = "cloud"
        query["v"] = "old-upload" if kind == "stale_cloud" else "current-upload"
        expected = b"cloud"
    elif kind in ("sending", "completed", "cloud_completed", "stale"):
        query["kind"] = "sending"
        expected = b"sending" if kind in ("sending", "stale") else b"confirmed"
        if kind == "cloud_completed":
            expected = b"cloud"
        query["v"] = hashlib.sha256(expected).hexdigest()
    request = SimpleNamespace(app={player_api.KEY_HASS: object()}, query=query)
    call = player_api.PlayerArtworkView().get(request, "frame-1")
    if kind in ("stale", "stale_cloud"):
        with pytest.raises(NotFound):
            asyncio.run(call)
    else:
        response = asyncio.run(call)
        assert response["body"] == expected
        assert response["content_type"] == "image/png"
        assert response["headers"]["Cache-Control"] == "private, no-store"



def test_rendering_direct_send_does_not_reuse_prior_cloud_preview(player_api):
    entry = _entry()
    entry.runtime_data.scheduler.external_upload_active = True
    entry.runtime_data.cloud = SimpleNamespace(
        preview_png=b"old-image", preview_title="Old artwork", upload_id="old-upload",
    )
    payload = player_api._player_payload(SimpleNamespace(data={}), entry)
    assert payload["state"] == "sending"
    assert payload["preview"] is None


def test_queue_without_playlist_has_playback_controls(player_api):
    entry = _entry()
    scheduler = entry.runtime_data.scheduler
    scheduler.playlist_id = scheduler.playlist_name = None
    scheduler.screens = []
    scheduler.enabled = False
    scheduler.queued_slides = [SimpleNamespace(screen_id="queued", name="Queued", source={})]
    payload = player_api._player_payload(SimpleNamespace(data={}), entry)
    assert payload["transport_available"]
    assert payload["paused"]
    assert payload["queue_count"] == 1
    assert payload["hand_queue"][0]["id"] == "queued"


def test_delayed_playback_explains_wait_instead_of_zero_countdown(player_api):
    from datetime import datetime, timezone
    entry = _entry("Displayed")
    scheduler = entry.runtime_data.scheduler
    scheduler.blocked_reason = "low_battery"
    scheduler.retry_at = datetime(2026, 9, 18, 15, tzinfo=timezone.utc)
    payload = player_api._player_payload(SimpleNamespace(data={}), entry)
    assert payload["state"] == "waiting"
    assert payload["seconds_remaining"] is None
    assert payload["delay"]["reason"] == "low_battery"
    assert payload["delay"]["retry_at"] == "2026-09-18T15:00:00+00:00"
