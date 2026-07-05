"""Chart widgets: history line/area/bar chart, arc gauge, progress bar."""

from __future__ import annotations

import math
from typing import Any

from ..context import RenderContext
from ..layout import Rect
from ..svg import SvgDoc, measure, truncate
from ..theme import Theme, PALETTE_HEX
from .base import fetch_error, render_error
from .core import _BASELINE, _widget_label


def _series_colors(theme: Theme) -> list[str]:
    """Ink first; extra series get the panel's strongest chromatic colours."""
    return [theme.ink, PALETTE_HEX["red"], PALETTE_HEX["blue"]]


def render_chart(
    doc: SvgDoc, rect: Rect, options: dict, data: Any, ctx: RenderContext, theme: Theme
) -> None:
    if (err := fetch_error(data)) is not None:
        render_error(doc, rect, err, theme)
        return

    series = [s for s in data.get("series", []) if s.get("points")]
    if not series:
        render_error(doc, rect, "No history data", theme)
        return

    label_h = _widget_label(
        doc, rect, options.get("name") or series[0].get("name") or "History", theme
    )

    values = [v for s in series for _, v in s["points"]]
    lo = options.get("min", min(values))
    hi = options.get("max", max(values))
    if hi <= lo:
        hi = lo + 1.0

    axis_h = round(theme.small * 1.6)
    plot = Rect(rect.x, rect.y + label_h, rect.w, rect.h - label_h - axis_h)
    if plot.h < theme.body:
        render_error(doc, rect, "Too little room for a chart", theme)
        return

    def to_xy(frac: float, value: float) -> tuple[float, float]:
        x = plot.x + frac * plot.w
        y = plot.bottom - (min(max(value, lo), hi) - lo) / (hi - lo) * plot.h
        return x, y

    hairline = max(1, round(theme.scale))
    # Dotted top/mid guides + solid baseline; dashes stay pure ink after the
    # palette snap (no greys exist on this panel).
    for frac in (0.0, 0.5):
        y = round(plot.y + frac * plot.h)
        doc.path(
            f"M{plot.x} {y}H{plot.right}",
            "none",
            stroke=theme.ink,
            stroke_width=hairline,
            dash=f"{hairline} {hairline * 5}",
        )
    doc.line(plot.x, plot.bottom, plot.right, plot.bottom, theme.ink, hairline)

    colors = _series_colors(theme)
    stroke_w = max(3, round(3 * theme.scale))
    for index, entry in enumerate(series):
        color = colors[index % len(colors)]
        points = [to_xy(frac, value) for frac, value in entry["points"]]
        style = options.get("style", "line")
        if style == "bar" and points:
            bar_w = max(2, int(plot.w / max(len(points), 1) * 0.7))
            for x, y in points:
                doc.rect(
                    int(x - bar_w / 2), int(y), bar_w, max(1, plot.bottom - int(y)), color
                )
        elif style == "area" and len(points) >= 2:
            d = f"M{points[0][0]:.1f} {plot.bottom}" + "".join(
                f"L{x:.1f} {y:.1f}" for x, y in points
            ) + f"L{points[-1][0]:.1f} {plot.bottom}Z"
            doc.path(d, color)
        elif len(points) >= 2:
            doc.polyline(points, color, stroke_w)
        elif points:
            x, y = points[0]
            doc.circle(int(x), int(y), stroke_w, fill=color)

    # Scale labels top-left / bottom-left inside the plot; time range along
    # the bottom axis.
    def fmt(value: float) -> str:
        rounded = round(value, 1) if hi - lo < 100 else round(value)
        return f"{rounded:g}"

    doc.text(
        plot.x, plot.y + theme.small, fmt(hi),
        size=theme.small, fill=theme.ink, weight=600,
    )
    doc.text(
        plot.x, plot.bottom - round(theme.small * 0.4), fmt(lo),
        size=theme.small, fill=theme.ink, weight=600,
    )
    baseline = rect.bottom - round(theme.small * 0.3)
    doc.text(rect.x, baseline, str(data.get("start_label", "")), size=theme.small, fill=theme.ink)
    doc.text(
        rect.right, baseline, str(data.get("end_label", "")),
        size=theme.small, fill=theme.ink, anchor="end",
    )

    # Legend only when there is more than one series.
    if len(series) > 1:
        x = rect.x
        square = round(theme.small * 0.7)
        for index, entry in enumerate(series):
            color = colors[index % len(colors)]
            doc.rect(x, rect.y + label_h - square - 2, square, square, color)
            name = truncate(str(entry.get("name", "")), rect.w / len(series) - square * 3, theme.small)
            doc.text(
                x + square + round(square * 0.6),
                rect.y + label_h - 2,
                name,
                size=theme.small,
                fill=theme.ink,
            )
            x += square + round(square * 0.6) + round(measure(name, theme.small)) + theme.small


