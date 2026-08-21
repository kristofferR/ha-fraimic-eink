"""Tests for the Fraimic Spectra 6 image-processing pipeline.

These exercise the pure conversion logic (no Home Assistant required), so they
can run standalone (deps cover the whole tests/ directory):

    uv run --with pillow --with numpy --with voluptuous --with resvg-py --with pytest pytest
"""

from __future__ import annotations

import hashlib
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
# Official uses the reference converter's intentionally slow sequential path;
# its exact behavior is covered by a small golden fixture below.
CORE_MODES = ["none", "bayer", "floyd_steinberg", "atkinson", "auto"]
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


@pytest.mark.parametrize("mode", CORE_MODES)
def test_output_is_exact_size(mode: str) -> None:
    w, h = LARGE
    data = ic.image_to_bin(_gradient(w, h), width=w, height=h, mode=mode, **RAW)
    assert len(data) == w * h // 2 == 960000


@pytest.mark.parametrize("mode", CORE_MODES)
def test_only_valid_panel_nibbles(mode: str) -> None:
    """Every nibble must be a valid E Ink Spectra 6 panel code.

    The panel codes are 0x0-0x3, 0x5, 0x6 — 0x4 is unused by the standard and
    anything above 0x6 would be garbage (the cycled-palette gotcha).
    """
    w, h = LARGE
    data = ic.image_to_bin(_gradient(w, h), width=w, height=h, mode=mode, **RAW)
    nibbles = {b >> 4 for b in data} | {b & 0x0F for b in data}
    assert nibbles <= {0x0, 0x1, 0x2, 0x3, 0x5, 0x6}, f"invalid nibbles: {nibbles}"


def test_small_frame_size_scales() -> None:
    data = ic.image_to_bin(_solid(400, 300, (10, 10, 10)), width=800, height=480, **RAW)
    assert len(data) == 800 * 480 // 2


def test_large_frame_uses_el315_padded_wire_layout() -> None:
    """The 31.5" panel has eight fixed-size IC blocks, not plain 4bpp."""
    import numpy as np

    width, height = 1440, 2560
    indices = np.zeros(width * height, dtype=np.uint8)
    data = ic._pack_nibbles(indices, width, height)

    assert len(data) == const.LARGE_FRAME_BIN_SIZE == 2_304_000
    blocks = np.frombuffer(data, dtype=np.uint8).reshape(8, 720, 400)
    assert np.all(blocks[[0, 1, 2, 4, 5, 6]] == 0x00)
    assert np.all(blocks[[3, 7], :, :80] == 0x00)
    assert np.all(blocks[[3, 7], :, 80:] == 0x11)


def test_large_frame_el315_corner_mapping() -> None:
    """Pin the official IC1/IC8 mapping for the bottom/top left corners."""
    import numpy as np

    width, height = 1440, 2560
    indices = np.ones((height, width), dtype=np.uint8)
    indices[height - 1, 0] = 3  # red bottom-left -> IC1 first high nibble
    indices[0, 0] = 4  # blue top-left -> IC8 first high nibble

    data = ic._pack_nibbles(indices.reshape(-1), width, height)

    assert data[0] == 0x31
    assert data[7 * 288_000 + 79] == 0x51


def test_official_mode_matches_fraimic_converter() -> None:
    """Match Fraimic/fraimic_bin_converter 1b794a3 end to end."""
    import numpy as np
    from PIL import Image

    source_width, source_height = 19, 13
    ys, xs = np.indices((source_height, source_width))
    rgb = np.dstack(
        (
            (xs * 31 + ys * 7) % 256,
            (xs * 11 + ys * 29) % 256,
            (xs * 17 + ys * 13) % 256,
        )
    ).astype(np.uint8)
    source = Image.fromarray(rgb, "RGB")
    prepared = ic._official_prepare_image(
        source, 32, 24, const.FIT_CONTAIN_BLACK, preprocess=True
    )
    indices = ic._official_atkinson_indices(prepared)

    assert hashlib.sha256(prepared.tobytes()).hexdigest() == (
        "9161abf6c29df1f7ec874b1b4606e659e57497105c3f8ee3c5b327fa369f335c"
    )
    assert hashlib.sha256(indices.tobytes()).hexdigest() == (
        "dd27e17d19f6f63a20f52dc1ceac4d9efedad3c6721ae708ce9b2c5bf3efd966"
    )

    raw = io.BytesIO()
    source.save(raw, format="PNG")
    packed, preview, mode = ic.convert_image(
        raw.getvalue(),
        width=32,
        height=24,
        fit=const.FIT_CONTAIN_BLACK,
        mode=const.MODE_OFFICIAL,
        saturation=0,
        contrast=0,
        sharpen=0,
        tone=0,
        preview=False,
    )

    assert packed == ic._pack_nibbles(indices, 32, 24)
    assert preview is None
    assert mode == const.MODE_OFFICIAL
    assert const.DITHER_MODES[0] == const.MODE_AUTO


