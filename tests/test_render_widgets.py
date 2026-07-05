"""Tests for the PR-2 widget packs: weather, agenda, charts, image (pure)."""

from __future__ import annotations

import io
from datetime import datetime

import pytest
import voluptuous as vol
from conftest import load

const = load("const")
schema = load("render.schema")
compose = load("render.compose")
context = load("render.context")

NOW = datetime(2026, 7, 3, 14, 5)
W, H = 800, 480


def _screen(data: dict):
    return schema.screen_from_dict(schema.SCREEN_SCHEMA(data))


def _tiny_png(color=(200, 120, 40), size=(64, 48)) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def _render(widget: dict, data) -> bytes:
    screen = _screen({"layout": "full", "widgets": [{**widget, "slot": "main"}]})
    ctx = context.RenderContext(now=NOW)
    ctx.widget_data = {0: data}
    return compose.render_screen_png(screen, ctx, W, H)


def _png_size(png: bytes):
    from PIL import Image

    with Image.open(io.BytesIO(png)) as img:
        return img.size


FORECAST = {
    "items": [
        {"label": "Mon", "condition": "sunny", "temp": 21.3, "templow": 12.1},
        {"label": "Tue", "condition": "rainy", "temp": 17.0, "templow": 11.0},
        {"label": "Wed", "condition": "partlycloudy", "temp": 19.5, "templow": 13.2},
    ]
}


@pytest.mark.parametrize(
    "widget,data",
    [
        ({"type": "weather_current", "entity": "weather.home"},
         {"condition": "partlycloudy", "temperature": 18.5, "unit": "°C", "name": "Home"}),
        ({"type": "weather_forecast", "entity": "weather.home", "count": 3}, FORECAST),
        ({"type": "calendar", "entities": ["calendar.family"]},
         {"events": [
             {"day": "Today", "time": "09:00", "title": "Standup"},
             {"day": "Today", "time": "14:00", "title": "A very long meeting title that must truncate"},
             {"day": "Tomorrow", "time": "", "title": "Garbage pickup"},
         ]}),
        ({"type": "todo", "entity": "todo.shopping"},
         {"items": [
             {"summary": "Milk", "done": False},
             {"summary": "Bread", "done": True},
             {"summary": "Eggs", "done": False},
         ]}),
        ({"type": "chart", "entities": ["sensor.temp"], "style": "line"},
         {"series": [{"name": "Temp", "points": [(i / 20, 18 + (i % 7)) for i in range(21)]}],
          "start_label": "00:00", "end_label": "14:00"}),
        ({"type": "chart", "entities": ["sensor.a", "sensor.b"], "style": "area"},
         {"series": [
             {"name": "A", "points": [(i / 10, i) for i in range(11)]},
             {"name": "B", "points": [(i / 10, 10 - i) for i in range(11)]},
         ], "start_label": "Mon", "end_label": "Fri"}),
        ({"type": "chart", "entities": ["sensor.temp"], "style": "bar"},
         {"series": [{"name": "Temp", "points": [(i / 6, i + 1) for i in range(7)]}],
          "start_label": "00:00", "end_label": "12:00"}),
        ({"type": "gauge", "entity": "sensor.battery", "unit": "%"},
         {"value": 62.0, "display": "62", "name": "Battery", "unit": "%"}),
        ({"type": "gauge", "entity": "sensor.battery",
          "thresholds": [{"from": 0, "color": "red"}, {"from": 50, "color": "green"}]},
         {"value": 80.0, "display": "80", "name": "Battery", "unit": "%"}),
        ({"type": "progress", "entity": "sensor.washer"},
         {"value": 45.0, "display": "45", "name": "Washer", "unit": "%"}),
    ],
)
def test_widget_renders_palette_pure(widget, data) -> None:
    """Every vector widget renders at size and stays 100% palette-pure."""
    import numpy as np
    from PIL import Image

    png = _render(widget, data)
    assert _png_size(png) == (W, H)
    arr = np.asarray(Image.open(io.BytesIO(png)).convert("RGB")).reshape(-1, 3)
    palette = np.array(const.SPECTRA6_RGB, dtype=np.uint8)
    exact = np.zeros(arr.shape[0], dtype=bool)
    for color in palette:
        exact |= (arr == color).all(axis=1)
    assert exact.mean() == 1.0


