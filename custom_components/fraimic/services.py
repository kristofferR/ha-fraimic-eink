"""Services for the Fraimic E-Ink Canvas integration.

Provides ``fraimic.upload_image`` which accepts an ordinary image (file path,
URL, or a camera/image entity), converts it to the frame's raw ``.bin`` format,
and uploads it.
"""

from __future__ import annotations

import hashlib
import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .api import FraimicError
from .const import (
    ATTR_CONFIG_ENTRY,
    ATTR_CONTRAST,
    ATTR_DITHER,
    ATTR_FIT,
    ATTR_IMAGE_ENTITY,
    ATTR_MODE,
    ATTR_PATH,
    ATTR_PREVIEW_ONLY,
    ATTR_ROTATE,
    ATTR_SATURATION,
    ATTR_SCREEN,
    ATTR_SCREEN_ID,
    ATTR_SHARPEN,
    ATTR_TONE,
    ATTR_URL,
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
    DITHER_MODES,
    DOMAIN,
    FIT_COVER,
    FIT_MODES,
    MAX_BIN_SIZE,
    MODE_AUTO,
    MODE_NONE,
    SERVICE_RENDER_SCREEN,
    SERVICE_UPLOAD_IMAGE,
)
from .image_convert import convert_image
from .render.display import async_show_screen
from .render.schema import SCREEN_SCHEMA, screen_from_dict
from .screens import AmbiguousScreenNameError, screen_by_key
from .source import async_get_source_bytes

_LOGGER = logging.getLogger(__name__)


class FrameUploadError(HomeAssistantError):
    """Raised when conversion succeeded but the frame upload failed."""


def _require_one_source(data: dict) -> dict:
    """Ensure exactly one image source was provided."""
    sources = [k for k in (ATTR_PATH, ATTR_URL, ATTR_IMAGE_ENTITY) if data.get(k)]
    if not sources:
        raise vol.Invalid(
            f"Provide one image source: {ATTR_PATH}, {ATTR_URL}, or {ATTR_IMAGE_ENTITY}"
        )
    return data


UPLOAD_IMAGE_SCHEMA = vol.All(
    vol.Schema(
        {
            vol.Optional(ATTR_CONFIG_ENTRY): cv.string,
            vol.Exclusive(ATTR_PATH, "source"): cv.string,
            vol.Exclusive(ATTR_URL, "source"): cv.url,
            vol.Exclusive(ATTR_IMAGE_ENTITY, "source"): cv.entity_id,
            # All processing params are optional with NO schema default — when a
            # call omits one, the frame's per-entry option (then the global
            # default) is used. This is what makes them configurable per frame.
            vol.Optional(ATTR_FIT): vol.In(FIT_MODES),
            vol.Optional(ATTR_ROTATE): vol.All(
                vol.Coerce(int), vol.In((0, 90, 180, 270))
            ),
            vol.Optional(ATTR_MODE): vol.In(DITHER_MODES),
            vol.Optional(ATTR_SATURATION): vol.All(
                vol.Coerce(float), vol.Range(min=0.0, max=3.0)
            ),
            vol.Optional(ATTR_CONTRAST): vol.All(
                vol.Coerce(float), vol.Range(min=0.0, max=3.0)
            ),
            vol.Optional(ATTR_SHARPEN): vol.All(
                vol.Coerce(float), vol.Range(min=0.0, max=100.0)
            ),
            vol.Optional(ATTR_TONE): vol.All(
                vol.Coerce(float), vol.Range(min=0.0, max=100.0)
            ),
            # Deprecated boolean kept for backward compatibility; superseded by `mode`.
            vol.Optional(ATTR_DITHER): cv.boolean,
        }
    ),
    _require_one_source,
)


def _require_screen_or_id(data: dict) -> dict:
    if (ATTR_SCREEN in data) == (ATTR_SCREEN_ID in data):
        raise vol.Invalid(
            f"Provide exactly one of {ATTR_SCREEN} (inline definition) or "
            f"{ATTR_SCREEN_ID} (a stored screen's id or name)"
        )
    return data


