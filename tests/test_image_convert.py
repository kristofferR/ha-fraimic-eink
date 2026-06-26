"""Tests for the Fraimic image -> Spectra 6 .bin conversion.

These exercise the pure conversion logic (no Home Assistant required), so they
can run standalone:

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
    """Load const + image_convert as the 'fraimic' package without importing HA."""
    if "fraimic" not in sys.modules:
        pkg = types.ModuleType("fraimic")
        pkg.__path__ = [str(PKG_DIR)]
        sys.modules["fraimic"] = pkg
    for name in ("const", "image_convert"):
        mod_name = f"fraimic.{name}"
        if mod_name not in sys.modules:
            spec = importlib.util.spec_from_file_location(mod_name, PKG_DIR / f"{name}.py")
            assert spec and spec.loader
            module = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = module
            spec.loader.exec_module(module)
    return sys.modules["fraimic.const"], sys.modules["fraimic.image_convert"]


const, ic = _load()

LARGE = (1600, 1200)


def _solid_rgb(width: int, height: int, color: tuple[int, int, int]) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.parametrize("fit", ["cover", "contain", "stretch"])
@pytest.mark.parametrize("rotate", [0, 90, 180, 270])
def test_output_is_exact_size(fit: str, rotate: int) -> None:
    w, h = LARGE
    data = ic.image_to_bin(_solid_rgb(800, 600, (10, 200, 30)), width=w, height=h, fit=fit, rotate=rotate)
    assert len(data) == w * h // 2 == 960000


def test_small_frame_size_scales() -> None:
    data = ic.image_to_bin(_solid_rgb(400, 300, (0, 0, 0)), width=800, height=480)
    assert len(data) == 800 * 480 // 2


@pytest.mark.parametrize(
    "color,nibble",
    [
        ((0, 0, 0), 0x0),       # black
        ((255, 255, 255), 0x1), # white
        ((0, 255, 0), 0x2),     # green
        ((0, 0, 255), 0x3),     # blue
        ((255, 0, 0), 0x4),     # red
        ((255, 255, 0), 0x5),   # yellow
    ],
)
def test_pure_colors_map_to_correct_palette_index(color, nibble) -> None:
    w, h = LARGE
    data = ic.image_to_bin(_solid_rgb(w, h, color), width=w, height=h, dither=False)
    expected = (nibble << 4) | nibble
    assert set(data) == {expected}, f"{color} -> {hex(data[0])}, expected {hex(expected)}"


def test_all_nibbles_are_valid_palette_indices() -> None:
    """Even on a noisy/dithered image, no nibble may exceed 5 (the gotcha)."""
    from PIL import Image
    import numpy as np

    w, h = LARGE
    # Deterministic gradient noise (computed in int, then cast to uint8).
    base = np.indices((h, w)).sum(axis=0)
    rgb = np.dstack([base % 256, (base * 2) % 256, (base * 3) % 256]).astype("uint8")
    buf = io.BytesIO()
    Image.fromarray(rgb, "RGB").save(buf, format="PNG")
    data = ic.image_to_bin(buf.getvalue(), width=w, height=h, dither=True)
    hi = {b >> 4 for b in data}
    lo = {b & 0x0F for b in data}
    assert max(hi | lo) <= 5


def test_preview_is_png() -> None:
    w, h = LARGE
    _bin, preview = ic.convert_image(_solid_rgb(800, 600, (200, 0, 0)), width=w, height=h)
    assert preview is not None
    assert preview[:8] == b"\x89PNG\r\n\x1a\n"