@pytest.mark.parametrize(
    "widget",
    [
        {"type": "weather_forecast", "entity": "weather.home"},
        {"type": "calendar", "entities": ["calendar.family"]},
        {"type": "todo", "entity": "todo.shopping"},
        {"type": "chart", "entities": ["sensor.temp"]},
        {"type": "gauge", "entity": "sensor.battery"},
        {"type": "progress", "entity": "sensor.washer"},
        {"type": "image", "url": "http://example.com/a.png"},
    ],
)
def test_widget_error_payload_renders_placeholder(widget) -> None:
    png = _render(widget, {"error": "backend unavailable"})
    assert _png_size(png) == (W, H)


def test_image_widget_keeps_photo_pixels_and_switches_mode() -> None:
    """Embedded photo region survives the snap; mode flips to error diffusion."""
    import numpy as np
    from PIL import Image

    screen = _screen(
        {
            "layout": "half_vertical",
            "widgets": [
                {"type": "clock", "slot": "left"},
                {"type": "image", "slot": "right", "url": "http://example.com/p.png"},
            ],
        }
    )
    ctx = context.RenderContext(now=NOW)
    # An off-palette solid photo: must NOT be snapped to palette colours.
    ctx.widget_data = {1: {"bytes": _tiny_png(color=(200, 120, 40))}}
    png, mode = compose.render_screen(screen, ctx, W, H)
    assert mode == const.MODE_FLOYD_STEINBERG

    arr = np.asarray(Image.open(io.BytesIO(png)).convert("RGB"))
    # The photo fills the right slot; sample its centre.
    assert tuple(arr[H // 2, int(W * 0.75)]) == (200, 120, 40)
    # The left (vector) half is still palette-pure.
    left = arr[:, : W // 3].reshape(-1, 3)
    palette = np.array(const.SPECTRA6_RGB, dtype=np.uint8)
    exact = np.zeros(left.shape[0], dtype=bool)
    for color in palette:
        exact |= (left == color).all(axis=1)
    assert exact.mean() == 1.0


def test_screen_without_image_keeps_mode_none() -> None:
    screen = _screen({"layout": "full", "widgets": [{"type": "clock", "slot": "main"}]})
    ctx = context.RenderContext(now=NOW)
    _png, mode = compose.render_screen(screen, ctx, W, H)
    assert mode == const.MODE_NONE


def test_picture_screen_schema() -> None:
    result = schema.SCREEN_SCHEMA(
        {"kind": "picture", "url": "http://ha.local:10000/lovelace/0?viewport=1600x1200"}
    )
    screen = schema.screen_from_dict(result)
    assert screen.kind == "picture"
    assert screen.source["url"].startswith("http://ha.local")
    assert screen.widgets == ()


def test_picture_screen_rejects_widgets_and_needs_one_source() -> None:
    with pytest.raises(vol.Invalid, match="exactly one"):
        schema.SCREEN_SCHEMA({"kind": "picture"})
    with pytest.raises(vol.Invalid, match="exactly one"):
        schema.SCREEN_SCHEMA(
            {"kind": "picture", "url": "http://a.example/x.png", "entity": "camera.front"}
        )
    with pytest.raises(vol.Invalid, match="no layout/widgets"):
        schema.SCREEN_SCHEMA(
            {
                "kind": "picture",
                "url": "http://a.example/x.png",
                "layout": "full",
                "widgets": [{"type": "clock", "slot": "main"}],
            }
        )


def test_dashboard_kind_rejects_picture_source_fields() -> None:
    with pytest.raises(vol.Invalid, match="only valid on kind"):
        schema.SCREEN_SCHEMA(
            {
                "layout": "full",
                "url": "http://a.example/x.png",
                "widgets": [{"type": "clock", "slot": "main"}],
            }
        )


def test_image_widget_source_validation() -> None:
    # Both sources set is fine schema-wise per-widget? No — image widget takes
    # url OR entity; fetch uses whichever is set, url first. Schema allows
    # both keys individually; neither is required at schema level (fetch
    # errors surface as a placeholder). Reject non-http URLs though.
    with pytest.raises(vol.Invalid):
        schema.SCREEN_SCHEMA(
            {
                "layout": "full",
                "widgets": [
                    {"type": "image", "slot": "main", "url": "ftp://example.com/x.png"}
                ],
            }
        )
