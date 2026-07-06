"""Tests for the pure scene data model (no Home Assistant import)."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "fraimic"


def _load():
    if "fraimic" not in sys.modules:
        pkg = types.ModuleType("fraimic")
        pkg.__path__ = [str(PKG_DIR)]
        sys.modules["fraimic"] = pkg
    name = "fraimic.scene_model"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, PKG_DIR / "scene_model.py")
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


sm = _load()


def test_scene_roundtrip():
    scene = sm.Scene(
        scene_id="abc123",
        name="Morning wall",
        mappings={"entry_1": "img_1", "entry_2": "img_2"},
        created_at=123.0,
    )
    restored = sm.Scene.from_dict(scene.to_dict())
    assert restored == scene
    assert restored.source == sm.SCENE_SOURCE_USER


def test_scene_from_dict_drops_empty_mappings():
    scene = sm.Scene.from_dict(
        {"scene_id": "x", "name": "S", "mappings": {"entry_1": "", "entry_2": "img"}}
    )
    assert scene.mappings == {"entry_2": "img"}


def test_scenes_dict_roundtrip_skips_broken():
    scenes = {"good": sm.Scene(scene_id="good", name="G", mappings={"e": "i"})}
    data = sm.scenes_to_dict(scenes)
    data["scenes"]["broken"] = {"created_at": "nan-such"}
    restored = sm.scenes_from_dict(data)
    assert set(restored) == {"good"}
    assert restored["good"].name == "G"
