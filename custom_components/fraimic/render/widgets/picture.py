"""Image widget: an embedded photo/camera frame inside a dashboard screen.

The raw source bytes arrive via the fetch layer; fitting and re-encoding
happen here because widget renderers already run in the executor. The
embedded region is recorded on the SvgDoc so the palette snap skips it and
the conversion pipeline switches to error diffusion (which leaves the exact
palette flats of the rest of the screen untouched).
"""

from __future__ import annotations

import io
from typing import Any

from ..context import RenderContext
from ..layout import Rect
from ..svg import SvgDoc
from ..theme import Theme
from .base import fetch_error, render_error


def render_image(
    doc: SvgDoc, rect: Rect, options: dict, data: Any, ctx: RenderContext, theme: Theme
) -> None:
    if (err := fetch_error(data)) is not None:
        render_error(doc, rect, err, theme)
        return

    raw = data.get("bytes")
    if not raw:
        render_error(doc, rect, "No image data", theme)
        return

    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(raw)) as src:
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

    buf = io.BytesIO()
    image.save(buf, format="PNG")
    doc.image(buf.getvalue(), rect.x, rect.y, rect.w, rect.h)
