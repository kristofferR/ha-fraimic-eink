"""Tests for the pure library data model + the pipeline's crop support.

Standalone like test_image_convert (no Home Assistant import):

    uv run --with pillow --with numpy --with pytest pytest
"""

from __future__ import annotations

import importlib.util
import io
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
    for name in ("const", "image_convert", "library_model"):
        mod_name = f"fraimic.{name}"
        if mod_name not in sys.modules:
            spec = importlib.util.spec_from_file_location(mod_name, PKG_DIR / f"{name}.py")
            assert spec and spec.loader
            module = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = module
            spec.loader.exec_module(module)
    return (
        sys.modules["fraimic.const"],
        sys.modules["fraimic.image_convert"],
        sys.modules["fraimic.library_model"],
    )


const, ic, lm = _load()


# --------------------------------------------------------------------- model


def test_safe_filename():
    assert lm.safe_filename("hello.jpg") == "hello.jpg"
    assert lm.safe_filename("my photo (1).png") == "my_photo_1_.png"
    # No path separators may survive (the id prefix already prevents collisions).
    assert "/" not in lm.safe_filename("../../etc/passwd")
    assert "\\" not in lm.safe_filename("..\\..\\etc\\passwd")
    assert lm.safe_filename("") == "image"
    assert len(lm.safe_filename("x" * 300 + ".jpg")) <= 80


def test_normalize_crop_valid():
    assert lm.normalize_crop([0, 0, 1, 1]) == (0.0, 0.0, 1.0, 1.0)
    assert lm.normalize_crop((0.1, 0.2, 0.9, 0.8)) == (0.1, 0.2, 0.9, 0.8)


@pytest.mark.parametrize(
    "box",
    [
        None,
        [0.5, 0.5],
        ["a", 0, 1, 1],
        [-0.1, 0, 1, 1],
        [0, 0, 1.2, 1],
        [0.5, 0, 0.5, 1],  # zero width
        [0.9, 0, 0.1, 1],  # inverted
    ],
)
def test_normalize_crop_invalid(box):
    with pytest.raises(ValueError):
        lm.normalize_crop(box)


def test_render_cache_key_stable_and_sensitive():
    params = {
        "width": 1600,
        "height": 1200,
        "fit": "cover",
        "rotate": 0,
        "preview_rotate": 0,
        "mode": "auto",
        "saturation": 1.15,
        "contrast": 1.4,
        "sharpen": 80.0,
        "tone": 25.0,
        "crop": None,
    }
    key = lm.render_cache_key(params)
    assert key == lm.render_cache_key(dict(params))
    assert key.startswith("1600x1200_")
    changed = dict(params, contrast=1.5)
    assert lm.render_cache_key(changed) != key
    cropped = dict(params, crop=[0.1, 0.1, 0.9, 0.9])
    assert lm.render_cache_key(cropped) != key


def test_library_image_roundtrip_and_album_fallback():
    image = lm.LibraryImage(
        image_id="abc123def456",
        filename="a.jpg",
        content_type="image/jpeg",
        uploaded_at=123.0,
        albums=["  ", "Art", "Art", ""],
        crops={"1600x1200": [0.1, 0.1, 0.9, 0.9]},
    )
    assert image.normalized_albums() == ["Art"]
    restored = lm.LibraryImage.from_dict(image.to_dict())
    assert restored.image_id == "abc123def456"
    assert restored.crop_for(1600, 1200) == (0.1, 0.1, 0.9, 0.9)
    assert restored.crop_for(2560, 1440) is None

    # An image with no albums at all falls back to the default album.
    bare = lm.LibraryImage("id", "f", "image/png", 0.0, albums=[])
    assert bare.normalized_albums() == [const.LIBRARY_ALBUM_DEFAULT]


def test_bad_saved_crop_is_ignored_not_fatal():
    image = lm.LibraryImage(
        "id", "f", "image/png", 0.0, crops={"1600x1200": [0.9, 0.9, 0.1, 0.1]}
    )
    assert image.crop_for(1600, 1200) is None


def test_manifest_roundtrip_skips_broken_entries():
    images = {
        "good": lm.LibraryImage("good", "a.jpg", "image/jpeg", 1.0),
    }
    data = lm.manifest_to_dict(images)
    data["images"]["broken"] = {"uploaded_at": "not-a-number"}
    restored = lm.manifest_from_dict(data)
    assert set(restored) == {"good"}
    assert restored["good"].filename == "a.jpg"


@pytest.mark.parametrize(
    "data",
    [
        None,
        [],
        {"images": []},
        {"images": None},
    ],
)
def test_manifest_from_dict_ignores_non_object_shapes(data):
    assert lm.manifest_from_dict(data) == {}


def test_all_albums_default_first():
    images = {
        "a": lm.LibraryImage("a", "a", "image/png", 0.0, albums=["Zebra"]),
        "b": lm.LibraryImage("b", "b", "image/png", 0.0, albums=["art"]),
    }
    albums = lm.all_albums(images)
    assert albums[0] == const.LIBRARY_ALBUM_DEFAULT
    assert albums == [const.LIBRARY_ALBUM_DEFAULT, "art", "Zebra"]


# ---------------------------------------------------------------------- crop


def _two_tone(width: int, height: int) -> bytes:
    """Left half pure black, right half pure white."""
    from PIL import Image

    img = Image.new("RGB", (width, height), (0, 0, 0))
    img.paste((255, 255, 255), (width // 2, 0, width, height))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


RAW = {"saturation": 1.0, "contrast": 1.0, "sharpen": 0, "tone": 0}


def test_convert_image_crop_selects_region():
    raw = _two_tone(400, 200)
    # Crop the right (white) half only: every rendered pixel must be white.
    bin_data, _, _ = ic.convert_image(
        raw, width=160, height=120, mode="none", crop=(0.5, 0.0, 1.0, 1.0), **RAW
    )
    # White is palette position 1 -> panel nibble 0x1 in both halves of a byte.
    assert set(bin_data) == {0x11}

    # Same conversion without the crop still contains black pixels.
    bin_full, _, _ = ic.convert_image(raw, width=160, height=120, mode="none", **RAW)
    assert set(bin_full) != {0x11}


def test_convert_image_degenerate_crop_raises():
    raw = _two_tone(400, 200)
    with pytest.raises(ValueError):
        ic.convert_image(
            raw, width=160, height=120, mode="none", crop=(0.5, 0.5, 0.5, 0.5), **RAW
        )
