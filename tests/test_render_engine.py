"""Tests for the SVG compose/rasterise engine (pure, no Home Assistant).

Run:  uv run --with pillow --with numpy --with voluptuous --with resvg-py --with pytest pytest
"""

from __future__ import annotations

import io
from datetime import datetime

from conftest import load

const = load("const")
schema = load("render.schema")
compose = load("render.compose")
context = load("render.context")
icons = load("render.icons")
ic = load("image_convert")

NOW = datetime(2026, 7, 3, 14, 5)
W, H = 800, 480  # small panel size keeps the suite fast; height % 4 == 0


def _screen(data: dict[str, object]) -> object:
    return schema.screen_from_dict(schema.SCREEN_SCHEMA(data))


def _quadrant_screen() -> tuple[object, object]:
    screen = _screen(
        {
            "name": "Test screen",
            "layout": "quadrant",
            "widgets": [
                {"type": "clock", "slot": "top_left"},
                {
                    "type": "stat",
                    "slot": "top_right",
                    "entity": "sensor.outdoor_temperature",
                    "color": "red",
                },
                {
                    "type": "entities",
                    "slot": "bottom_left",
                    "entities": ["sensor.indoor_temperature", "light.kitchen"],
                },
                {
                    "type": "template",
                    "slot": "bottom_right",
                    "template": "unused-in-test",
                },
            ],
        }
    )
    ctx = context.RenderContext(now=NOW)
    ctx.widget_data = {
        1: {
            "value": "21.4",
            "name": "Outdoor temperature",
            "unit": "°C",
            "icon": "mdi:thermometer",
            "trend_delta": 1.2,
        },
        2: {
            "rows": [
                {"name": "Indoor temperature", "value": "22.1 °C", "icon": "mdi:thermometer"},
                {"name": "Kitchen", "value": "On", "icon": "mdi:lightbulb"},
            ]
        },
        3: {"text": "Energy today: 12.4 kWh. All quiet in the house."},
    }
    return screen, ctx


def _png_size(png: bytes) -> tuple[int, int]:
    from PIL import Image

    with Image.open(io.BytesIO(png)) as img:
        return img.size


def test_renders_expected_dimensions() -> None:
    screen, ctx = _quadrant_screen()
    png = compose.render_screen_png(screen, ctx, W, H)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert _png_size(png) == (W, H)


def test_render_is_deterministic() -> None:
    screen, ctx = _quadrant_screen()
    first = compose.render_screen_png(screen, ctx, W, H)
    second = compose.render_screen_png(screen, ctx, W, H)
    assert first == second, "identical context must render byte-identically"


def test_palette_purity_and_bin_roundtrip() -> None:
    """Every pixel is an exact palette colour; the .bin conversion is stable.

    100% purity is guaranteed by construction: antialiased edges are snapped
    back to the screen's used colours after rasterising (without that, grey
    glyph edges quantise to the panel's muted green — seen on hardware).
    """
    import numpy as np
    from PIL import Image

    screen, ctx = _quadrant_screen()
    png = compose.render_screen_png(screen, ctx, W, H)

    arr = np.asarray(Image.open(io.BytesIO(png)).convert("RGB")).reshape(-1, 3)
    palette = np.array(const.SPECTRA6_RGB, dtype=np.uint8)
    exact = np.zeros(arr.shape[0], dtype=bool)
    for color in palette:
        exact |= (arr == color).all(axis=1)
    purity = float(exact.mean())
    assert purity == 1.0, f"only {purity:.2%} of pixels are exact palette colours"

    # The full path a screen takes to the frame: quantise with mode "none" and
    # NO preprocessing. Deterministic + valid nibbles + exact size.
    bin1 = ic.image_to_bin(
        png,
        width=W,
        height=H,
        mode="none",
        saturation=1.0,
        contrast=1.0,
        sharpen=0,
        tone=0,
        preprocess=False,
    )
    bin2 = ic.image_to_bin(
        png,
        width=W,
        height=H,
        mode="none",
        saturation=1.0,
        contrast=1.0,
        sharpen=0,
        tone=0,
        preprocess=False,
    )
    assert bin1 == bin2
    assert len(bin1) == W * H // 2
    nibbles = {b >> 4 for b in bin1} | {b & 0x0F for b in bin1}
    assert nibbles <= {0x0, 0x1, 0x2, 0x3, 0x5, 0x6}


def test_preprocess_false_keeps_palette_colors_exact() -> None:
    """A solid calibrated-palette PNG survives preprocess=False untouched."""
    from PIL import Image

    for index, rgb in enumerate(const.SPECTRA6_RGB):
        buf = io.BytesIO()
        Image.new("RGB", (W, H), tuple(rgb)).save(buf, format="PNG")
        data = ic.image_to_bin(
            buf.getvalue(),
            width=W,
            height=H,
            mode="none",
            saturation=1.0,
            contrast=1.0,
            sharpen=0,
            tone=0,
            preprocess=False,
        )
        nibble = const.SPECTRA6_PANEL_INDEX[index]
        assert set(data) == {(nibble << 4) | nibble}


def test_fetch_error_renders_placeholder_not_exception() -> None:
    screen = _screen(
        {
            "layout": "full",
            "widgets": [
                {"type": "stat", "slot": "main", "entity": "sensor.gone"},
            ],
        }
    )
    ctx = context.RenderContext(now=NOW)
    ctx.widget_data = {0: {"error": "Entity sensor.gone not found"}}
    png = compose.render_screen_png(screen, ctx, W, H)
    assert _png_size(png) == (W, H)


def test_missing_widget_data_renders_gracefully() -> None:
    """No fetched data at all (None payloads) must still produce a screen."""
    screen, _ = _quadrant_screen()
    ctx = context.RenderContext(now=NOW)  # widget_data left empty
    png = compose.render_screen_png(screen, ctx, W, H)
    assert _png_size(png) == (W, H)


def test_black_background_flips_ink() -> None:
    screen = _screen(
        {
            "layout": "full",
            "background": "black",
            "widgets": [{"type": "clock", "slot": "main"}],
        }
    )
    ctx = context.RenderContext(now=NOW)
    import numpy as np
    from PIL import Image

    png = compose.render_screen_png(screen, ctx, W, H)
    arr = np.asarray(Image.open(io.BytesIO(png)).convert("RGB")).reshape(-1, 3)
    black = (arr == (0, 0, 0)).all(axis=1).mean()
    white = (arr == (255, 255, 255)).all(axis=1).mean()
    assert black > 0.5  # background
    assert white > 0.01  # the clock digits


def test_unknown_icon_falls_back_to_placeholder() -> None:
    assert icons.icon_path("mdi:this-icon-does-not-exist-xyz") is None
    assert icons.icon_path(None) is None
    # A real icon resolves to path data.
    assert icons.icon_path("mdi:thermometer")


def test_long_template_text_is_clipped_not_crashed() -> None:
    screen = _screen(
        {
            "layout": "quadrant",
            "widgets": [{"type": "template", "slot": "top_left", "template": "x"}],
        }
    )
    ctx = context.RenderContext(now=NOW)
    ctx.widget_data = {0: {"text": "word " * 400}}
    png = compose.render_screen_png(screen, ctx, W, H)
    assert _png_size(png) == (W, H)
