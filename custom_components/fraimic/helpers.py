"""Shared helpers for resolving per-frame render parameters.

Both the ``upload_image`` service and the media library render images with the
same precedence — explicit call override > per-frame option > global default —
so the resolution logic lives here once.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.exceptions import HomeAssistantError

from .const import (
    ATTR_CONTRAST,
    ATTR_DITHER,
    ATTR_FIT,
    ATTR_MODE,
    ATTR_ROTATE,
    ATTR_SATURATION,
    ATTR_SHARPEN,
    ATTR_TONE,
    CONF_HEIGHT,
    CONF_ROTATION,
    CONF_WIDTH,
    DEFAULT_CONTRAST,
    DEFAULT_HEIGHT,
    DEFAULT_ROTATION,
    DEFAULT_SATURATION,
    DEFAULT_SHARPEN,
    DEFAULT_TONE,
    DEFAULT_WIDTH,
    DOMAIN,
    FIT_COVER,
    MAX_BIN_SIZE,
    MODE_AUTO,
    MODE_NONE,
)


def resolve_mode(overrides: dict, options: Any) -> str:
    """Pick the dither mode: call > legacy ``dither`` bool > frame option > auto."""
    if overrides.get(ATTR_MODE):
        return overrides[ATTR_MODE]
    if ATTR_DITHER in overrides:
        return MODE_AUTO if overrides[ATTR_DITHER] else MODE_NONE
    return options.get(ATTR_MODE, MODE_AUTO)


def resolve_render_params(entry: ConfigEntry, overrides: dict | None = None) -> dict[str, Any]:
    """Resolve the full conversion parameter set for one frame.

    The returned dict's keys match ``convert_image`` keyword arguments (plus
    nothing else), so it can be splatted into a conversion call and hashed as a
    render-cache key.
    """
    overrides = overrides or {}
    options = entry.options

    width = entry.data.get(CONF_WIDTH, DEFAULT_WIDTH)
    height = entry.data.get(CONF_HEIGHT, DEFAULT_HEIGHT)
    # Guard before the (memory-heavy) conversion so an absurd custom resolution
    # can't OOM Home Assistant; the frame would reject it post-conversion anyway.
    if width * height // 2 > MAX_BIN_SIZE:
        raise HomeAssistantError(
            f"Frame resolution {width}x{height} is too large to render"
        )

    # Per-frame base rotation (how the frame is mounted) + any per-call rotate.
    base_rotation = options.get(CONF_ROTATION, DEFAULT_ROTATION)
    return {
        "width": width,
        "height": height,
        "fit": overrides.get(ATTR_FIT, options.get(ATTR_FIT, FIT_COVER)),
        "rotate": (base_rotation + overrides.get(ATTR_ROTATE, 0)) % 360,
        # The buffer is native-orientation; the preview is rotated back by the
        # mount rotation so the dashboard shows what you actually see on the wall.
        "preview_rotate": (-base_rotation) % 360,
        "mode": resolve_mode(overrides, options),
        "saturation": overrides.get(
            ATTR_SATURATION, options.get(ATTR_SATURATION, DEFAULT_SATURATION)
        ),
        "contrast": overrides.get(ATTR_CONTRAST, options.get(ATTR_CONTRAST, DEFAULT_CONTRAST)),
        "sharpen": overrides.get(ATTR_SHARPEN, options.get(ATTR_SHARPEN, DEFAULT_SHARPEN)),
        "tone": overrides.get(ATTR_TONE, options.get(ATTR_TONE, DEFAULT_TONE)),
    }


def loaded_fraimic_entries(hass: HomeAssistant) -> list[ConfigEntry]:
    """All currently loaded Fraimic config entries."""
    return [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
    ]
