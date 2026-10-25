"""The recorded-voice result card: the question, a rule, then the answer.

Drawn in exact panel colours with the bundled Inter fonts at the size of the
picture it becomes, so the photo pipeline maps it onto the panel losslessly.
Pure and CPU-bound: run it in an executor.
"""

from __future__ import annotations

from .svg import SvgDoc, rasterize, snap_to_colors, truncate, wrap
from .theme import PALETTE_HEX

# Line heights relative to the font size.
_QUESTION_LEADING = 1.3
_ANSWER_LEADING = 1.22


def _clamp(text: str, max_w: float, size: int, weight: int, limit: int) -> list[str]:
    """Wrap ``text``; past ``limit`` lines, ellipsis-truncate the last one."""
    lines = wrap(" ".join(text.split()), max_w, size, weight)
    if len(lines) <= limit:
        return lines
    rest = " ".join(lines[limit - 1:])
    # A fitting rest still lost lines, so always mark the cut.
    return [*lines[: limit - 1], truncate(f"{rest}…", max_w, size, weight)]


def result_card(
    answer: str,
    *,
    width: int,
    height: int,
    question: str | None = None,
    label: str = "YOU ASKED",
    when: str = "",
) -> bytes:
    """PNG of one result card at ``width`` x ``height``."""
    black, red = PALETTE_HEX["black"], PALETTE_HEX["red"]
    unit = min(width, height) / 1200
    landscape = width > height
    pad = round((90 if landscape else 110) * unit)
    inner = width - 2 * pad
    doc = SvgDoc(width, height, PALETTE_HEX["white"])

    y = pad
    label_size = round(34 * unit)
    doc.text(pad, y + label_size, label, size=label_size, fill=red, weight=700,
             letter_spacing=round(5 * unit))
    y += round(label_size * 1.6)
    if question:
        size = round(52 * unit)
        step = round(size * _QUESTION_LEADING)
        for line in _clamp(question, inner, size, 500, 3):
            doc.text(pad, y + size, line, size=size, fill=black, weight=500)
            y += step
    y += round(40 * unit)
    rule = max(2, round(6 * unit))
    doc.rect(pad, y, inner, rule, black)
    y += rule + round(56 * unit)

    footer_size = round(30 * unit)
    footer_baseline = height - pad
    footer_rule = footer_baseline - round(footer_size * 1.9)
    doc.rect(pad, footer_rule, inner, max(1, round(3 * unit)), black)
    doc.text(pad, footer_baseline, "Home Assistant", size=footer_size, fill=black, weight=500)
    if when:
        doc.text(width - pad, footer_baseline, when, size=footer_size, fill=black,
                 weight=500, anchor="end")

    # The largest answer size whose lines fit above the footer.
    room = footer_rule - round(48 * unit) - y
    size = round(104 * unit)
    minimum = round(52 * unit)
    while True:
        lines = wrap(" ".join(answer.split()), inner, size, 700)
        if len(lines) * size * _ANSWER_LEADING <= room or size <= minimum:
            break
        size = max(minimum, int(size * 0.92))
    step = round(size * _ANSWER_LEADING)
    lines = _clamp(answer, inner, size, 700, max(1, room // step))
    for index, line in enumerate(lines):
        doc.text(pad, y + size + index * step, line, size=size, fill=black, weight=700)

    png = rasterize(doc.to_string(), width, height)
    return snap_to_colors(png, doc.colors)
