"""Spectra 6 design system: colours, type scale, and spacing for screens.

Every colour is one of the six *calibrated* panel colours from
``const.SPECTRA6_RGB``, so flat regions quantise losslessly to their palette
index (dither mode "none") and never speckle. No greys, no gradients, no
opacity — anything off-palette would dither into noise on the panel.

The type scale is tuned for the 13.3" frame (~150 PPI at 1600x1200) and scales
linearly with the frame's short edge so the Large Canvas gets proportionate
sizes.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..const import PALETTE_NAMES, SPECTRA6_RGB

# Named palette colour -> hex, using the exact calibrated panel values.
PALETTE_HEX: dict[str, str] = {
    name: "#{:02x}{:02x}{:02x}".format(*SPECTRA6_RGB[index])
    for name, index in PALETTE_NAMES.items()
}

# Short-edge reference the base type scale was designed against.
_BASE_SHORT_EDGE = 1200


@dataclass(frozen=True)
class Theme:
    """Resolved colours and pixel sizes for one rendered screen."""

    width: int
    height: int
    scale: float
    bg: str
    ink: str
    accent: str
    padding: int
    header_h: int
    rule: int  # hairline stroke width
    # Type scale (px).
    display: int  # clock
    value: int  # stat tile value
    title: int  # header / large text
    body: int
    small: int
    label: int  # uppercase widget labels
    icon: int  # default widget icon size

    @classmethod
    def for_screen(
        cls,
        width: int,
        height: int,
        *,
        background: str = "white",
        accent: str = "red",
        padding: int = 32,
        show_header: bool = True,
    ) -> Theme:
        scale = min(width, height) / _BASE_SHORT_EDGE
        # Ink flips to white on a black background; any other background keeps
        # black ink (the only pairing with enough contrast on this panel).
        ink = "white" if background == "black" else "black"

        def px(base: float, minimum: int = 8) -> int:
            return max(minimum, round(base * scale))

        return cls(
            width=width,
            height=height,
            scale=scale,
            bg=PALETTE_HEX[background],
            ink=PALETTE_HEX[ink],
            accent=PALETTE_HEX[accent],
            padding=max(0, round(padding * scale)),
            header_h=px(76) if show_header else 0,
            rule=max(2, round(2 * scale)),
            display=px(210),
            value=px(96),
            title=px(38),
            body=px(30),
            small=px(24),
            label=px(22),
            icon=px(52),
        )

    def color(self, name: str | None, fallback: str | None = None) -> str:
        """Resolve a palette colour name to hex (fallback: ink)."""
        if name and name in PALETTE_HEX:
            return PALETTE_HEX[name]
        return fallback if fallback is not None else self.ink
