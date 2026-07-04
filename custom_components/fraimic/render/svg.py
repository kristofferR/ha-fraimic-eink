"""SVG document builder, text measurement, and resvg rasterisation.

Coordinates are integers wherever possible (crisp strokes on a panel that has
no greys to hide antialiasing in). Text metrics come from PIL reading the same
bundled Inter TTFs that resvg rasterises with, so measured widths track the
rendered result closely.

``rasterize`` is CPU-bound (resvg via pyo3) and must run in an executor.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape as _escape
from xml.sax.saxutils import quoteattr

FONT_DIR = Path(__file__).parent / "fonts" / "Inter"
FONT_FAMILY = "Inter"
FONT_FILES = {
    400: "Inter-Regular.ttf",
    500: "Inter-Medium.ttf",
    600: "Inter-SemiBold.ttf",
    700: "Inter-Bold.ttf",
}
ELLIPSIS = "…"

_font_cache: dict[tuple[int, int], Any] = {}


def _pil_font(size: int, weight: int):
    """A cached PIL font matching the bundled TTF resvg will use."""
    from PIL import ImageFont

    weight = weight if weight in FONT_FILES else 400
    key = (size, weight)
    font = _font_cache.get(key)
    if font is None:
        font = ImageFont.truetype(str(FONT_DIR / FONT_FILES[weight]), size)
        _font_cache[key] = font
    return font


def measure(text: str, size: int, weight: int = 400) -> float:
    """Rendered pixel width of ``text`` at ``size``/``weight``."""
    if not text:
        return 0.0
    return float(_pil_font(size, weight).getlength(text))


def truncate(text: str, max_w: float, size: int, weight: int = 400) -> str:
    """Ellipsis-truncate ``text`` to fit ``max_w`` pixels."""
    if measure(text, size, weight) <= max_w:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if measure(text[:mid] + ELLIPSIS, size, weight) <= max_w:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo].rstrip() + ELLIPSIS if lo else ELLIPSIS


def wrap(text: str, max_w: float, size: int, weight: int = 400) -> list[str]:
    """Word-wrap ``text`` into lines fitting ``max_w`` pixels.

    Overlong single words are ellipsis-truncated rather than broken mid-word.
    Explicit newlines are respected.
    """
    lines: list[str] = []
    for paragraph in text.split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if measure(candidate, size, weight) <= max_w:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return [
        line if measure(line, size, weight) <= max_w else truncate(line, max_w, size, weight)
        for line in lines
    ]


def fit_size(text: str, max_w: float, base: int, minimum: int, weight: int = 400) -> int:
    """Largest font size <= ``base`` at which ``text`` fits ``max_w`` pixels."""
    size = base
    while size > minimum and measure(text, size, weight) > max_w:
        size = max(minimum, int(size * 0.92))
    return size


class SvgDoc:
    """Accumulates SVG elements and serialises the document."""

    def __init__(self, width: int, height: int, background: str) -> None:
        self.width = width
        self.height = height
        self._parts: list[str] = [
            f'<rect width="{width}" height="{height}" fill="{background}"/>'
        ]

    def rect(self, x: int, y: int, w: int, h: int, fill: str, rx: int = 0) -> None:
        rx_attr = f' rx="{rx}"' if rx else ""
        self._parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}"{rx_attr}/>'
        )

    def line(self, x1: int, y1: int, x2: int, y2: int, stroke: str, width: int) -> None:
        self._parts.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'stroke="{stroke}" stroke-width="{width}"/>'
        )

    def circle(
        self, cx: int, cy: int, r: int, *, fill: str = "none",
        stroke: str | None = None, stroke_width: int = 0,
    ) -> None:
        stroke_attr = (
            f' stroke="{stroke}" stroke-width="{stroke_width}"' if stroke else ""
        )
        self._parts.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}"{stroke_attr}/>'
        )

    def path(self, d: str, fill: str, transform: str | None = None) -> None:
        transform_attr = f" transform={quoteattr(transform)}" if transform else ""
        self._parts.append(f'<path d={quoteattr(d)} fill="{fill}"{transform_attr}/>')

    def text(
        self,
        x: int,
        y: int,
        content: str,
        *,
        size: int,
        fill: str,
        weight: int = 400,
        anchor: str = "start",
        letter_spacing: float = 0.0,
    ) -> None:
        """Add a text element (``y`` is the baseline)."""
        spacing_attr = (
            f' letter-spacing="{letter_spacing:g}"' if letter_spacing else ""
        )
        anchor_attr = f' text-anchor="{anchor}"' if anchor != "start" else ""
        self._parts.append(
            f'<text x="{x}" y="{y}" font-family="{FONT_FAMILY}" '
            f'font-size="{size}" font-weight="{weight}" fill="{fill}"'
            f"{anchor_attr}{spacing_attr}>{_escape(content)}</text>"
        )

    def icon(self, path_d: str | None, x: int, y: int, size: int, fill: str) -> None:
        """Draw a 24x24-viewBox MDI path scaled into a ``size`` box at (x, y).

        ``path_d`` of None (unknown icon) draws a neutral outline circle so the
        layout stays intact without pretending to know the glyph.
        """
        if path_d is None:
            r = size // 2 - max(1, size // 12)
            stroke = max(2, size // 12)
            self.circle(
                x + size // 2, y + size // 2, r, stroke=fill, stroke_width=stroke
            )
            return
        scale = size / 24.0
        self.path(path_d, fill, transform=f"translate({x} {y}) scale({scale:g})")

    def to_string(self) -> str:
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" '
            f'height="{self.height}" viewBox="0 0 {self.width} {self.height}">'
            + "".join(self._parts)
            + "</svg>"
        )


def rasterize(svg: str, width: int, height: int) -> bytes:
    """Rasterise an SVG string to PNG bytes with the bundled fonts only.

    ``skip_system_fonts`` keeps output byte-identical across machines (HAOS,
    CI, dev laptops) — a prerequisite for content-hash upload skipping and
    golden tests.
    """
    import resvg_py

    return bytes(
        resvg_py.svg_to_bytes(
            svg_string=svg,
            width=width,
            height=height,
            font_dirs=[str(FONT_DIR)],
            skip_system_fonts=True,
            sans_serif_family=FONT_FAMILY,
        )
    )