def _polar(cx: float, cy: float, r: float, angle_deg: float) -> tuple[float, float]:
    rad = math.radians(angle_deg)
    return cx + r * math.cos(rad), cy + r * math.sin(rad)


def _arc_path(cx: float, cy: float, r: float, a0: float, a1: float) -> str:
    """SVG arc from angle a0 to a1 (degrees, clockwise, 0 = 3 o'clock)."""
    x0, y0 = _polar(cx, cy, r, a0)
    x1, y1 = _polar(cx, cy, r, a1)
    large = 1 if (a1 - a0) % 360 > 180 else 0
    return f"M{x0:.1f} {y0:.1f}A{r:.1f} {r:.1f} 0 {large} 1 {x1:.1f} {y1:.1f}"


def _gauge_color(options: dict, value: float, theme: Theme) -> str:
    color = theme.color(options.get("color"), theme.accent)
    for threshold in options.get("thresholds") or []:
        if value >= threshold["from"]:
            color = PALETTE_HEX[threshold["color"]]
    return color


def render_gauge(
    doc: SvgDoc, rect: Rect, options: dict, data: Any, ctx: RenderContext, theme: Theme
) -> None:
    if (err := fetch_error(data)) is not None:
        render_error(doc, rect, err, theme)
        return

    label_h = _widget_label(
        doc, rect, options.get("name") or data.get("name") or options.get("entity", ""), theme
    )

    lo, hi = options.get("min", 0.0), options.get("max", 100.0)
    if hi <= lo:
        hi = lo + 1.0
    value = data.get("value")

    # 270° arc opening downwards (135° -> 405°).
    inner = Rect(rect.x, rect.y + label_h, rect.w, rect.h - label_h)
    r = max(10, min(inner.w // 2 - theme.rule * 2, round(inner.h * 0.52)))
    cx, cy = inner.cx, inner.y + round(inner.h * 0.58)
    track_w = max(3, round(theme.scale * 4))
    arc_w = max(track_w * 3, round(r * 0.2))

    doc.path(
        _arc_path(cx, cy, r, 135, 405), "none",
        stroke=theme.ink, stroke_width=track_w, linecap="round",
    )
    if isinstance(value, (int, float)):
        frac = min(max((value - lo) / (hi - lo), 0.0), 1.0)
        if frac > 0:
            doc.path(
                _arc_path(cx, cy, r, 135, 135 + 270 * frac), "none",
                stroke=_gauge_color(options, value, theme),
                stroke_width=arc_w, linecap="round",
            )

    display = str(data.get("display", "—"))
    size = theme.value
    while size > theme.body and measure(display, size, 700) > r * 1.35:
        size = max(theme.body, int(size * 0.9))
    doc.text(
        cx, cy + round(size * _BASELINE), display,
        size=size, fill=theme.ink, weight=700, anchor="middle",
    )
    if unit := (options.get("unit") or data.get("unit")):
        doc.text(
            cx, cy + round(size * _BASELINE) + round(theme.small * 1.5), str(unit),
            size=theme.small, fill=theme.ink, weight=500, anchor="middle",
        )


def render_progress(
    doc: SvgDoc, rect: Rect, options: dict, data: Any, ctx: RenderContext, theme: Theme
) -> None:
    if (err := fetch_error(data)) is not None:
        render_error(doc, rect, err, theme)
        return

    lo, hi = options.get("min", 0.0), options.get("max", 100.0)
    if hi <= lo:
        hi = lo + 1.0
    value = data.get("value")
    name = options.get("name") or data.get("name") or options.get("entity", "")

    bar_h = max(8, round(theme.body * 0.7))
    stroke = max(2, theme.rule)
    row_h = round(theme.body * 1.6) + bar_h
    top = rect.cy - row_h // 2

    baseline = top + theme.body
    doc.text(
        rect.x, baseline,
        truncate(name, rect.w * 0.7, theme.body, 600),
        size=theme.body, fill=theme.ink, weight=600,
    )
    display = str(data.get("display", "—"))
    if unit := data.get("unit"):
        display = f"{display} {unit}"
    doc.text(
        rect.right, baseline, display,
        size=theme.body, fill=theme.ink, weight=600, anchor="end",
    )

    bar_y = top + round(theme.body * 1.6)
    doc.rect(rect.x, bar_y, rect.w, bar_h, theme.ink)
    doc.rect(
        rect.x + stroke, bar_y + stroke, rect.w - 2 * stroke, bar_h - 2 * stroke, theme.bg
    )
    if isinstance(value, (int, float)):
        frac = min(max((value - lo) / (hi - lo), 0.0), 1.0)
        fill_w = round((rect.w - 4 * stroke) * frac)
        if fill_w > 0:
            doc.rect(
                rect.x + 2 * stroke,
                bar_y + 2 * stroke,
                fill_w,
                bar_h - 4 * stroke,
                theme.color(options.get("color"), theme.accent),
            )
