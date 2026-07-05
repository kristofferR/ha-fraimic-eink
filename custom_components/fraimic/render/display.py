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
from homeassistant.exceptions import HomeAssistantError

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
from .compose import render_screen
from .fetch import async_build_context
from .schema import KIND_PICTURE, ScreenConfig

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


async def async_render_screen(
    hass: HomeAssistant, entry, screen: ScreenConfig
) -> tuple[bytes, str]:
    """Fetch widget data and render the screen; returns (png, dither_mode)."""
    ctx = await async_build_context(hass, screen)
    width, height = _viewed_size(entry)
    try:
        return await hass.async_add_executor_job(
            render_screen, screen, ctx, width, height
        )
    except Exception as err:
        raise HomeAssistantError(
            f"Failed to render screen {screen.name!r}: {err}"
        ) from err


async def _async_picture_source(hass: HomeAssistant, screen: ScreenConfig) -> tuple[bytes, dict]:
    """Raw bytes + conversion overrides for a ``kind: picture`` screen.

    Pictures go through the normal photo pipeline (dither + preprocessing) —
    this is the screenshot-URL / camera path, not the vector renderer.
    """
    from ..source import async_get_source_bytes

    source = screen.source or {}
    raw = await async_get_source_bytes(
        hass,
        url=source.get("url"),
        entity_id=source.get("entity"),
        redact_url=True,
    )
    overrides: dict = {}
    if fit := source.get("fit"):
        overrides[ATTR_FIT] = fit
    if mode := source.get("mode"):
        overrides[ATTR_MODE] = mode
    return raw, overrides


async def async_show_screen(
    hass: HomeAssistant,
    entry,
    screen: ScreenConfig,
    *,
    preview_only: bool = False,
    skip_if_hash: str | None = None,
    hold_playlist: bool = True,
) -> dict:
    """Render ``screen`` and upload it — or only refresh the screen preview.

    ``preview_only`` runs the identical render + quantisation but skips the
    upload: a zero-battery iterate loop against the screen-preview image
    entity. ``skip_if_hash``/``hold_playlist`` are the playlist scheduler's
    knobs (skip unchanged content; don't hold yourself).
    """
    # Local import: services.py imports this module at load time.
    from ..services import async_convert_for_entry, async_render_and_upload

    if screen.kind == KIND_PICTURE:
        png, overrides = await _async_picture_source(hass, screen)
        preprocess = True
    else:
        png, mode = await async_render_screen(hass, entry, screen)
        overrides = dict(_NEUTRAL_OVERRIDES)
        overrides[ATTR_MODE] = mode
        preprocess = False
    width, height = _viewed_size(entry)
    runtime = entry.runtime_data

    if preview_only:
        bin_data, preview_png, used_mode = await async_convert_for_entry(
            hass, entry, png, overrides, preprocess=preprocess
        )
        _set_screen_preview(runtime, preview_png, used_mode)
        return {
            "uploaded": False,
            "content_hash": hashlib.sha256(bin_data).hexdigest(),
            "mode": used_mode,
            "width": width,
            "height": height,
        }

    result = await async_render_and_upload(
        hass,
        entry,
        png,
        overrides,
        preprocess=preprocess,
        skip_if_hash=skip_if_hash,
        hold_playlist=hold_playlist,
    )
    preview_png = result.pop("preview_png", None)
    _set_screen_preview(runtime, preview_png, result["mode"])
    return {"width": width, "height": height, **result}


def _set_screen_preview(runtime, preview_png: bytes | None, mode: str) -> None:
    if preview_png and runtime.screen_preview_image is not None:
        runtime.screen_preview_image.set_preview(preview_png, mode)