RENDER_SCREEN_SCHEMA = vol.All(
    vol.Schema(
        {
            vol.Optional(ATTR_CONFIG_ENTRY): cv.string,
            vol.Exclusive(ATTR_SCREEN, "screen"): vol.All(dict, SCREEN_SCHEMA),
            vol.Exclusive(ATTR_SCREEN_ID, "screen"): cv.string,
            vol.Optional(ATTR_PREVIEW_ONLY, default=False): cv.boolean,
        }
    ),
    _require_screen_or_id,
)


def _resolve_mode(data: dict, options: dict) -> str:
    """Pick the dither mode: call > legacy ``dither`` bool > frame option > auto."""
    if data.get(ATTR_MODE):
        return data[ATTR_MODE]
    if ATTR_DITHER in data:
        return MODE_AUTO if data[ATTR_DITHER] else MODE_NONE
    return options.get(ATTR_MODE, MODE_AUTO)


def async_setup_services(hass: HomeAssistant) -> None:
    """Register integration services (idempotent)."""
    if hass.services.has_service(DOMAIN, SERVICE_UPLOAD_IMAGE):
        return
    hass.services.async_register(
        DOMAIN,
        SERVICE_UPLOAD_IMAGE,
        _async_handle_upload_image,
        schema=UPLOAD_IMAGE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_RENDER_SCREEN,
        _async_handle_render_screen,
        schema=RENDER_SCREEN_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )


def _resolve_entry(hass: HomeAssistant, call: ServiceCall):
    """Return the loaded Fraimic config entry targeted by the call."""
    entry_id = call.data.get(ATTR_CONFIG_ENTRY)
    loaded = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
    ]
    if entry_id is not None:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN:
            raise ServiceValidationError(f"No Fraimic config entry with id {entry_id}")
        if entry.state is not ConfigEntryState.LOADED:
            raise ServiceValidationError("That Fraimic frame is not currently loaded")
        return entry
    if not loaded:
        raise ServiceValidationError("No Fraimic frame is set up")
    if len(loaded) > 1:
        raise ServiceValidationError(
            "Multiple Fraimic frames are configured; specify config_entry_id"
        )
    return loaded[0]


async def _async_handle_upload_image(call: ServiceCall) -> None:
    """Handle the ``fraimic.upload_image`` service call."""
    hass = call.hass
    entry = _resolve_entry(hass, call)
    raw = await async_get_source_bytes(
        hass,
        path=call.data.get(ATTR_PATH),
        url=call.data.get(ATTR_URL),
        entity_id=call.data.get(ATTR_IMAGE_ENTITY),
    )
    await async_render_and_upload(hass, entry, raw, dict(call.data))


async def _async_handle_render_screen(call: ServiceCall) -> ServiceResponse:
    """Handle the ``fraimic.render_screen`` service call."""
    hass = call.hass
    entry = _resolve_entry(hass, call)
    if (key := call.data.get(ATTR_SCREEN_ID)) is not None:
        try:
            screen = screen_by_key(entry, key)
        except AmbiguousScreenNameError as err:
            raise ServiceValidationError(str(err)) from err
        if screen is None:
            raise ServiceValidationError(
                f"No stored screen with id or name {key!r} on this frame"
            )
    else:
        screen = screen_from_dict(call.data[ATTR_SCREEN])
    result = await async_show_screen(
        hass, entry, screen, preview_only=call.data[ATTR_PREVIEW_ONLY]
    )
    return result if call.return_response else None


