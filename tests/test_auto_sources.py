"""Auto mode sources resolve to concrete, repeat-aware picture slides."""

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from importlib.util import module_from_spec, spec_from_file_location
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from conftest import PKG_DIR, load
from test_gallery_preview import gallery  # noqa: F401 - fixture

NOW = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)


@pytest.fixture
def resolver(gallery, monkeypatch):  # noqa: F811 - fixture
    monkeypatch.setitem(sys.modules, "fraimic.gallery_http", gallery)
    providers_ha = sys.modules["fraimic.providers.ha"]
    providers_ha.async_remember_candidate = AsyncMock()
    spec = spec_from_file_location("fraimic.auto_sources", PKG_DIR / "auto_sources.py")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.dt_util, "utcnow", lambda: NOW, raising=False)
    monkeypatch.setattr(module, "get_provider", lambda key: SimpleNamespace(name=key.title()))
    return module


def _resolve(resolver, source, *, settings=None, history=None, exclude=(), playlists=None):
    auto = load("auto_mode")
    entry = SimpleNamespace(data={"width": 1600, "height": 1200}, options={})
    return asyncio.run(
        resolver.async_resolve_pick(
            SimpleNamespace(),
            entry,
            settings or auto.AutoSettings(),
            auto.AutoSource(**source),
            history or auto.AutoHistory(),
            exclude=set(exclude),
            playlists=playlists,
        )
    )


def _candidate(item_id, width=None, height=None):
    base = load("providers.base")
    return base.ArtCandidate(
        provider="reframed", item_id=item_id, image_url=f"https://art.example/{item_id}.jpg",
        title=item_id.title(), artist="Monet", width=width, height=height,
    )


def test_library_folder_skips_recent_and_misfit_art(resolver, monkeypatch):
    model = load("library_model")
    auto = load("auto_mode")
    images = {
        name: model.LibraryImage(
            name, f"{name}.jpg", "image/jpeg", 1, width=width, height=height,
            albums=["Favorites"],
        )
        for name, width, height in (
            ("shown", 1600, 1200), ("fresh", 1600, 1200), ("tall", 300, 3000),
        )
    }
    monkeypatch.setattr(resolver, "get_library", lambda _: SimpleNamespace(images=images))
    history = auto.AutoHistory()
    history.record("library:shown", NOW - timedelta(days=1))
    source = {"kind": "gallery", "source": "saved", "browse_id": "favorites"}
    slide = _resolve(resolver, source, history=history)
    assert slide.source["library_image"] == "fresh"
    assert "fit" not in slide.source  # follows the frame default
    strict = auto.AutoSettings().updated({"orientation": "strict"})
    assert _resolve(resolver, source, settings=strict, history=history, exclude={"library:fresh"}).source["library_image"] == "shown"


def test_folder_of_folders_picks_a_subfolder_and_remembers_the_pick(resolver, monkeypatch):
    auto = load("auto_mode")
    base = load("providers.base")
    pages = {
        "collections": base.BrowsePage(
            title="Collections",
            folders=(base.BrowseFolder("collections/monet", "Monet"),), candidates=(),
        ),
        "collections/monet": base.BrowsePage(
            title="Monet", folders=(),
            candidates=(_candidate("haystacks", 1600, 1200),),
        ),
    }
    browse = AsyncMock(side_effect=lambda _h, _e, _p, browse_id: pages[browse_id])
    monkeypatch.setattr(resolver, "async_browse_provider", browse)
    settings = auto.AutoSettings().updated({"caption": True, "tone": "vivid"})
    slide = _resolve(
        resolver, {"kind": "gallery", "source": "reframed", "browse_id": "collections"},
        settings=settings,
    )
    assert slide.source["provider_item"] == "haystacks"
    assert slide.source["caption"] and slide.source["tone"] == "vivid"
    assert slide.source["metadata"]["download_url"] == "https://art.example/haystacks.jpg"
    resolver.async_remember_candidate.assert_awaited_once()


def test_random_online_pick_retries_recent_art(resolver, monkeypatch):
    auto = load("auto_mode")
    draws = iter([_candidate("old"), _candidate("new")])
    fetch = AsyncMock(side_effect=lambda *_a, **_k: SimpleNamespace(candidate=next(draws), data=b""))
    monkeypatch.setattr(resolver, "async_fetch_art", fetch)
    history = auto.AutoHistory()
    history.record("provider:reframed:old", NOW)
    slide = _resolve(resolver, {"kind": "shuffle"}, history=history)
    assert slide.source["provider_item"] == "new"
    assert fetch.await_args.args[2] == "shuffle"


def test_deleted_playlist_is_reported(resolver):
    playlists = SimpleNamespace(get=lambda _: None)
    with pytest.raises(Exception, match="no longer exists"):
        _resolve(resolver, {"kind": "playlist", "playlist_id": "gone"}, playlists=playlists)
