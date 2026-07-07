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

from .api import FraimicConnectionError, FraimicError
from .const import (
    ATTR_CONFIG_ENTRY,
    ATTR_CONTRAST,
    ATTR_DITHER,
    ATTR_FIT,
    ATTR_IMAGE_ENTITY,
    ATTR_MODE,
    ATTR_CAPTION,
    ATTR_PATH,
    ATTR_PREVIEW_ONLY,
    ATTR_PROVIDER,
    ATTR_QUERY,
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
    PROVIDER_KEYS,
    PROVIDER_SHUFFLE,
    SERVICE_RENDER_SCREEN,
    SERVICE_SHOW_ONLINE_IMAGE,
    SERVICE_UPLOAD_IMAGE,
)
from .coordinator import FraimicConfigEntry
from .image_convert import convert_image
from .render.display import async_show_screen
from .render.schema import SCREEN_SCHEMA, screen_from_dict
from .screens import AmbiguousScreenNameError, screen_by_key
from .source import async_get_source_bytes

_LOGGER = logging.getLogger(__name__)


class FrameUploadError(HomeAssistantError):
    """Raised when conversion succeeded but the frame upload failed."""


def begin_external_upload(entry):
    """Block playlist work while a manual upload is being prepared."""
    scheduler = getattr(entry.runtime_data, "scheduler", None)
    if scheduler is None:
        return None
    if scheduler.busy:
        raise HomeAssistantError("A playlist upload is already in progress")
    scheduler.begin_external_upload()
    return scheduler


def finish_external_upload(scheduler, *, uploaded: bool, hold: bool = True) -> None:
    """Release a manual-upload guard and optionally hold the playlist."""
    if scheduler is not None:
        scheduler.finish_external_upload(uploaded=uploaded, hold=hold)


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

SHOW_ONLINE_IMAGE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY): cv.string,
        vol.Required(ATTR_PROVIDER): vol.In((*PROVIDER_KEYS, PROVIDER_SHUFFLE)),
        vol.Optional(ATTR_QUERY): cv.string,
        vol.Optional(ATTR_CAPTION, default=False): cv.boolean,
        vol.Optional(ATTR_PREVIEW_ONLY, default=False): cv.boolean,
    }
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
    hass.services.async_register(
        DOMAIN,
        SERVICE_SHOW_ONLINE_IMAGE,
        _async_handle_show_online_image,
        schema=SHOW_ONLINE_IMAGE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )


def _resolve_entry(hass: HomeAssistant, call: ServiceCall) -> FraimicConfigEntry:
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
    scheduler = begin_external_upload(entry)
    uploaded = False
    try:
        raw = await async_get_source_bytes(
            hass,
            path=call.data.get(ATTR_PATH),
            url=call.data.get(ATTR_URL),
            entity_id=call.data.get(ATTR_IMAGE_ENTITY),
        )
        result = await async_render_and_upload(
            hass, entry, raw, dict(call.data), hold_playlist=False
        )
        uploaded = result.get("uploaded", True)
        if uploaded:
            entry.runtime_data.last_art = None
    finally:
        finish_external_upload(scheduler, uploaded=uploaded)


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


async def _async_handle_show_online_image(call: ServiceCall) -> ServiceResponse:
    """Handle ``fraimic.show_online_image``: fetch + display one online image."""
    hass = call.hass
    entry = _resolve_entry(hass, call)
    screen = screen_from_dict(
        SCREEN_SCHEMA(
            {
                "name": "Online image",
                "kind": "picture",
                "provider": call.data[ATTR_PROVIDER],
                **(
                    {"query": call.data[ATTR_QUERY]}
                    if call.data.get(ATTR_QUERY)
                    else {}
                ),
                "caption": call.data[ATTR_CAPTION],
            }
        )
    )
    result = await async_show_screen(
        hass, entry, screen, preview_only=call.data[ATTR_PREVIEW_ONLY]
    )
    if not call.return_response:
        return None
    art = result.pop("art", None) or {}
    return {
        **result,
        "provider": art.get("provider"),
        "title": art.get("title"),
        "artist": art.get("artist"),
        "attribution": art.get("attribution"),
    }


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
    scheduler = begin_external_upload(entry) if hold_playlist else None
    uploaded = False
    try:
        async with runtime.upload_lock:
            bin_data, preview_png, used_mode = await async_convert_for_entry(
                hass, entry, raw, overrides, preprocess=preprocess
            )
            content_hash = hashlib.sha256(bin_data).hexdigest()
            if skip_if_hash is not None and content_hash == skip_if_hash:
                if preview_png:
                    runtime.last_preview = preview_png
                    if runtime.preview_image is not None:
                        runtime.preview_image.set_preview(preview_png, used_mode)
                return {
                    "mode": used_mode,
                    "content_hash": content_hash,
                    "uploaded": False,
                    "preview_png": preview_png,
                }

            try:
                await runtime.client.upload_image(bin_data)
            except FraimicConnectionError as err:
                raise FrameUploadError(f"Could not upload to the frame: {err}") from err
            except FraimicError as err:
                raise HomeAssistantError(f"Could not upload to the frame: {err}") from err

            uploaded = True
            if preview_png:
                runtime.last_preview = preview_png
                if runtime.preview_image is not None:
                    runtime.preview_image.set_preview(preview_png, used_mode)

            # Pull a fresh snapshot so last-refresh / status updates promptly.
            await runtime.coordinator.async_request_refresh()
    finally:
        finish_external_upload(scheduler, uploaded=uploaded)

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