async def async_convert_for_entry(
    hass,
    entry,
    raw: bytes,
    overrides: dict | None = None,
    *,
    preprocess: bool = True,
) -> tuple[bytes, bytes | None, str]:
    """Convert ``raw`` image bytes for ``entry``'s frame, without uploading.

    Each processing param resolves as: explicit ``overrides`` value > per-frame
    option > global default. Returns ``(bin_data, preview_png, used_mode)``.
    ``preprocess=False`` skips photo enhancement (autocontrast/tone/...) for
    sources that are already final panel content — rendered dashboard screens.
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
    fit = overrides.get(ATTR_FIT, options.get(ATTR_FIT, FIT_COVER))
    saturation = overrides.get(ATTR_SATURATION, options.get(ATTR_SATURATION, DEFAULT_SATURATION))
    contrast = overrides.get(ATTR_CONTRAST, options.get(ATTR_CONTRAST, DEFAULT_CONTRAST))
    sharpen = overrides.get(ATTR_SHARPEN, options.get(ATTR_SHARPEN, DEFAULT_SHARPEN))
    tone = overrides.get(ATTR_TONE, options.get(ATTR_TONE, DEFAULT_TONE))
    # Per-frame base rotation (how the frame is mounted) + any per-call rotate.
    base_rotation = options.get(CONF_ROTATION, DEFAULT_ROTATION)
    rotate = (base_rotation + overrides.get(ATTR_ROTATE, 0)) % 360
    # The buffer is native-orientation; the preview is rotated back by the mount
    # rotation so the dashboard shows what you actually see on the wall.
    preview_rotate = (-base_rotation) % 360

    requested_mode = _resolve_mode(overrides, options)
    try:
        bin_data, preview_png, used_mode = await hass.async_add_executor_job(
            _convert,
            raw,
            width,
            height,
            fit,
            rotate,
            requested_mode,
            saturation,
            contrast,
            sharpen,
            tone,
            preview_rotate,
            preprocess,
        )
    except Exception as err:  # noqa: BLE001 - Pillow raises a variety of errors
        raise HomeAssistantError(f"Could not convert the image: {err}") from err

    if requested_mode == MODE_AUTO:
        _LOGGER.info("Fraimic auto-selected dither mode '%s' for this image", used_mode)
    return bin_data, preview_png, used_mode


async def async_render_and_upload(
    hass,
    entry,
    raw: bytes,
    overrides: dict | None = None,
    *,
    preprocess: bool = True,
    skip_if_hash: str | None = None,
    hold_playlist: bool = True,
) -> dict:
    """Convert ``raw`` image bytes and upload them to ``entry``'s frame.

    Shared by the ``upload_image`` service, the media_player ``play_media``
    path, and screen rendering. Returns
    ``{"mode", "content_hash", "uploaded"}``.

    ``skip_if_hash``: when the freshly packed ``.bin``'s SHA-256 equals this,
    the frame is not touched (``uploaded: False``) — content is identical and
    an upload would only burn a ~30 s e-ink refresh and battery.
    ``hold_playlist``: manual uploads pause the playlist scheduler for one
    interval; the scheduler's own uploads pass False.
    """
    runtime = entry.runtime_data
    scheduler = runtime.scheduler
    external_started = False
    if hold_playlist and scheduler is not None:
        if scheduler.busy:
            raise HomeAssistantError("A playlist upload is already in progress")
        scheduler.begin_external_upload()
        external_started = True
    try:
        async with runtime.upload_lock:
            bin_data, preview_png, used_mode = await async_convert_for_entry(
                hass, entry, raw, overrides, preprocess=preprocess
            )
            content_hash = hashlib.sha256(bin_data).hexdigest()
            if preview_png:
                runtime.last_preview = preview_png
                if runtime.preview_image is not None:
                    runtime.preview_image.set_preview(preview_png, used_mode)
            if skip_if_hash is not None and content_hash == skip_if_hash:
                return {
                    "mode": used_mode,
                    "content_hash": content_hash,
                    "uploaded": False,
                    "preview_png": preview_png,
                }

            try:
                await runtime.client.upload_image(bin_data)
            except FraimicError as err:
                raise FrameUploadError(f"Could not upload to the frame: {err}") from err

            if external_started:
                scheduler.finish_external_upload(uploaded=True)
                external_started = False

            # Pull a fresh snapshot so last-refresh / status updates promptly.
            await runtime.coordinator.async_request_refresh()
    finally:
        if external_started:
            scheduler.finish_external_upload(uploaded=False)

    return {
        "mode": used_mode,
        "content_hash": content_hash,
        "uploaded": True,
        "preview_png": preview_png,
    }


def _convert(
    raw: bytes,
    width: int,
    height: int,
    fit: str,
    rotate: int,
    mode: str,
    saturation: float,
    contrast: float,
    sharpen: float,
    tone: float,
    preview_rotate: int,
    preprocess: bool = True,
) -> tuple[bytes, bytes | None, str]:
    return convert_image(
        raw,
        width=width,
        height=height,
        fit=fit,
        rotate=rotate,
        preview_rotate=preview_rotate,
        mode=mode,
        saturation=saturation,
        contrast=contrast,
        sharpen=sharpen,
        tone=tone,
        preprocess=preprocess,
    )
