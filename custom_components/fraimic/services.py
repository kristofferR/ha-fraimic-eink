"""Services for the Fraimic E-Ink Canvas integration.

Provides ``fraimic.upload_image`` which accepts an ordinary image (file path,
URL, or a camera/image entity), converts it to the frame's raw ``.bin`` format,
and uploads it.
"""

from __future__ import annotations

import logging

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import FraimicError
from .const import (
    ATTR_CONFIG_ENTRY,
    ATTR_CONTRAST,
    ATTR_DITHER,
    ATTR_FIT,
    ATTR_IMAGE_ENTITY,
    ATTR_MODE,
    ATTR_PATH,
    ATTR_ROTATE,
    ATTR_SATURATION,
    ATTR_SHARPEN,
    ATTR_URL,
    CONF_HEIGHT,
    CONF_ROTATION,
    CONF_WIDTH,
    DEFAULT_CONTRAST,
    DEFAULT_HEIGHT,
    DEFAULT_ROTATION,
    DEFAULT_SATURATION,
    DEFAULT_SHARPEN,
    DEFAULT_WIDTH,
    DITHER_MODES,
    DOMAIN,
    FIT_COVER,
    FIT_MODES,
    MODE_AUTO,
    MODE_NONE,
    SERVICE_UPLOAD_IMAGE,
)
from .image_convert import convert_image

_LOGGER = logging.getLogger(__name__)

MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024  # 25 MB safety cap for URL/file sources

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
            # Deprecated boolean kept for backward compatibility; superseded by `mode`.
            vol.Optional(ATTR_DITHER): cv.boolean,
        }
    ),
    _require_one_source,
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


async def _async_get_source_bytes(hass: HomeAssistant, call: ServiceCall) -> bytes:
    """Fetch the raw source image bytes from path, url, or an entity."""
    if (path := call.data.get(ATTR_PATH)) is not None:
        if not hass.config.is_allowed_path(path):
            raise ServiceValidationError(
                f"Path {path} is not allowed; add its folder to allowlist_external_dirs"
            )

        def _read() -> bytes:
            with open(path, "rb") as file:
                return file.read(MAX_DOWNLOAD_BYTES + 1)

        data = await hass.async_add_executor_job(_read)
        if len(data) > MAX_DOWNLOAD_BYTES:
            raise ServiceValidationError("Source file is too large")
        return data

    if (url := call.data.get(ATTR_URL)) is not None:
        session = async_get_clientsession(hass)
        try:
            resp = await session.get(url, timeout=aiohttp.ClientTimeout(total=30))
        except Exception as err:  # noqa: BLE001 - surfaced to the user
            raise HomeAssistantError(f"Could not download {url}: {err}") from err
        async with resp:
            if resp.status != 200:
                raise HomeAssistantError(f"Downloading {url} returned HTTP {resp.status}")
            data = await resp.content.read(MAX_DOWNLOAD_BYTES + 1)
            if len(data) > MAX_DOWNLOAD_BYTES:
                raise ServiceValidationError("Downloaded image is too large")
            return data

    entity_id = call.data[ATTR_IMAGE_ENTITY]
    domain = entity_id.split(".", 1)[0]
    if domain == "camera":
        from homeassistant.components.camera import async_get_image

        image = await async_get_image(hass, entity_id)
        return image.content
    if domain == "image":
        from homeassistant.components.image import async_get_image

        image = await async_get_image(hass, entity_id)
        return image.content
    raise ServiceValidationError(
        f"{entity_id} must be a camera or image entity"
    )


async def _async_handle_upload_image(call: ServiceCall) -> None:
    """Handle the ``fraimic.upload_image`` service call."""
    hass = call.hass
    entry = _resolve_entry(hass, call)
    runtime = entry.runtime_data

    raw = await _async_get_source_bytes(hass, call)

    width = entry.data.get(CONF_WIDTH, DEFAULT_WIDTH)
    height = entry.data.get(CONF_HEIGHT, DEFAULT_HEIGHT)
    options = entry.options
    # Each processing param: per-call value > per-frame option > global default.
    fit = call.data.get(ATTR_FIT, options.get(ATTR_FIT, FIT_COVER))
    saturation = call.data.get(ATTR_SATURATION, options.get(ATTR_SATURATION, DEFAULT_SATURATION))
    contrast = call.data.get(ATTR_CONTRAST, options.get(ATTR_CONTRAST, DEFAULT_CONTRAST))
    sharpen = call.data.get(ATTR_SHARPEN, options.get(ATTR_SHARPEN, DEFAULT_SHARPEN))
    # Per-frame base rotation (how the frame is mounted) + any per-call rotate.
    base_rotation = options.get(CONF_ROTATION, DEFAULT_ROTATION)
    rotate = (base_rotation + call.data.get(ATTR_ROTATE, 0)) % 360
    # The buffer is native-orientation; the preview is rotated back by the mount
    # rotation so the dashboard shows what you actually see on the wall.
    preview_rotate = (-base_rotation) % 360

    requested_mode = _resolve_mode(call.data, options)
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
            preview_rotate,
        )
    except Exception as err:  # noqa: BLE001 - Pillow raises a variety of errors
        raise HomeAssistantError(f"Could not convert the image: {err}") from err

    if requested_mode == MODE_AUTO:
        _LOGGER.info("Fraimic auto-selected dither mode '%s' for this image", used_mode)

    try:
        await runtime.client.upload_image(bin_data)
    except FraimicError as err:
        raise HomeAssistantError(f"Could not upload to the frame: {err}") from err

    if preview_png and runtime.preview_image is not None:
        runtime.preview_image.set_preview(preview_png, used_mode)

    # Pull a fresh snapshot so last-refresh / status updates promptly.
    await runtime.coordinator.async_request_refresh()


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
    preview_rotate: int,
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
    )
