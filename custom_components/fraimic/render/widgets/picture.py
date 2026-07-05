"""Image widget: an embedded photo/camera frame inside a dashboard screen.

The raw source bytes arrive via the fetch layer; fitting and re-encoding
happen here because widget renderers already run in the executor. The
embedded region is recorded on the SvgDoc so the palette snap skips it and
the photo is pre-dithered before being embedded, keeping vector regions
palette-exact and deterministic.
"""

from __future__ import annotations

import io

from ...const import MAX_SOURCE_PIXELS, MODE_FLOYD_STEINBERG
from ...image_convert import _ensure_extra_decoders, quantize_image_to_png
from ..context import RenderContext
from ..layout import Rect
from ..svg import SvgDoc
from ..theme import Theme
from .base import fetch_error, render_error


def render_image(
    doc: SvgDoc,
    rect: Rect,
    options: dict,
    data: object,
    _ctx: RenderContext,
    theme: Theme,
) -> None:
    if (err := fetch_error(data)) is not None:
        render_error(doc, rect, err, theme)
        return

    raw = data.get("bytes") if isinstance(data, dict) else None
    if not isinstance(raw, bytes) or not raw:
        render_error(doc, rect, "No image data", theme)
        return

    from PIL import Image, ImageOps, UnidentifiedImageError

    _ensure_extra_decoders()
    try:
        with Image.open(io.BytesIO(raw)) as src:
            if src.width * src.height > MAX_SOURCE_PIXELS:
                render_error(
                    doc,
                    rect,
                    f"Source image is too large ({src.width}x{src.height})",
                    theme,
                )
                return
            image = ImageOps.exif_transpose(src)
            if image.mode not in ("RGB",):
                # Flatten transparency onto the screen background.
                rgba = image.convert("RGBA")
                bg_rgb = tuple(int(theme.bg[i : i + 2], 16) for i in (1, 3, 5))
                background = Image.new("RGBA", rgba.size, (*bg_rgb, 255))
                image = Image.alpha_composite(background, rgba).convert("RGB")
            size = (rect.w, rect.h)
            if options.get("fit") == "contain":
                bg_rgb = tuple(int(theme.bg[i : i + 2], 16) for i in (1, 3, 5))
                image = ImageOps.pad(
                    image, size, method=Image.Resampling.LANCZOS, color=bg_rgb
                )
            else:
                image = ImageOps.fit(
                    image, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5)
                )
    except UnidentifiedImageError:
        render_error(doc, rect, "Source is not a supported image", theme)
        return

    png = quantize_image_to_png(image, rect.w, rect.h, MODE_FLOYD_STEINBERG)
    doc.image(png, rect.x, rect.y, rect.w, rect.h)
