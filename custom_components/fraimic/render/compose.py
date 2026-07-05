"""Compose a screen: header + slots + widgets -> SVG -> PNG.

Pure and CPU-bound; ``render_screen_png`` must run in an executor. All data is
already in the RenderContext, so nothing here touches Home Assistant.
"""

from __future__ import annotations

import logging

from .context import RenderContext
from .layout import divider_lines, slot_rects
from .schema import ScreenConfig
from .svg import SvgDoc, measure, rasterize, snap_to_colors, truncate
from .theme import Theme
from .widgets import WIDGET_REGISTRY
from .widgets.base import render_error

_LOGGER = logging.getLogger(__name__)


def build_doc(screen: ScreenConfig, ctx: RenderContext, width: int, height: int) -> SvgDoc:
    """Build the complete screen SVG document at the *viewed* resolution."""
    theme = Theme.for_screen(
        width,
        height,
        background=screen.background,
        accent=screen.accent,
        padding=screen.padding,
        show_header=screen.show_header,
    )
    doc = SvgDoc(width, height, theme.bg)

    if screen.show_header:
        _header(doc, screen, ctx, theme)

    rects = slot_rects(
        screen.layout, width, height, padding=theme.padding, header_h=theme.header_h
    )
    for x1, y1, x2, y2 in divider_lines(
        screen.layout, width, height, padding=theme.padding, header_h=theme.header_h
    ):
        doc.line(x1, y1, x2, y2, theme.ink, theme.rule)

    for index, widget in enumerate(screen.widgets):
        rect = rects[widget.slot]
        renderer = WIDGET_REGISTRY.get(widget.type)
        data = ctx.widget_data.get(index)
        try:
            if renderer is None:
                render_error(doc, rect, f"Unknown widget: {widget.type}", theme)
            else:
                renderer(doc, rect, widget.options, data, ctx, theme)
        except Exception:  # noqa: BLE001 - one bad widget must not kill the screen
            _LOGGER.exception(
                "Widget %r in slot %r failed to render", widget.type, widget.slot
            )
            render_error(doc, rect, f"{widget.type} failed to render", theme)

    return doc


def build_svg(screen: ScreenConfig, ctx: RenderContext, width: int, height: int) -> str:
    """The composed screen as an SVG string."""
    return build_doc(screen, ctx, width, height).to_string()


def _header(doc: SvgDoc, screen: ScreenConfig, ctx: RenderContext, theme: Theme) -> None:
    """Slim title bar: screen name left, date + time right, rule below."""
    x0, x1 = theme.padding, theme.width - theme.padding
    baseline = theme.padding + round(theme.header_h * 0.42)
    stamp = ctx.now.strftime("%a %-d %b · %H:%M")
    stamp_w = measure(stamp, theme.small, 500)
    doc.text(
        x0,
        baseline,
        truncate(screen.name, x1 - x0 - stamp_w - theme.small * 2, theme.title, 600),
        size=theme.title,
        fill=theme.ink,
        weight=600,
    )
    doc.text(x1, baseline, stamp, size=theme.small, fill=theme.ink, weight=500, anchor="end")
    rule_y = theme.padding + round(theme.header_h * 0.68)
    doc.line(x0, rule_y, x1, rule_y, theme.ink, theme.rule)


def render_screen(
    screen: ScreenConfig, ctx: RenderContext, width: int, height: int
) -> tuple[bytes, str]:
    """Rasterise the composed screen; return (png, dither_mode).

    Executor-only (CPU-bound). Antialiased edge pixels are snapped back to
    the set of colours the screen actually uses — otherwise they quantise
    unpredictably on the panel (grey glyph edges land on muted green).
    Embedded photo regions are pre-dithered by their widget renderer and
    excluded from the snap, so the final screen remains palette-pure and can
    use ``mode="none"`` without diffusion leaking into vector regions.
    """
    from ..const import MODE_NONE

    doc = build_doc(screen, ctx, width, height)
    png = snap_to_colors(
        rasterize(doc.to_string(), width, height), doc.colors, doc.raster_rects
    )
    return png, MODE_NONE


def render_screen_png(
    screen: ScreenConfig, ctx: RenderContext, width: int, height: int
) -> bytes:
    """Convenience wrapper returning only the PNG bytes."""
    return render_screen(screen, ctx, width, height)[0]
