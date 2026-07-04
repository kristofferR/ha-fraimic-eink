"""Render a screen and push it to the frame (or preview it battery-free).

The renderer produces the screen at the *viewed* orientation (width/height
swapped when the frame is mounted at 90/270) as a PNG; the existing
``async_render_and_upload`` pipeline then applies the base rotation, quantises
with dither mode "none" (all screen colours are exact palette values, so
quantisation is lossless), packs the ``.bin``, and uploads.
"""

from __future__ import annotations

import hashlib

from homeassistant.core import HomeAssistant

from ..const import (
    ATTR_CONTRAST,
    ATTR_FIT,
    ATTR_MODE,
    ATTR_SATURATION,
    ATTR_SHARPEN,
    ATTR_TONE,
    CONF_HEIGHT,
    CONF_ROTATION,
    CONF_WIDTH,
    DEFAULT_HEIGHT,
    DEFAULT_ROTATION,
    DEFAULT_WIDTH,
    FIT_COVER,
    MODE_NONE,
)
from .compose import render_screen_png
from .fetch import async_build_context
from .schema import ScreenConfig

# The screen PNG already is final panel content: no photo enhancement.
_NEUTRAL_OVERRIDES = {
    ATTR_FIT: FIT_COVER,
    ATTR_MODE: MODE_NONE,
    ATTR_SATURATION: 1.0,
    ATTR_CONTRAST: 1.0,
    ATTR_SHARPEN: 0.0,
    ATTR_TONE: 0.0,
}


def _viewed_size(entry) -> tuple[int, int]:
    """Panel resolution swapped to the orientation the viewer actually sees."""
    width = entry.data.get(CONF_WIDTH, DEFAULT_WIDTH)
    height = entry.data.get(CONF_HEIGHT, DEFAULT_HEIGHT)
    if entry.options.get(CONF_ROTATION, DEFAULT_ROTATION) in (90, 270):
        return height, width
    return width, height


async def async_render_screen(hass: HomeAssistant, entry, screen: ScreenConfig) -> bytes:
    """Fetch widget data and render the screen to PNG bytes."""
    ctx = await async_build_context(hass, screen)
    width, height = _viewed_size(entry)
    return await hass.async_add_executor_job(
        render_screen_png, screen, ctx, width, height
    )


async def async_show_screen(
    hass: HomeAssistant, entry, screen: ScreenConfig, *, preview_only: bool = False
) -> dict:
    """Render ``screen`` and upload it — or only refresh the screen preview.

    ``preview_only`` runs the identical render + quantisation but skips the
    upload: a zero-battery iterate loop against the screen-preview image
    entity.
    """
    # Local import: services.py imports this module at load time.
    from ..services import async_convert_for_entry, async_render_and_upload

    png = await async_render_screen(hass, entry, screen)
    width, height = _viewed_size(entry)
    runtime = entry.runtime_data

    if preview_only:
        bin_data, preview_png, mode = await async_convert_for_entry(
            hass, entry, png, dict(_NEUTRAL_OVERRIDES), preprocess=False
        )
        _set_screen_preview(runtime, preview_png, mode)
        return {
            "uploaded": False,
            "content_hash": hashlib.sha256(bin_data).hexdigest(),
            "mode": mode,
            "width": width,
            "height": height,
        }

    result = await async_render_and_upload(
        hass, entry, png, dict(_NEUTRAL_OVERRIDES), preprocess=False
    )
    _set_screen_preview(runtime, runtime.last_preview, result["mode"])
    return {"uploaded": True, "width": width, "height": height, **result}


def _set_screen_preview(runtime, preview_png: bytes | None, mode: str) -> None:
    if preview_png and runtime.screen_preview_image is not None:
        runtime.screen_preview_image.set_preview(preview_png, mode)
