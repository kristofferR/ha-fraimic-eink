"""Agenda widgets: calendar events and todo checklist."""

from __future__ import annotations

from typing import Any

from ..context import RenderContext
from ..layout import Rect
from ..svg import SvgDoc, measure, truncate
from ..theme import Theme
from .base import fetch_error, render_error


def render_calendar(
    doc: SvgDoc, rect: Rect, options: dict, data: Any, ctx: RenderContext, theme: Theme
) -> None:
    if (err := fetch_error(data)) is not None:
        render_error(doc, rect, err, theme)
        return

    events = data.get("events", [])
    if not events:
        doc.text(
            rect.cx,
            rect.cy + round(theme.body * 0.36),
            "No upcoming events",
            size=theme.body,
            fill=theme.ink,
            anchor="middle",
        )
        return

    row_h = round(theme.body * 1.9)
    header_h = round(theme.label * 2.0)
    accent_w = max(3, theme.rule + 1)
    time_w = round(measure("00:00", theme.body, 600)) + round(theme.body * 0.7)

    y = rect.y
    current_day: str | None = None
    for event in events:
        day = event.get("day", "")
        if day != current_day:
            if y + header_h + row_h > rect.bottom:
                break
            current_day = day
            doc.text(
                rect.x,
                y + header_h - round(theme.label * 0.5),
                day.upper(),
                size=theme.label,
                fill=theme.ink,
                weight=600,
                letter_spacing=theme.label * 0.08,
            )
            y += header_h
        if y + row_h > rect.bottom:
            break
        baseline = y + row_h // 2 + round(theme.body * 0.36)
        doc.rect(rect.x, y + row_h // 6, accent_w, row_h - row_h // 3, theme.accent)
        x_time = rect.x + accent_w + round(theme.body * 0.5)
        time_label = event.get("time") or ""
        doc.text(x_time, baseline, time_label, size=theme.body, fill=theme.ink, weight=600)
        x_title = x_time + (time_w if time_label else 0)
        doc.text(
            x_title,
            baseline,
            truncate(str(event.get("title", "")), rect.right - x_title, theme.body),
            size=theme.body,
            fill=theme.ink,
        )
        y += row_h


def render_todo(
    doc: SvgDoc, rect: Rect, options: dict, data: Any, ctx: RenderContext, theme: Theme
) -> None:
    if (err := fetch_error(data)) is not None:
        render_error(doc, rect, err, theme)
        return

    items = data.get("items", [])
    if not items:
        doc.text(
            rect.cx,
            rect.cy + round(theme.body * 0.36),
            "All done",
            size=theme.body,
            fill=theme.ink,
            anchor="middle",
        )
        return

    row_h = round(theme.body * 2.0)
    box = round(theme.body * 0.85)
    stroke = max(2, theme.rule)
    limit = min(len(items), options.get("max_items") or len(items), max(1, rect.h // row_h))

    y = rect.y
    for item in items[:limit]:
        baseline = y + row_h // 2 + round(theme.body * 0.36)
        box_y = y + (row_h - box) // 2
        done = bool(item.get("done"))
        if done:
            doc.rect(rect.x, box_y, box, box, theme.ink)
            # White check mark inside the filled box.
            inset = max(2, box // 5)
            doc.path(
                f"M{rect.x + inset} {box_y + box // 2}"
                f"L{rect.x + box // 2 - 1} {box_y + box - inset}"
                f"L{rect.x + box - inset} {box_y + inset}",
                "none",
                stroke=theme.bg,
                stroke_width=stroke,
            )
        else:
            doc.rect(rect.x, box_y, box, box, theme.ink)
            doc.rect(
                rect.x + stroke,
                box_y + stroke,
                box - 2 * stroke,
                box - 2 * stroke,
                theme.bg,
            )
        x_text = rect.x + box + round(theme.body * 0.6)
        text = truncate(str(item.get("summary", "")), rect.right - x_text, theme.body)
        doc.text(x_text, baseline, text, size=theme.body, fill=theme.ink)
        if done:
            strike_y = y + row_h // 2
            doc.line(
                x_text,
                strike_y,
                x_text + round(measure(text, theme.body)),
                strike_y,
                theme.ink,
                max(1, round(theme.scale)),
            )
        y += row_h
