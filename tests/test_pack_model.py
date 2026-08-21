"""Tests for the pure art-pack logic + the bundled catalog (no HA import)."""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

PKG_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "fraimic"


def _load():
    if "fraimic" not in sys.modules:
        pkg = types.ModuleType("fraimic")
        pkg.__path__ = [str(PKG_DIR)]
        sys.modules["fraimic"] = pkg
    name = "fraimic.pack_model"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, PKG_DIR / "pack_model.py")
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


pm = _load()


def test_bundled_catalog_is_valid():
    data = json.loads((PKG_DIR / "packs" / "catalog.json").read_text(encoding="utf-8"))
    packs = pm.validate_catalog(data)
    assert len(packs) >= 4
    # Every filename must be unique across the catalog so installs into the
    # library never collide on originals' names.
    filenames = [image["filename"] for pack in packs for image in pack["images"]]
    assert len(filenames) == len(set(filenames))


def test_map_remote_catalog():
    data = {
        "packs": [
            {
                "id": "monet",
                "name": "Claude Monet",
                "description": "Impressionism.",
                "category": "famous_artists",
                "categories": ["famous_artists"],
                "license": "Public domain",
                "cover": "scene_packs/monet/01.jpg",
                "images": [
                    {
                        "filename": "01.jpg",
                        "path": "scene_packs/monet/01.jpg",
                        "title": "Impression, Sunrise",
                        "commons_url": "https://commons.wikimedia.org/wiki/File:x.jpg",
                        "license": "CC BY-SA 4.0",
                        "attribution": "Claude Monet, Wikimedia Commons",
                    }
                ],
            },
            # Widget packs are scripts for a different integration: skipped.
            {"id": "agenda", "name": "Agenda", "type": "widget", "images": []},
            # Malformed entries are skipped, not fatal.
            {"name": "no id"},
            {"id": "empty", "name": "Empty", "images": []},
        ]
    }
    packs = pm.map_remote_catalog(data, "https://raw.example/main/")
    assert len(packs) == 1
    pack = packs[0]
    assert pack["id"] == "fa-monet"
    assert pack["category"] == "Famous Artists"
    assert pack["cover_url"] == "https://raw.example/main/scene_packs/monet/01.jpg"
    image = pack["images"][0]
    assert image["url"] == "https://raw.example/main/scene_packs/monet/01.jpg"
    assert image["preview_url"] == image["url"]
    assert image["filename"] == "monet_01.jpg"
    assert image["source_url"].startswith("https://commons.wikimedia.org/")
    assert image["license"] == "CC BY-SA 4.0"
    assert image["attribution"] == "Claude Monet, Wikimedia Commons"
    assert "frame-addons" in pack["attribution"]


def test_map_remote_catalog_empty_or_garbage():
    assert pm.map_remote_catalog({}, "https://x") == []
    assert pm.map_remote_catalog([], "https://x") == []
    assert pm.map_remote_catalog({"packs": "bad"}, "https://x") == []
    assert pm.map_remote_catalog({"packs": ["nope", 4]}, "https://x") == []
    assert (
        pm.map_remote_catalog(
            {"packs": [{"id": "bad", "name": "Bad", "images": 1}]},
            "https://x",
        )
        == []
    )


def test_map_remote_catalog_ignores_malformed_categories():
    data = {
        "packs": [
            {
                "id": "weird",
                "name": "Weird",
                "categories": {"not": "a-list"},
                "images": [
                    {"filename": "01.jpg", "path": "scene_packs/weird/01.jpg"}
                ],
            }
        ]
    }

    packs = pm.map_remote_catalog(data, "https://raw.example/main")

    assert packs[0]["category"] == "Art"


def test_make_reframed_pack_is_lazy_and_bounded():
    pack = pm.make_reframed_pack(
        "collections/after-the-storm",
        "After the Storm",
        "Reframed Collections",
        cover_url="https://images.test/storm",
        source_count=82,
    )

    assert pack["id"] == "rg-collections-after-the-storm"
    assert pack["provider_path"] == "collections/after-the-storm"
    assert pack["images"] == []
    assert pack["image_count"] == pm.REFRAMED_PACK_LIMIT == 24
    assert "82 artworks" in pack["description"]


def test_make_reframed_pack_preserves_known_empty_count():
    pack = pm.make_reframed_pack(
        "collections/empty", "Empty", "Reframed Collections", source_count=0
    )

    assert pack["image_count"] == 0
    assert "0 artworks" in pack["description"]


def test_materialize_reframed_pack_maps_metadata_and_deduplicates():
    candidate = types.SimpleNamespace(
        item_id="albert-bierstadt/elk-in-oak-grove",
        image_url="https://files.test/elk/original",
        thumb_url="https://images.test/elk",
        title="Elk in Oak Grove",
        license=None,
        attribution="Elk in Oak Grove — Albert Bierstadt, Reframed Gallery",
        extra={
            "source_url": "https://www.reframed.gallery/albert-bierstadt/elk-in-oak-grove"
        },
    )
    pack = pm.make_reframed_pack(
        "collections/after-the-storm", "After the Storm", "Reframed Collections"
    )

    materialized = pm.materialize_reframed_pack(pack, [candidate, candidate])

    assert materialized["image_count"] == 1
    assert materialized["cover_url"] == "https://images.test/elk"
    assert len(materialized["images"]) == 1
    image = materialized["images"][0]
    assert image["title"] == "Elk in Oak Grove"
    assert image["url"] == "https://files.test/elk/original"
    assert image["preview_url"] == "https://images.test/elk"
    assert image["filename"] == "Albert Bierstadt - Elk in Oak Grove.jpg"
    assert image["source_url"].startswith("https://www.reframed.gallery/")


