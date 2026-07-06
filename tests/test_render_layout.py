"""Tests for layout slot geometry (pure, no Home Assistant)."""

from __future__ import annotations

import pytest
from conftest import load

layout = load("render.layout")

SIZES = [(1600, 1200), (1200, 1600), (2560, 1440), (800, 480)]


def _overlap(a, b) -> bool:
    return not (
        a.right <= b.x or b.right <= a.x or a.bottom <= b.y or b.bottom <= a.y
    )


@pytest.mark.parametrize("name,slots", list(layout.LAYOUT_SLOTS.items()))
@pytest.mark.parametrize("width,height", SIZES)
@pytest.mark.parametrize("header_h", [0, 76])
def test_slots_fit_and_do_not_overlap(name, slots, width, height, header_h) -> None:
    rects = layout.slot_rects(name, width, height, padding=32, header_h=header_h)
    assert set(rects) == set(slots)
    values = list(rects.values())
    for rect in values:
        assert rect.w > 0 and rect.h > 0
        assert rect.x >= 32 and rect.y >= 32 + header_h
        assert rect.right <= width - 32 and rect.bottom <= height - 32
    for i, a in enumerate(values):
        for b in values[i + 1 :]:
            assert not _overlap(a, b), f"{name}: {a} overlaps {b}"


def test_unknown_layout_raises() -> None:
    with pytest.raises(ValueError):
        layout.slot_rects("nope", 800, 480, padding=16)


@pytest.mark.parametrize("name", list(layout.LAYOUT_SLOTS))
def test_divider_lines_sit_in_gutters(name) -> None:
    rects = layout.slot_rects(name, 1600, 1200, padding=32, header_h=76)
    lines = layout.divider_lines(name, 1600, 1200, padding=32, header_h=76)
    expected = {"full": 0, "half_horizontal": 1, "half_vertical": 1, "quadrant": 2}
    assert len(lines) == expected[name]
    for x1, y1, x2, y2 in lines:
        for rect in rects.values():
            if x1 == x2:  # vertical divider: strictly between columns
                assert x1 < rect.x or x1 > rect.right
            if y1 == y2:  # horizontal divider: strictly between rows
                assert y1 < rect.y or y1 > rect.bottom
