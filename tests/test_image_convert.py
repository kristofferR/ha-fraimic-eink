"""Tests for the Fraimic Spectra 6 image-processing pipeline.

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
ALL_MODES = ["none", "bayer", "floyd_steinberg", "atkinson", "auto"]
# No pre-processing, so a solid colour stays exactly that colour.
RAW = {"saturation": 1.0, "contrast": 1.0, "sharpen": 0}


def _solid(width: int, height: int, color: tuple[int, int, int]) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, format="PNG")
    return buf.getvalue()


def _gradient(width: int, height: int) -> bytes:
    import numpy as np
    from PIL import Image

    base = np.indices((height, width)).sum(axis=0)
    rgb = np.dstack([base % 256, (base * 2) % 256, (base * 3) % 256]).astype("uint8")
    buf = io.BytesIO()
    Image.fromarray(rgb, "RGB").save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.parametrize("mode", ALL_MODES)
def test_output_is_exact_size(mode: str) -> None:
    w, h = LARGE
    data = ic.image_to_bin(_gradient(w, h), width=w, height=h, mode=mode, **RAW)
    assert len(data) == w * h // 2 == 960000


@pytest.mark.parametrize("mode", ALL_MODES)
def test_no_nibble_exceeds_five(mode: str) -> None:
    """Every nibble must be a valid Spectra index 0-5 (the cycled-palette gotcha)."""
    w, h = LARGE
    data = ic.image_to_bin(_gradient(w, h), width=w, height=h, mode=mode, **RAW)
    assert max({b >> 4 for b in data} | {b & 0x0F for b in data}) <= 5


def test_small_frame_size_scales() -> None:
    data = ic.image_to_bin(_solid(400, 300, (10, 10, 10)), width=800, height=480, **RAW)
    assert len(data) == 800 * 480 // 2


def test_odd_pixel_count_rejected() -> None:
    with pytest.raises(ValueError):
        ic.image_to_bin(_solid(100, 100, (0, 0, 0)), width=801, height=481, **RAW)


@pytest.mark.parametrize(
    "index,rgb",
    list(enumerate(const.SPECTRA6_RGB)),
)
def test_calibrated_colors_map_to_their_own_index(index, rgb) -> None:
    """A solid patch of a calibrated palette colour must quantise to that index."""
    w, h = LARGE
    data = ic.image_to_bin(_solid(w, h, tuple(rgb)), width=w, height=h, mode="none", **RAW)
    expected = (index << 4) | index
    assert set(data) == {expected}, f"{rgb} -> {hex(data[0])}, expected {hex(expected)}"


def test_auto_resolves_to_a_real_mode() -> None:
    assert const.DEFAULT_MODE_RESOLVED in (
        const.MODE_FLOYD_STEINBERG,
        const.MODE_ATKINSON,
    )


def test_preview_is_png_and_default_pipeline_runs() -> None:
    w, h = LARGE
    # Defaults (saturation/contrast/sharpen on) must not crash and must preview.
    _bin, preview, mode = ic.convert_image(_solid(800, 600, (200, 40, 40)), width=w, height=h)
    assert preview is not None and preview[:8] == b"\x89PNG\r\n\x1a\n"
    assert mode in (const.MODE_FLOYD_STEINBERG, const.MODE_ATKINSON, const.MODE_BAYER)


def _flat_graphic(width: int, height: int) -> bytes:
    """A few large blocks of solid colour — i.e. a 'graphic', not a photo."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, width // 2, height // 2], fill=(200, 30, 30))
    draw.rectangle([width // 2, 0, width, height // 2], fill=(30, 30, 200))
    draw.rectangle([0, height // 2, width // 2, height], fill=(30, 160, 30))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_auto_picks_bayer_for_flat_graphics() -> None:
    w, h = LARGE
    _bin, _preview, mode = ic.convert_image(_flat_graphic(w, h), width=w, height=h, mode="auto")
    assert mode == const.MODE_BAYER


def _continuous_tone(width: int, height: int) -> bytes:
    """Continuous-tone proxy: a full-range 2D gradient + fine noise, so it has
    spread-out colours and few exactly-equal neighbours (like a photo)."""
    import numpy as np
    from PIL import Image

    ys, xs = np.indices((height, width))
    rng = np.random.default_rng(1)
    noise = rng.integers(-4, 5, size=(height, width, 3))
    r = xs * 255 // (width - 1)
    g = ys * 255 // (height - 1)
    b = (xs + ys) * 255 // (width + height - 2)
    rgb = np.clip(np.dstack([r, g, b]) + noise, 0, 255).astype("uint8")
    buf = io.BytesIO()
    Image.fromarray(rgb, "RGB").save(buf, format="PNG")
    return buf.getvalue()


def test_auto_picks_error_diffusion_for_photos() -> None:
    w, h = LARGE
    _bin, _preview, mode = ic.convert_image(_continuous_tone(w, h), width=w, height=h, mode="auto")
    assert mode in (const.MODE_FLOYD_STEINBERG, const.MODE_ATKINSON)