def test_materialize_reframed_pack_filters_insecure_urls_and_caps_images():
    invalid = types.SimpleNamespace(
        item_id="artist/insecure",
        image_url="http://files.test/insecure.jpg",
        thumb_url=None,
        title="Insecure",
        license=None,
        attribution=None,
        extra={},
    )
    candidates = [invalid]
    candidates.extend(
        types.SimpleNamespace(
            item_id=f"artist/work-{index}",
            image_url=f"https://files.test/work-{index}.jpg",
            thumb_url=None,
            title=f"Work {index}",
            license=None,
            attribution=None,
            extra={},
        )
        for index in range(pm.REFRAMED_PACK_LIMIT + 5)
    )
    pack = pm.make_reframed_pack(
        "collections/large", "Large", "Reframed Collections"
    )

    materialized = pm.materialize_reframed_pack(pack, candidates)

    assert materialized["image_count"] == pm.REFRAMED_PACK_LIMIT
    assert len(materialized["images"]) == pm.REFRAMED_PACK_LIMIT
    assert all(image["url"].startswith("https://") for image in materialized["images"])


def test_make_wallhaven_pack_is_lazy_and_bounded():
    pack = pm.make_wallhaven_pack(
        "top/1M",
        "This month",
        "Wallhaven Top",
    )

    assert pack["id"] == "wh-top-1m"
    assert pack["provider_key"] == "wallhaven"
    assert pack["provider_path"] == "top/1M"
    assert pack["images"] == []
    assert pack["image_count"] == pm.WALLHAVEN_PACK_LIMIT == 24
    assert pack["cover_url"] == pm.WALLHAVEN_FALLBACK_COVER


def test_materialize_wallhaven_pack_uses_readable_filename_and_metadata():
    candidate = types.SimpleNamespace(
        item_id="mlg7qm",
        image_url="https://w.wallhaven.cc/full/ml/wallhaven-mlg7qm.jpg",
        thumb_url="https://th.wallhaven.cc/lg/ml/mlg7qm.jpg",
        title="Mountains · Landscape · Clouds",
        artist="test-user",
        license=None,
        attribution="Mountains · Landscape · Clouds — test-user, Wallhaven",
        extra={"source_url": "https://wallhaven.cc/w/mlg7qm"},
    )
    pack = pm.make_wallhaven_pack("top/1M", "This month", "Wallhaven Top")

    materialized = pm.materialize_wallhaven_pack(pack, [candidate, candidate])

    assert materialized["image_count"] == 1
    assert materialized["cover_url"] == candidate.thumb_url
    assert materialized["images"] == [
        {
            "title": candidate.title,
            "url": candidate.image_url,
            "preview_url": candidate.thumb_url,
            "filename": "test-user - Mountains · Landscape · Clouds.jpg",
            "source_url": "https://wallhaven.cc/w/mlg7qm",
            "license": None,
            "attribution": candidate.attribution,
        }
    ]


@pytest.mark.parametrize(
    "broken",
    [
        {},
        {"packs": []},
        {"packs": [{"id": "x"}]},
        {"packs": [{"id": "x", "name": "X", "category": "Art", "attribution": "a", "images": []}]},
        {
            "packs": [
                {
                    "id": "x",
                    "name": "X",
                    "category": "Art",
                    "attribution": "a",
                    "images": [
                        {
                            "title": "t",
                            "url": "http://insecure",
                            "preview_url": "https://example.test/p.jpg",
                            "filename": "f",
                        }
                    ],
                }
            ]
        },
        {
            "packs": [
                {
                    "id": "x",
                    "name": "X",
                    "category": "Art",
                    "attribution": "a",
                    "images": [
                        {
                            "title": "t",
                            "url": "https://example.test/i.jpg",
                            "filename": "f",
                        }
                    ],
                }
            ]
        },
        {
            "packs": [
                {
                    "id": "x",
                    "name": "X",
                    "category": "Art",
                    "attribution": "a",
                    "images": [
                        {
                            "title": "t",
                            "url": "https://example.test/i.jpg",
                            "preview_url": "http://insecure",
                            "filename": "f",
                        }
                    ],
                }
            ]
        },
    ],
)
def test_validate_catalog_rejects_broken(broken):
    with pytest.raises(ValueError):
        pm.validate_catalog(broken)


def test_match_prefers_orientation_and_variety():
    frames = [("landscape_frame", 1600, 1200), ("portrait_frame", 1200, 1600)]
    images = [
        ("land1", 4000, 3000),
        ("port1", 3000, 4000),
        ("land2", 4000, 3000),
    ]
    result = pm.match_images_to_frames(frames, images)
    assert result["landscape_frame"] == "land1"
    assert result["portrait_frame"] == "port1"


def test_match_falls_back_when_no_orientation_match():
    frames = [("portrait_frame", 1200, 1600)]
    images = [("land1", 4000, 3000)]
    assert pm.match_images_to_frames(frames, images) == {"portrait_frame": "land1"}


def test_match_avoids_duplicates_until_exhausted():
    frames = [(f"f{i}", 1600, 1200) for i in range(3)]
    images = [("land1", 400, 300), ("land2", 400, 300)]
    result = pm.match_images_to_frames(frames, images)
    # Two frames get distinct images; the third reuses one.
    assert set(result.values()) == {"land1", "land2"}
    assert len(result) == 3


def test_match_unknown_dimensions_treated_as_flexible():
    frames = [("f", 1600, 1200)]
    images = [("mystery", None, None)]
    assert pm.match_images_to_frames(frames, images) == {"f": "mystery"}
