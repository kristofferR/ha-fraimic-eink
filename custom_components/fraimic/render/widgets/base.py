"""Widget renderer protocol and shared error placeholder.

A widget renderer is a plain function::

    def render(doc: SvgDoc, rect: Rect, options: dict, data: Any,
               ctx: RenderContext, theme: Theme) -> None

``data`` is the payload the fetch layer gathered for this widget (or None for
widgets that only need ``ctx.now``). Renderers must draw entirely inside
``rect`` and must never raise for bad data — that's what ``render_error`` and
the compose-level try/except are for.
"""

from __future__ import annotations

from typing import Any, Callable

from ..context import RenderContext
from ..icons import icon_path
from ..layout import Rect
from ..svg import SvgDoc, wrap
from ..theme import Theme

WidgetRenderer = Callable[[SvgDoc, Rect, dict, Any, RenderContext, Theme], None]


def fetch_error(data: Any) -> str | None:
    """The error message if this widget's fetch failed, else None."""
    if isinstance(data, dict) and "error" in data:
        return str(data["error"])
    return None


def render_error(doc: SvgDoc, rect: Rect, message: str, theme: Theme) -> None:
    """Small centred alert glyph + wrapped message; deliberately quiet."""
    icon_size = theme.icon
    max_w = max(icon_size, rect.w - theme.small * 2)
    lines = wrap(message, max_w, theme.small)[:3]
    line_h = round(theme.small * 1.4)
    block_h = icon_size + theme.small + len(lines) * line_h
    top = rect.cy - block_h // 2
    doc.icon(
        icon_path("mdi:alert-circle-outline"),
        rect.cx - icon_size // 2,
        top,
        icon_size,
        theme.ink,
    )
    y = top + icon_size + theme.small
    for line in lines:
        doc.text(rect.cx, y, line, size=theme.small, fill=theme.ink, anchor="middle")
        y += line_h
