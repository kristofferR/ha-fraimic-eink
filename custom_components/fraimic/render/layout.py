"""Layout slot geometry for dashboard screens.

TRMNL-style layout grammar: a screen is one of four layouts, each defining
named slots that hold exactly one widget. All geometry is integer pixels so
strokes and rules land on whole pixels (fractional coordinates antialias into
off-palette greys that quantise unpredictably).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

LAYOUT_FULL: Final = "full"
LAYOUT_HALF_HORIZONTAL: Final = "half_horizontal"
LAYOUT_HALF_VERTICAL: Final = "half_vertical"
LAYOUT_QUADRANT: Final = "quadrant"

LAYOUT_SLOTS: Final[dict[str, tuple[str, ...]]] = {
    LAYOUT_FULL: ("main",),
    LAYOUT_HALF_HORIZONTAL: ("top", "bottom"),
    LAYOUT_HALF_VERTICAL: ("left", "right"),
    LAYOUT_QUADRANT: ("top_left", "top_right", "bottom_left", "bottom_right"),
}


@dataclass(frozen=True)
class Rect:
    """An integer pixel rectangle (x, y = top-left corner)."""

    x: int
    y: int
    w: int
    h: int

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h

    @property
    def cx(self) -> int:
        return self.x + self.w // 2

    @property
    def cy(self) -> int:
        return self.y + self.h // 2


def slot_rects(
    layout: str, width: int, height: int, *, padding: int, header_h: int = 0
) -> dict[str, Rect]:
    """Return the content rectangle for every slot of ``layout``.

    ``padding`` is both the outer margin and the gutter between slots;
    ``header_h`` reserves a band across the top (the screen title bar).
    """
    x0, y0 = padding, padding + header_h
    x1, y1 = width - padding, height - padding
    w, h = x1 - x0, y1 - y0
    gut = padding

    if layout == LAYOUT_FULL:
        return {"main": Rect(x0, y0, w, h)}
    if layout == LAYOUT_HALF_HORIZONTAL:
        each = (h - gut) // 2
        return {
            "top": Rect(x0, y0, w, each),
            "bottom": Rect(x0, y1 - each, w, each),
        }
    if layout == LAYOUT_HALF_VERTICAL:
        each = (w - gut) // 2
        return {
            "left": Rect(x0, y0, each, h),
            "right": Rect(x1 - each, y0, each, h),
        }
    if layout == LAYOUT_QUADRANT:
        each_w = (w - gut) // 2
        each_h = (h - gut) // 2
        return {
            "top_left": Rect(x0, y0, each_w, each_h),
            "top_right": Rect(x1 - each_w, y0, each_w, each_h),
            "bottom_left": Rect(x0, y1 - each_h, each_w, each_h),
            "bottom_right": Rect(x1 - each_w, y1 - each_h, each_w, each_h),
        }
    raise ValueError(f"Unknown layout: {layout}")


def divider_lines(
    layout: str, width: int, height: int, *, padding: int, header_h: int = 0
) -> list[tuple[int, int, int, int]]:
    """Hairline dividers centred in the gutters, as (x1, y1, x2, y2) tuples."""
    rects = slot_rects(layout, width, height, padding=padding, header_h=header_h)
    x0, y0 = padding, padding + header_h
    x1, y1 = width - padding, height - padding
    lines: list[tuple[int, int, int, int]] = []
    if layout == LAYOUT_HALF_HORIZONTAL:
        mid = (rects["top"].bottom + rects["bottom"].y) // 2
        lines.append((x0, mid, x1, mid))
    elif layout == LAYOUT_HALF_VERTICAL:
        mid = (rects["left"].right + rects["right"].x) // 2
        lines.append((mid, y0, mid, y1))
    elif layout == LAYOUT_QUADRANT:
        mid_x = (rects["top_left"].right + rects["top_right"].x) // 2
        mid_y = (rects["top_left"].bottom + rects["bottom_left"].y) // 2
        lines.append((x0, mid_y, x1, mid_y))
        lines.append((mid_x, y0, mid_x, y1))
    return lines
