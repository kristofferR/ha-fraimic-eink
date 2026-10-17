"""Auto mode sources resolve to concrete, repeat-aware picture slides."""

import asyncio
import io
import json
import sys
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from importlib.util import module_from_spec, spec_from_file_location
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image
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

    async def executor(function, *args):
        return function(*args)

    return asyncio.run(
        resolver.async_resolve_pick(
            SimpleNamespace(async_add_executor_job=executor),
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


@pytest.mark.parametrize(
    "dimensions,expected",
    [
        ([(None, None), (300, 3000)], [(None, None)]),
        ([(1600, 1200), (None, None), (300, 3000)], [(1600, 1200), (None, None)]),
        ([(300, 3000)], [(300, 3000)]),
    ],
)
def test_suitable_prefers_matches_and_unknown_sizes(resolver, dimensions, expected):
    auto = load("auto_mode")
    entry = SimpleNamespace(data={"width": 1600, "height": 1200}, options={})
    picker = resolver._Picker(None, entry, auto.AutoSettings(), auto.AutoHistory(), set())
    assert picker._suitable(dimensions, lambda size: size) == expected


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


@pytest.mark.parametrize("state", ["fresh", "recent", "queued", "exhausted", "all_queued"])
def test_folder_checks_later_pages_before_reusing_art(resolver, monkeypatch, state):
    auto = load("auto_mode")
    base = load("providers.base")
    pages = {
        "art": base.BrowsePage(
            title="Art", candidates=(_candidate("first", 1600, 1200),),
            folders=(base.BrowseFolder("art/page/2", "Page 2"),),
        ),
        "art/page/2": base.BrowsePage(
            title="Page 2", candidates=(_candidate("second", 1600, 1200),),
        ),
    }
    browse = AsyncMock(side_effect=lambda _h, _e, _p, browse_id: pages[browse_id])
    monkeypatch.setattr(resolver, "async_browse_provider", browse)
    history = auto.AutoHistory()
    if state == "exhausted":
        history.record("provider:reframed:second", NOW - timedelta(days=1))
    if state in ("recent", "exhausted"):
        history.record("provider:reframed:first", NOW)
    exclude = {"provider:reframed:first"} if state in ("queued", "all_queued") else set()
    if state == "all_queued":
        exclude.add("provider:reframed:second")
    source = {"kind": "gallery", "source": "reframed", "browse_id": "art"}
    settings = auto.AutoSettings().updated({"avoid_repeats_days": -1})
    if state == "all_queued":
        with pytest.raises(auto.AutoSourceQueued):
            _resolve(resolver, source, settings=settings, history=history, exclude=exclude)
    else:
        slide = _resolve(resolver, source, settings=settings, history=history, exclude=exclude)
        assert slide.source["provider_item"] == ("first" if state == "fresh" else "second")
    assert browse.await_count == (1 if state == "fresh" else 2)


def test_auto_pick_keeps_provider_callback_metadata_in_saved_queue(resolver, monkeypatch):
    base = load("providers.base")
    queue_model = load("playback_queue")
    candidate = base.ArtCandidate(
        provider="unsplash", item_id="photo-1", image_url="https://example.test/photo.jpg",
        title="Photo", attribution="Photo by Artist on Unsplash",
        extra={"download_location": "https://api.unsplash.com/photos/photo-1/download"},
    )
    monkeypatch.setattr(resolver, "async_fetch_art", AsyncMock(
        return_value=base.ArtImage(data=b"photo", candidate=candidate),
    ))
    slide = _resolve(resolver, {"kind": "shuffle"})
    queue = queue_model.PlaybackQueue()
    queue.add_auto(slide, "shuffle")
    restored = queue_model.PlaybackQueue.from_dict(json.loads(json.dumps(queue.to_dict())))

    assert restored.items[0].screen.source["metadata"]["provider_candidate"] == asdict(candidate)


def test_deleted_playlist_is_reported(resolver):
    playlists = SimpleNamespace(get=lambda _: None)
    with pytest.raises(Exception, match="no longer exists"):
        _resolve(resolver, {"kind": "playlist", "playlist_id": "gone"}, playlists=playlists)


@pytest.mark.parametrize("kind", ["library", "folder", "playlist"])
def test_fully_queued_source_is_distinct_from_an_empty_source(resolver, monkeypatch, kind):
    auto = load("auto_mode")
    base = load("providers.base")
    model = load("library_model")
    schema = load("render.schema")
    image = model.LibraryImage("only", "only.jpg", "image/jpeg", 1, width=1600, height=1200)
    images = {"only": image}
    candidates = [_candidate("only", 1600, 1200)]
    slides = [schema.screen_from_dict(schema.SCREEN_SCHEMA({"kind": "picture", "library_image": "only"}))]
    monkeypatch.setattr(resolver, "get_library", lambda _: SimpleNamespace(images=images))
    monkeypatch.setattr(resolver, "async_browse_provider", AsyncMock(side_effect=lambda *_: base.BrowsePage(
        title="Art", folders=(), candidates=tuple(candidates),
    )))
    playlists = SimpleNamespace(get=lambda _: True, render_slides=lambda _: slides)
    source = {
        "library": {"kind": "gallery", "source": "saved"},
        "folder": {"kind": "gallery", "source": "reframed", "browse_id": "art"},
        "playlist": {"kind": "playlist", "playlist_id": "favorites"},
    }[kind]
    key = "provider:reframed:only" if kind == "folder" else "library:only"
    with pytest.raises(auto.AutoSourceQueued):
        _resolve(resolver, source, exclude={key}, playlists=playlists)
    assert _resolve(resolver, source, playlists=playlists) is not None
    images.clear()
    candidates.clear()
    slides.clear()
    assert _resolve(resolver, source, exclude={key}, playlists=playlists) is None


@pytest.mark.parametrize("size,matches", [((1600, 1200), True), ((600, 3000), False)])
def test_strict_folder_checks_unknown_dimensions(resolver, monkeypatch, size, matches):
    auto = load("auto_mode")
    base = load("providers.base")
    candidate = _candidate("unknown")
    page = base.BrowsePage(title="Art", folders=(), candidates=(candidate,))
    monkeypatch.setattr(resolver, "async_browse_provider", AsyncMock(return_value=page))
    data = io.BytesIO()
    Image.new("RGB", size).save(data, format="PNG")
    fetch = AsyncMock(return_value=SimpleNamespace(data=data.getvalue(), candidate=candidate))
    monkeypatch.setattr(resolver, "async_art_by_media_id", fetch)
    slide = _resolve(
        resolver, {"kind": "gallery", "source": "reframed", "browse_id": "art"},
        settings=auto.AutoSettings().updated({"orientation": "strict"}),
    )
    assert (slide is not None) == matches
    fetch.assert_awaited_once()


@pytest.mark.parametrize("failure", ["fetch", "decode", "misfit"])
def test_strict_folder_skips_unusable_candidates_with_bounded_fetches(
    resolver, monkeypatch, failure
):
    auto = load("auto_mode")
    base = load("providers.base")
    candidates = tuple(_candidate(str(i)) for i in range(resolver.RANDOM_ATTEMPTS + 1))
    page = base.BrowsePage(title="Art", folders=(), candidates=candidates)
    monkeypatch.setattr(resolver, "async_browse_provider", AsyncMock(return_value=page))
    data = io.BytesIO()
    Image.new("RGB", (600, 3000)).save(data, format="PNG")
    fetch = AsyncMock(
        side_effect=resolver.HomeAssistantError("unreachable") if failure == "fetch" else None,
        return_value=SimpleNamespace(data=b"invalid" if failure == "decode" else data.getvalue()),
    )
    monkeypatch.setattr(resolver, "async_art_by_media_id", fetch)
    assert _resolve(
        resolver, {"kind": "gallery", "source": "reframed", "browse_id": "art"},
        settings=auto.AutoSettings().updated({"orientation": "strict"}),
    ) is None
    assert fetch.await_count == resolver.RANDOM_ATTEMPTS


def test_strict_library_rejects_unknown_dimensions(resolver, monkeypatch):
    auto = load("auto_mode")
    model = load("library_model")
    image = model.LibraryImage("unknown", "unknown.jpg", "image/jpeg", 1)
    monkeypatch.setattr(
        resolver, "get_library", lambda _: SimpleNamespace(images={"unknown": image})
    )
    assert _resolve(
        resolver, {"kind": "gallery", "source": "saved"},
        settings=auto.AutoSettings().updated({"orientation": "strict"}),
    ) is None


@pytest.mark.parametrize("kind", ["library", "provider"])
def test_strict_playlist_filters_mismatched_pictures(resolver, monkeypatch, kind):
    auto = load("auto_mode")
    schema = load("render.schema")
    model = load("library_model")
    images = {
        name: model.LibraryImage(name, f"{name}.jpg", "image/jpeg", 1, width=w, height=h)
        for name, w, h in (("wide", 1600, 1200), ("tall", 300, 3000))
    }
    monkeypatch.setattr(resolver, "get_library", lambda _: SimpleNamespace(images=images))
    metadata = AsyncMock(side_effect=lambda _h, _e, _p, item: _candidate(
        item, images[item].width, images[item].height
    ))
    monkeypatch.setattr(resolver, "async_candidate_by_media_id", metadata)
    slides = [
        replace(schema.screen_from_dict(schema.SCREEN_SCHEMA({
            "kind": "picture",
            **({"library_image": name} if kind == "library" else {
                "provider": "reframed", "provider_item": name, "caption": True,
            }),
            "fit": "cover", "tone": "soft",
        }), name), overlay_mode="none")
        for name in images
    ]
    playlists = SimpleNamespace(get=lambda _: True, render_slides=lambda _: slides)
    settings = auto.AutoSettings().updated({"orientation": "strict", "tone": "vivid"})
    source = {"kind": "playlist", "playlist_id": "art"}
    slide = _resolve(resolver, source, settings=settings, playlists=playlists)
    assert slide.screen_id == "wide"
    assert slide.source == slides[0].source
    assert slide.overlay_mode == "none"
    slides.pop(0)
    assert _resolve(resolver, source, settings=settings, playlists=playlists) is None


@pytest.mark.parametrize("fit,matches", [("cover", False), ("contain", True)])
def test_strict_playlist_uses_the_saved_fit(resolver, monkeypatch, fit, matches):
    auto = load("auto_mode")
    schema = load("render.schema")
    model = load("library_model")
    image = model.LibraryImage("tall", "tall.jpg", "image/jpeg", 1, width=1200, height=6000)
    monkeypatch.setattr(resolver, "get_library", lambda _: SimpleNamespace(images={"tall": image}))
    slide = schema.screen_from_dict(schema.SCREEN_SCHEMA({
        "kind": "picture", "library_image": "tall", "fit": fit,
    }))
    playlists = SimpleNamespace(get=lambda _: True, render_slides=lambda _: [slide])
    settings = auto.AutoSettings().updated({
        "orientation": "strict", "fit": "contain" if fit == "cover" else "cover",
    })
    assert (_resolve(
        resolver, {"kind": "playlist", "playlist_id": "art"},
        settings=settings, playlists=playlists,
    ) is not None) == matches


def test_strict_playlist_only_fetches_the_eligible_pick(resolver, monkeypatch):
    auto = load("auto_mode")
    schema = load("render.schema")
    slides = [schema.screen_from_dict(schema.SCREEN_SCHEMA({
        "kind": "picture", "entity": f"image.{name}",
    }), name) for name in ("queued", "recent", "fresh")]
    playlists = SimpleNamespace(get=lambda _: True, render_slides=lambda _: slides)
    data = io.BytesIO()
    Image.new("RGB", (1600, 1200)).save(data, format="PNG")
    fetch = AsyncMock(return_value=data.getvalue())
    monkeypatch.setattr(resolver, "async_get_source_bytes", fetch)
    history = auto.AutoHistory()
    history.record("slide:art:recent", NOW)
    slide = _resolve(
        resolver, {"kind": "playlist", "playlist_id": "art"},
        settings=auto.AutoSettings().updated({"orientation": "strict"}),
        history=history, exclude={"slide:art:queued"}, playlists=playlists,
    )
    assert slide.screen_id == "fresh"
    fetch.assert_awaited_once()
    assert fetch.await_args.kwargs["entity_id"] == "image.fresh"


@pytest.mark.parametrize("kind", ["dashboard", "entity"])
def test_playlist_fallback_identity_survives_queue_storage(resolver, kind):
    auto = load("auto_mode")
    schema = load("render.schema")
    queue_model = load("playback_queue")
    source = {"kind": "playlist", "playlist_id": "art"}
    data = {"kind": "picture", "entity": "image.art"} if kind == "entity" else {
        "layout": "full",
        "widgets": [{"type": "template", "slot": "main", "template": "Hello"}],
    }
    slides = [schema.screen_from_dict(schema.SCREEN_SCHEMA(data), name) for name in ("a", "b")]
    playlists = SimpleNamespace(get=lambda _: True, render_slides=lambda _: slides)
    first = _resolve(resolver, source, playlists=playlists)
    key = auto.picture_key(first)
    assert key == f"slide:art:{first.screen_id}"
    queue = queue_model.PlaybackQueue()
    queue.add_auto(first, "Art")
    queued = queue_model.PlaybackQueue.from_dict(queue.to_dict()).items[0].screen
    assert queued.screen_id != first.screen_id
    assert auto.picture_key(queued) == key
    assert auto.picture_key(_resolve(resolver, source, exclude={key}, playlists=playlists)) != key
    history = auto.AutoHistory()
    history.record(auto.picture_key(queued), NOW)
    assert auto.picture_key(_resolve(resolver, source, history=history, playlists=playlists)) != key
