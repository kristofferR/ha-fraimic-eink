"""Core widget pack: clock, date, stat tile, entity list, template text."""

from __future__ import annotations

from typing import Any

from ..context import RenderContext
from ..icons import icon_path
from ..layout import Rect
from ..svg import SvgDoc, fit_size, measure, truncate, wrap
from ..theme import Theme
from .base import fetch_error, render_error

# Baseline offset: distance from a text's vertical centre to its baseline,
# as a fraction of font size (approximates Inter's cap height / 2).
_BASELINE = 0.36


def _widget_label(doc: SvgDoc, rect: Rect, text: str, theme: Theme) -> int:
    """Uppercase label at the top-left of a widget; returns its height."""
    doc.text(
        rect.x,
        rect.y + theme.label,
        truncate(text.upper(), rect.w * 0.75, theme.label, 600),
        size=theme.label,
        fill=theme.ink,
        weight=600,
        letter_spacing=theme.label * 0.08,
    )
    return round(theme.label * 1.6)


def render_clock(
    doc: SvgDoc, rect: Rect, options: dict, data: Any, ctx: RenderContext, theme: Theme
) -> None:
    text = ctx.now.strftime(options.get("format", "%H:%M"))
    base = min(theme.display, round(rect.h * 0.72))
    size = fit_size(text, rect.w * 0.94, base, theme.title, 700)
    doc.text(
        rect.cx,
        rect.cy + round(size * _BASELINE),
        text,
        size=size,
        fill=theme.ink,
        weight=700,
        anchor="middle",
    )


def render_date(
    doc: SvgDoc, rect: Rect, options: dict, data: Any, ctx: RenderContext, theme: Theme
) -> None:
    text = ctx.now.strftime(options.get("format", "%A, %-d %B"))
    base = min(round(theme.title * 1.5), round(rect.h * 0.5))
    size = fit_size(text, rect.w * 0.94, base, theme.small, 600)
    doc.text(
        rect.cx,
        rect.cy + round(size * _BASELINE),
        text,
        size=size,
        fill=theme.ink,
        weight=600,
        anchor="middle",
    )


def render_stat(
    doc: SvgDoc, rect: Rect, options: dict, data: Any, ctx: RenderContext, theme: Theme
) -> None:
    if (err := fetch_error(data)) is not None:
        render_error(doc, rect, err, theme)
        return

    label = options.get("name") or data.get("name") or options.get("entity", "")
    _widget_label(doc, rect, label, theme)

    icon_name = options.get("icon") or data.get("icon")
    value_fill = theme.color(options.get("color"))
    if icon_name:
        icon_fill = theme.color(options.get("color"), theme.accent)
        doc.icon(
            icon_path(icon_name),
            rect.right - theme.icon,
            rect.y,
            theme.icon,
            icon_fill,
        )

    value = str(data.get("value", "—"))
    unit = options.get("unit") or data.get("unit") or ""
    gap = max(4, theme.value // 12)
    # Start generous (big slots deserve a big number) and shrink until
    # value + unit fit the tile width.
    size = min(round(theme.value * 1.4), round(rect.h * 0.38))
    while size > theme.body:
        unit_size = max(theme.small, round(size * 0.38))
        total = measure(value, size, 700)
        if unit:
            total += gap + measure(unit, unit_size, 500)
        if total <= rect.w:
            break
        size = max(theme.body, int(size * 0.92))
    unit_size = max(theme.small, round(size * 0.38))

    baseline = rect.cy + round(size * _BASELINE)
    doc.text(rect.x, baseline, value, size=size, fill=value_fill, weight=700)
    if unit:
        doc.text(
            rect.x + round(measure(value, size, 700)) + gap,
            baseline,
            unit,
            size=unit_size,
            fill=theme.ink,
            weight=500,
        )

    delta = data.get("trend_delta")
    if isinstance(delta, (int, float)) and delta != 0:
        arrow = max(8, theme.small // 2 + 2)
        y = baseline + round(theme.small * 1.7)
        top, bottom = y - arrow, y
        if delta > 0:
            d = f"M{rect.x} {bottom}L{rect.x + arrow // 2} {top}L{rect.x + arrow} {bottom}Z"
        else:
            d = f"M{rect.x} {top}L{rect.x + arrow // 2} {bottom}L{rect.x + arrow} {top}Z"
        doc.path(d, theme.ink)
        doc.text(
            rect.x + arrow + max(4, arrow // 2),
            y,
            f"{delta:+.1f}".rstrip("0").rstrip("."),
            size=theme.small,
            fill=theme.ink,
            weight=500,
        )


def render_entities(
    doc: SvgDoc, rect: Rect, options: dict, data: Any, ctx: RenderContext, theme: Theme
) -> None:
    if (err := fetch_error(data)) is not None:
        render_error(doc, rect, err, theme)
        return

    rows = data.get("rows", [])
    row_h = round(theme.body * 2.1)
    limit = min(
        len(rows),
        options.get("max_rows") or len(rows),
        max(1, rect.h // row_h),
    )
    hairline = max(1, round(theme.scale))
    icon_size = round(theme.body * 1.15)
    gap = round(theme.body * 0.55)

    y = rect.y
    for index, row in enumerate(rows[:limit]):
        baseline = y + row_h // 2 + round(theme.body * _BASELINE)
        x_text = rect.x
        if icon := row.get("icon"):
            doc.icon(
                icon_path(icon),
                rect.x,
                y + (row_h - icon_size) // 2,
                icon_size,
                theme.ink,
            )
            x_text = rect.x + icon_size + gap
        value = str(row.get("value", ""))
        value_w = min(measure(value, theme.body, 600), rect.w * 0.45)
        doc.text(
            rect.right,
            baseline,
            truncate(value, rect.w * 0.45, theme.body, 600),
            size=theme.body,
            fill=theme.ink,
            weight=600,
            anchor="end",
        )
        doc.text(
            x_text,
            baseline,
            truncate(
                str(row.get("name", "")),
                rect.right - x_text - value_w - gap,
                theme.body,
            ),
            size=theme.body,
            fill=theme.ink,
        )
        if index < limit - 1:
            doc.line(rect.x, y + row_h, rect.right, y + row_h, theme.ink, hairline)
        y += row_h


def render_template(
    doc: SvgDoc, rect: Rect, options: dict, data: Any, ctx: RenderContext, theme: Theme
) -> None:
    if (err := fetch_error(data)) is not None:
        render_error(doc, rect, err, theme)
        return

    size = {
        "s": theme.small,
        "m": theme.body,
        "l": round(theme.title * 1.1),
    }[options.get("size", "m")]
    line_h = round(size * 1.45)
    lines = wrap(str(data.get("text", "")), rect.w, size)
    max_lines = max(1, rect.h // line_h)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = truncate(lines[-1] + "…", rect.w, size)

    centered = options.get("align") == "center"
    x = rect.cx if centered else rect.x
    anchor = "middle" if centered else "start"
    block_h = len(lines) * line_h
    y = max(rect.y, rect.cy - block_h // 2) + round(size * 0.8)
    for line in lines:
        doc.text(x, y, line, size=size, fill=theme.ink, anchor=anchor)
        y += line_h


CORE_WIDGETS = {
    "clock": render_clock,
    "date": render_date,
    "stat": render_stat,
    "entities": render_entities,
    "template": render_template,
}
