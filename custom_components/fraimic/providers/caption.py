"""Caption strip: attribution rendered under an online image. HA-free, CPU-bound.

The strip is built with the same SVG/Inter/snap pipeline as dashboard
screens, so it is exact-palette black and white and survives the photo
pipeline untouched (contrast/tone preserve the endpoints and error
diffusion has zero error on exact palette colours).
"""

from __future__ import annotations

import io

from ..render.svg import SvgDoc, rasterize, snap_to_colors, truncate
from ..render.theme import PALETTE_HEX


def strip_height(height: int) -> int:
    return max(48, height // 22)


def caption_strip_png(text: str, width: int, strip_h: int) -> bytes:
    """A black strip with white attribution text, exactly width x strip_h."""
    doc = SvgDoc(width, strip_h, PALETTE_HEX["black"])
    size = max(16, round(strip_h * 0.42))
    pad = round(strip_h * 0.45)
    doc.text(
        pad,
        strip_h // 2 + round(size * 0.36),
        truncate(text, width - 2 * pad, size, 500),
        size=size,
        fill=PALETTE_HEX["white"],
        weight=500,
    )
    return snap_to_colors(rasterize(doc.to_string(), width, strip_h), doc.colors)


def composite_with_caption(photo: bytes, text: str, width: int, height: int) -> bytes:
    """Cover-fit ``photo`` above a caption strip; returns width x height PNG."""
    from PIL import Image, ImageOps

    strip_h = strip_height(height)
    strip = Image.open(io.BytesIO(caption_strip_png(text, width, strip_h)))
    with Image.open(io.BytesIO(photo)) as src:
        image = ImageOps.exif_transpose(src).convert("RGB")
        photo_part = ImageOps.fit(
            image,
            (width, height - strip_h),
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        )
    canvas = Image.new("RGB", (width, height), (255, 255, 255))
    canvas.paste(photo_part, (0, 0))
    canvas.paste(strip.convert("RGB"), (0, height - strip_h))
    out = io.BytesIO()
    canvas.save(out, format="PNG")
    return out.getvalue()
