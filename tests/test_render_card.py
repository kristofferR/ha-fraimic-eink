"""The recorded-voice result card renders palette-pure at the frame's size."""

from __future__ import annotations

import io

import pytest
from conftest import load

card = load("render.card")
theme = load("render.theme")


@pytest.mark.parametrize("size", [(1440, 2560), (1600, 1200)])
def test_card_is_frame_sized_and_palette_pure(size: tuple[int, int]) -> None:
    from PIL import Image

    png = card.result_card(
        "Turned off 3 lights in the living room.", width=size[0], height=size[1],
        question="Turn off the living room lights", when="Sun 25 Oct, 14:06",
    )
    with Image.open(io.BytesIO(png)) as image:
        assert image.size == size
        colors = {color for _, color in image.convert("RGB").getcolors(maxcolors=16) or []}
    palette = {tuple(int(value[i:i + 2], 16) for i in (1, 3, 5)) for value in theme.PALETTE_HEX.values()}
    # Black text, white paper and the red label; antialiasing snaps away.
    assert colors <= palette and len(colors) == 3


def test_overlong_text_is_cut_with_an_ellipsis() -> None:
    lines = card._clamp("word " * 200, 600, 40, 500, 3)
    assert len(lines) == 3
    assert lines[-1].endswith("…")
