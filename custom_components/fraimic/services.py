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
    ATTR_LIBRARY_IMAGE,
    ATTR_MODE,
    ATTR_PATH,
    ATTR_ROTATE,
    ATTR_SATURATION,
    ATTR_SHARPEN,
    ATTR_TONE,
    ATTR_URL,
    DITHER_MODES,
    DOMAIN,
    FIT_MODES,
    MODE_AUTO,
    SERVICE_UPLOAD_IMAGE,
)
from .const import MAX_SOURCE_BYTES as MAX_DOWNLOAD_BYTES
from .helpers import resolve_render_params
from .image_convert import convert_image
from .library import get_library

_LOGGER = logging.getLogger(__name__)

def _require_one_source(data: dict) -> dict:
    """Ensure exactly one image source was provided."""
    sources = [
        k
        for k in (ATTR_PATH, ATTR_URL, ATTR_IMAGE_ENTITY, ATTR_LIBRARY_IMAGE)
        if data.get(k)
    ]
    if not sources:
        raise vol.Invalid(
            f"Provide one image source: {ATTR_PATH}, {ATTR_URL}, "
            f"{ATTR_IMAGE_ENTITY}, or {ATTR_LIBRARY_IMAGE}"
        )
    return data


UPLOAD_IMAGE_SCHEMA = vol.All(
    vol.Schema(
        {
            vol.Optional(ATTR_CONFIG_ENTRY): cv.string,
            vol.Exclusive(ATTR_PATH, "source"): cv.string,
            vol.Exclusive(ATTR_URL, "source"): cv.url,
            vol.Exclusive(ATTR_IMAGE_ENTITY, "source"): cv.entity_id,
            vol.Exclusive(ATTR_LIBRARY_IMAGE, "source"): cv.string,
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

        try:
            data = await hass.async_add_executor_job(_read)
        except OSError as err:
            raise ServiceValidationError(f"Could not read {path}: {err}") from err
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
        return _checked(image.content)
    if domain == "image":
        from homeassistant.components.image import async_get_image

        image = await async_get_image(hass, entity_id)
        return _checked(image.content)
    raise ServiceValidationError(
        f"{entity_id} must be a camera or image entity"
    )


def _checked(data: bytes) -> bytes:
    """Apply the same source-size cap used for file/URL sources."""
    if len(data) > MAX_DOWNLOAD_BYTES:
        raise ServiceValidationError("Source image is too large")
    return data


async def _async_handle_upload_image(call: ServiceCall) -> None:
    """Handle the ``fraimic.upload_image`` service call."""
    hass = call.hass
    entry = _resolve_entry(hass, call)
    if image_id := call.data.get(ATTR_LIBRARY_IMAGE):
        # Library sends go through the render cache (and honour saved crops).
        library = get_library(hass)
        if library is None:
            raise ServiceValidationError("The Fraimic library is not set up")
        await library.async_send_to_entry(image_id, entry, dict(call.data))
        return
    raw = await _async_get_source_bytes(hass, call)
    await async_render_and_upload(hass, entry, raw, dict(call.data))


async def async_render_and_upload(hass, entry, raw: bytes, overrides: dict | None = None) -> None:
    """Convert ``raw`` image bytes and upload them to ``entry``'s frame.

    Each processing param resolves as: explicit ``overrides`` value > per-frame
    option > global default. Shared by the ``upload_image`` service and the
    media_player ``play_media`` path.
    """
    runtime = entry.runtime_data
    params = resolve_render_params(entry, overrides)
    requested_mode = params["mode"]
    try:
        bin_data, preview_png, used_mode = await hass.async_add_executor_job(
            lambda: convert_image(raw, **params)
        )
    except Exception as err:  # noqa: BLE001 - Pillow raises a variety of errors
        raise HomeAssistantError(f"Could not convert the image: {err}") from err

    if requested_mode == MODE_AUTO:
        _LOGGER.info("Fraimic auto-selected dither mode '%s' for this image", used_mode)

    try:
        await runtime.client.upload_image(bin_data)
    except FraimicError as err:
        raise HomeAssistantError(f"Could not upload to the frame: {err}") from err

    if preview_png:
        runtime.last_preview = preview_png
        if runtime.preview_image is not None:
            runtime.preview_image.set_preview(preview_png, used_mode)

    # Pull a fresh snapshot so last-refresh / status updates promptly.
    await runtime.coordinator.async_request_refresh()