def test_official_standard_mode_uses_published_portrait_geometry(monkeypatch) -> None:
    import numpy as np

    portrait = np.zeros((1600, 1200), dtype=np.uint8)
    portrait[0, 0] = 2
    portrait[0, -1] = 3
    portrait[-1, 0] = 4
    portrait[-1, -1] = 5
    prepared_size = None

    def prepare(image, width, height, fit, *, preprocess):
        nonlocal prepared_size
        prepared_size = (width, height)
        return image

    monkeypatch.setattr(ic, "_official_prepare_image", prepare)
    monkeypatch.setattr(
        ic, "_official_atkinson_indices", lambda image: portrait.reshape(-1)
    )

    indices = ic._official_frame_indices(
        object(), 1600, 1200, const.FIT_CONTAIN_BLACK, preprocess=True
    )

    assert prepared_size == (1200, 1600)
    assert np.array_equal(indices.reshape(1200, 1600), np.rot90(portrait, k=1))


@pytest.mark.parametrize(
    ("width", "height", "expected_sha256"),
    [
        (
            1600,
            1200,
            "180db78069be63ed5e9157265f89da7e1e986f2f6d25f7a4fa50364757dbac52",
        ),
        (
            1440,
            2560,
            "9af7cdd7cf6e17b5fa4c065e869967f7adf0f819c255d42c54c74b0e794de660",
        ),
    ],
)
def test_known_panel_wire_layout_golden(
    width: int, height: int, expected_sha256: str
) -> None:
    """Pin the complete official EL133UF1/EL315 coordinate mapping."""
    import numpy as np

    rows = np.arange(height, dtype=np.uint32)[:, None]
    cols = np.arange(width, dtype=np.uint32)[None, :]
    indices = ((rows * 3 + cols * 5 + rows // 37 + cols // 29) % 6).astype(
        np.uint8
    )

    packed = ic._pack_nibbles(indices.reshape(-1), width, height)

    # Generated independently with Fraimic/fraimic_bin_converter at 1b794a3.
    assert hashlib.sha256(packed).hexdigest() == expected_sha256


@pytest.mark.parametrize(
    ("reported", "native"),
    [
        ((1200, 1600), (1600, 1200)),
        ((2560, 1440), (1440, 2560)),
    ],
)
def test_known_frame_orientations_are_canonicalized(
    reported: tuple[int, int], native: tuple[int, int]
) -> None:
    assert const.canonical_frame_resolution(*reported) == native


@pytest.mark.parametrize("width,height", [(1200, 1600), (2560, 1440)])
def test_legacy_panel_orientation_cannot_use_generic_packer(
    width: int, height: int
) -> None:
    with pytest.raises(ValueError, match="verified render resolution"):
        ic._pack_nibbles([0], width, height)


def test_oversized_custom_buffer_is_rejected() -> None:
    with pytest.raises(ValueError, match="buffer exceeds"):
        ic._expected_bin_size(4096, 4096)


@pytest.mark.parametrize("width,height", [(0, 4), (4, 0), (-4, 4), (4, -4)])
def test_non_positive_buffer_dimensions_are_rejected(
    width: int, height: int
) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        ic._expected_bin_size(width, height)


def test_odd_pixel_count_rejected() -> None:
    with pytest.raises(ValueError):
        ic.image_to_bin(_solid(100, 100, (0, 0, 0)), width=801, height=481, **RAW)


def test_auto_mode_handles_1x1_source() -> None:
    w, h = 800, 480
    _bin, _preview, mode = ic.convert_image(_solid(1, 1, (120, 80, 40)), width=w, height=h, mode="auto")
    assert mode in (const.MODE_FLOYD_STEINBERG, const.MODE_ATKINSON, const.MODE_BAYER)


@pytest.mark.parametrize(
    "index,rgb",
    list(enumerate(const.SPECTRA6_RGB)),
)
def test_calibrated_colors_map_to_their_own_index(index, rgb) -> None:
    """A solid patch of a calibrated palette colour must quantise to that colour.

    The packed byte carries the E Ink *panel code* for the palette position
    (positions 4/5 map to nibbles 0x5/0x6 — 0x4 is unused by the standard).
    """
    w, h = LARGE
    data = ic.image_to_bin(_solid(w, h, tuple(rgb)), width=w, height=h, mode="none", **RAW)
    nibble = const.SPECTRA6_PANEL_INDEX[index]
    expected = (nibble << 4) | nibble
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
