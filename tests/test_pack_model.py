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
    assert len(packs) >= 3
    # Every filename must be unique across the catalog so installs into the
    # library never collide on originals' names.
    filenames = [image["filename"] for pack in packs for image in pack["images"]]
    assert len(filenames) == len(set(filenames))


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
                    "images": [{"title": "t", "url": "http://insecure", "filename": "f"}],
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
