"""Weather widgets: current conditions and forecast strip."""

from __future__ import annotations

from typing import Any

from ..context import RenderContext
from ..icons import icon_path
from ..layout import Rect
from ..svg import SvgDoc, measure, truncate
from ..theme import Theme
from .base import fetch_error, render_error
from .core import _BASELINE, _widget_label

# HA weather-entity condition -> MDI icon.
CONDITION_ICONS = {
    "clear-night": "mdi:weather-night",
    "cloudy": "mdi:weather-cloudy",
    "exceptional": "mdi:weather-cloudy-alert",
    "fog": "mdi:weather-fog",
    "hail": "mdi:weather-hail",
    "lightning": "mdi:weather-lightning",
    "lightning-rainy": "mdi:weather-lightning-rainy",
    "partlycloudy": "mdi:weather-partly-cloudy",
    "pouring": "mdi:weather-pouring",
    "rainy": "mdi:weather-rainy",
    "snowy": "mdi:weather-snowy",
    "snowy-rainy": "mdi:weather-snowy-rainy",
    "sunny": "mdi:weather-sunny",
    "windy": "mdi:weather-windy",
    "windy-variant": "mdi:weather-windy-variant",
}


def _condition_icon(condition: str | None) -> str | None:
    if condition is None:
        return None
    return icon_path(CONDITION_ICONS.get(condition, "mdi:weather-partly-cloudy"))


def render_weather_current(
    doc: SvgDoc, rect: Rect, options: dict, data: Any, ctx: RenderContext, theme: Theme
) -> None:
    if (err := fetch_error(data)) is not None:
        render_error(doc, rect, err, theme)
        return

    _widget_label(doc, rect, options.get("name") or data.get("name") or "Weather", theme)

    icon_size = min(round(rect.h * 0.5), round(theme.value * 1.6))
    icon_y = rect.cy - icon_size // 2
    doc.icon(_condition_icon(data.get("condition")), rect.x, icon_y, icon_size, theme.ink)

    temp = data.get("temperature")
    value = "—" if temp is None else f"{temp:g}"
    unit = data.get("unit") or "°"
    x = rect.x + icon_size + round(theme.body * 0.8)
    size = min(round(theme.value * 1.2), round(rect.h * 0.4))
    while size > theme.body and (
        measure(value, size, 700) + measure(unit, round(size * 0.38), 500) > rect.right - x
    ):
        size = max(theme.body, int(size * 0.92))
    baseline = rect.cy + round(size * _BASELINE * 0.6)
    doc.text(x, baseline, value, size=size, fill=theme.ink, weight=700)
    doc.text(
        x + round(measure(value, size, 700)) + max(4, size // 12),
        baseline,
        unit,
        size=max(theme.small, round(size * 0.38)),
        fill=theme.ink,
        weight=500,
    )
    condition = str(data.get("condition") or "").replace("-", " ").capitalize()
    if condition:
        doc.text(
            x,
            baseline + round(theme.body * 1.5),
            truncate(condition, rect.right - x, theme.body),
            size=theme.body,
            fill=theme.ink,
        )


def render_weather_forecast(
    doc: SvgDoc, rect: Rect, options: dict, data: Any, ctx: RenderContext, theme: Theme
) -> None:
    if (err := fetch_error(data)) is not None:
        render_error(doc, rect, err, theme)
        return

    items = data.get("items", [])
    if not items:
        render_error(doc, rect, "No forecast data", theme)
        return

    col_w = rect.w // len(items)
    icon_size = min(round(col_w * 0.55), round(rect.h * 0.3), theme.icon * 2)
    label_size = theme.small
    temp_size = min(theme.title, round(col_w * 0.32))

    # Vertical rhythm: label / icon / temp (+ low) centred as a block.
    gap = round(theme.small * 0.7)
    block_h = label_size + gap + icon_size + gap + temp_size
    has_low = any(item.get("templow") is not None for item in items)
    if has_low:
        block_h += round(theme.small * 1.3)
    top = max(rect.y, rect.cy - block_h // 2)

    for index, item in enumerate(items):
        cx = rect.x + col_w * index + col_w // 2
        y = top
        doc.text(
            cx,
            y + label_size,
            str(item.get("label", "")),
            size=label_size,
            fill=theme.ink,
            weight=600,
            anchor="middle",
        )
        y += label_size + gap
        doc.icon(
            _condition_icon(item.get("condition")),
            cx - icon_size // 2,
            y,
            icon_size,
            theme.ink,
        )
        y += icon_size + gap
        temp = item.get("temp")
        doc.text(
            cx,
            y + temp_size,
            "—" if temp is None else f"{round(temp)}°",
            size=temp_size,
            fill=theme.ink,
            weight=700,
            anchor="middle",
        )
        if has_low and (low := item.get("templow")) is not None:
            doc.text(
                cx,
                y + temp_size + round(theme.small * 1.3),
                f"{round(low)}°",
                size=theme.small,
                fill=theme.ink,
                anchor="middle",
            )
