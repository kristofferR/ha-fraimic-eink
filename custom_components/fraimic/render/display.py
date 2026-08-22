"""Render a screen and push it to the frame (or preview it battery-free).

The renderer produces the screen at the *viewed* orientation (width/height
swapped when the frame is mounted at 90/270) as a PNG; the existing
``async_render_and_upload`` pipeline then applies the base rotation, quantises
with dither mode "none" (all screen colours are exact palette values, so
quantisation is lossless), packs the ``.bin``, and uploads.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

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
    PLAYLIST_TONE_VALUES,
)
from ..power import TRIGGER_MANUAL
from .compose import render_screen
from .fetch import async_build_context
from .schema import KIND_PICTURE, ScreenConfig

if TYPE_CHECKING:
    from ..coordinator import FraimicConfigEntry

# The screen PNG already is final panel content: no photo enhancement.
_NEUTRAL_OVERRIDES = {
    ATTR_FIT: FIT_COVER,
    ATTR_MODE: MODE_NONE,
    ATTR_SATURATION: 1.0,
    ATTR_CONTRAST: 1.0,
    ATTR_SHARPEN: 0.0,
    ATTR_TONE: 0.0,
}


def _public_art_dict(candidate) -> dict:
    """Attribution metadata safe for HA state and service responses."""
    return {
        key: value
        for key in (
            "provider",
            "item_id",
            "title",
            "artist",
            "license",
            "attribution",
            "width",
            "height",
        )
        if (value := getattr(candidate, key, None)) is not None
    }


def viewed_size(entry) -> tuple[int, int]:
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
    width, height = viewed_size(entry)
    try:
        return await hass.async_add_executor_job(
            render_screen, screen, ctx, width, height
        )
    except Exception as err:
        raise HomeAssistantError(
            f"Failed to render screen {screen.name!r}: {err}"
        ) from err


async def _async_picture_source(
    hass: HomeAssistant, entry: FraimicConfigEntry, screen: ScreenConfig
) -> tuple[bytes, dict, object | None]:
    """Raw bytes + conversion overrides (+ art attribution) for a picture screen.

    Pictures go through the normal photo pipeline (dither + preprocessing) —
    this is the screenshot-URL / camera / online-provider path, not the vector
    renderer.
    """
    from ..source import async_get_source_bytes

    source = screen.source or {}
    art = None
    overrides = _picture_overrides(source)
    if source.get("library_image"):
        raise HomeAssistantError("Library pictures use the cached render path")
    if provider_key := source.get("provider"):
        from ..providers.caption import composite_with_caption
        from ..providers.ha import (
            ArtFetchError,
            async_art_by_media_id,
            async_fetch_art,
        )

        fit = source.get("fit") or entry.options.get(ATTR_FIT, FIT_COVER)
        if item_id := source.get("provider_item"):
            try:
                art = await async_art_by_media_id(
                    hass, entry, provider_key, item_id
                )
                raw = art.data
            except ArtFetchError:
                metadata = source.get("metadata") or {}
                download_url = metadata.get("download_url")
                if not isinstance(download_url, str) or not download_url:
                    raise
                raw = await async_get_source_bytes(
                    hass, url=download_url, redact_url=True
                )
        else:
            art = await async_fetch_art(
                hass,
                entry,
                provider_key,
                query=source.get("query"),
                fit=fit,
            )
            raw = art.data
        attribution = (
            art.candidate.attribution
            if art is not None
            else (source.get("metadata") or {}).get("attribution")
        )
        if source.get("caption") and attribution:
            width, height = viewed_size(entry)
            try:
                raw = await hass.async_add_executor_job(
                    composite_with_caption,
                    raw,
                    attribution,
                    width,
                    height,
                    fit,
                )
            except Exception as err:
                raise ArtFetchError(f"Captioned image: {err}") from err
    else:
        raw = await async_get_source_bytes(
            hass,
            url=source.get("url"),
            entity_id=source.get("entity"),
            redact_url=True,
        )
    return raw, overrides, art


def _picture_overrides(source: dict) -> dict:
    """Resolve per-slide picture controls into conversion overrides."""
    overrides = {}
    if fit := source.get("fit"):
        overrides[ATTR_FIT] = fit
    if mode := source.get("mode"):
        overrides[ATTR_MODE] = mode
    if (tone := source.get("tone")) in PLAYLIST_TONE_VALUES:
        overrides[ATTR_TONE] = PLAYLIST_TONE_VALUES[tone]
    if crop := source.get("crop"):
        overrides["crop"] = tuple(crop)
    return overrides


async def async_show_screen(
    hass: HomeAssistant,
    entry,
    screen: ScreenConfig,
    *,
    preview_only: bool = False,
    skip_if_hash: str | None = None,
    hold_playlist: bool = True,
    trigger: str = TRIGGER_MANUAL,
) -> dict:
    """Render ``screen`` and upload it — or only refresh the screen preview.

    ``preview_only`` runs the identical render + quantisation but skips the
    upload: a zero-battery iterate loop against the screen-preview image
    entity. ``skip_if_hash``/``hold_playlist`` are the playlist scheduler's
    knobs (skip unchanged content; don't hold yourself).
    """
    # Local import: services.py imports this module at load time.
    from ..services import (
        async_convert_for_entry,
        async_render_and_upload,
        begin_external_upload,
        finish_external_upload,
    )

    scheduler = (
        begin_external_upload(entry) if hold_playlist and not preview_only else None
    )
    uploaded = False
    try:
        art = None
        art_info: dict | None = None
        rendered = None
        if screen.kind == KIND_PICTURE:
            source = screen.source or {}
            if image_id := source.get("library_image"):
                from ..library import get_library

                library = get_library(hass)
                if library is None:
                    raise HomeAssistantError("The Fraimic library is not set up")
                overrides = _picture_overrides(source)
                rendered = await library.async_render_for_entry(
                    image_id, entry, overrides
                )
                png = b""
            else:
                png, overrides, art = await _async_picture_source(hass, entry, screen)
            art_info = _public_art_dict(art.candidate) if art is not None else None
            if isinstance(source.get("metadata"), dict):
                art_info = {**source["metadata"], **(art_info or {})}
            preprocess = True
        else:
            png, mode = await async_render_screen(hass, entry, screen)
            overrides = dict(_NEUTRAL_OVERRIDES)
            overrides[ATTR_MODE] = mode
            preprocess = False
        width, height = viewed_size(entry)
        runtime = entry.runtime_data
        overlay_count = 0
        overlay_manager = None
        if getattr(hass, "data", None) is not None:
            from ..overlays import get_overlay_manager

            overlay_manager = get_overlay_manager(hass)
        if (
            screen.kind == KIND_PICTURE
            and getattr(screen, "overlay_mode", "inherit") == "inherit"
            and overlay_manager is not None
        ):
            from ..overlays import async_apply_frame_overlays

            if rendered is None:
                rendered = await async_convert_for_entry(
                    hass, entry, png, overrides, preprocess=True
                )
            base_preview = rendered[1]
            if base_preview is not None:
                composed, overlay_count = await async_apply_frame_overlays(
                    hass, entry, base_preview, art_info
                )
                if overlay_count:
                    rendered = await async_convert_for_entry(
                        hass,
                        entry,
                        composed,
                        _NEUTRAL_OVERRIDES,
                        preprocess=False,
                    )
                    png = b""
                    overrides = dict(_NEUTRAL_OVERRIDES)
                    preprocess = False

        if preview_only:
            if rendered is None:
                rendered = await async_convert_for_entry(
                    hass, entry, png, overrides, preprocess=preprocess
                )
            bin_data, preview_png, used_mode = rendered
            _set_screen_preview(runtime, preview_png, used_mode)
            runtime.last_overlay_count = overlay_count
            return {
                "uploaded": False,
                "content_hash": hashlib.sha256(bin_data).hexdigest(),
                "mode": used_mode,
                "width": width,
                "height": height,
                "art": art_info,
            }

        upload_kwargs = {
            "preprocess": preprocess,
            "skip_if_hash": skip_if_hash,
            "hold_playlist": scheduler is None and hold_playlist,
        }
        if rendered is not None:
            upload_kwargs["rendered"] = rendered
        if trigger != TRIGGER_MANUAL:
            upload_kwargs["trigger"] = trigger
        result = await async_render_and_upload(
            hass, entry, png, overrides, **upload_kwargs
        )
        uploaded = result.get("uploaded", True)
        displayed = result.get("displayed", uploaded)
        preview_png = result.pop("preview_png", None)
        _set_screen_preview(runtime, preview_png, result["mode"])
        runtime.last_overlay_count = overlay_count
        if displayed or result.get("content_hash") == skip_if_hash:
            # Attribution for whatever is now on the glass (None for
            # non-provider content, so stale credits never outlive their image).
            runtime.last_art = art_info
            runtime.media_title = (art_info or {}).get("title") or screen.name
            # Entities read this lazily — poke coordinator listeners so their
            # attributes update now instead of at the next poll.
            runtime.coordinator.async_update_listeners()
            if uploaded and art is not None:
                from ..providers.ha import async_art_displayed

                await async_art_displayed(hass, entry, art)
        return {"width": width, "height": height, "art": art_info, **result}
    finally:
        finish_external_upload(scheduler, uploaded=uploaded)


def _set_screen_preview(runtime, preview_png: bytes | None, mode: str) -> None:
    if preview_png and runtime.screen_preview_image is not None:
        runtime.screen_preview_image.set_preview(preview_png, mode)
