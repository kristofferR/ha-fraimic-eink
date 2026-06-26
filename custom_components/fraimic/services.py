"""Services for the Fraimic E-Ink Canvas integration.

Provides ``fraimic.upload_image`` which accepts an ordinary image (file path,
URL, or a camera/image entity), converts it to the frame's raw ``.bin`` format,
and uploads it.
"""

from __future__ import annotations

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
    ATTR_DITHER,
    ATTR_FIT,
    ATTR_IMAGE_ENTITY,
    ATTR_PATH,
    ATTR_ROTATE,
    ATTR_URL,
    CONF_HEIGHT,
    CONF_WIDTH,
    DEFAULT_HEIGHT,
    DEFAULT_WIDTH,
    DOMAIN,
    FIT_COVER,
    FIT_MODES,
    SERVICE_UPLOAD_IMAGE,
)
from .image_convert import convert_image

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
            vol.Optional(ATTR_FIT, default=FIT_COVER): vol.In(FIT_MODES),
            vol.Optional(ATTR_ROTATE, default=0): vol.All(
                vol.Coerce(int), vol.In((0, 90, 180, 270))
            ),
            vol.Optional(ATTR_DITHER, default=True): cv.boolean,
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

    try:
        bin_data, preview_png = await hass.async_add_executor_job(
            _convert,
            raw,
            width,
            height,
            call.data[ATTR_FIT],
            call.data[ATTR_ROTATE],
            call.data[ATTR_DITHER],
        )
    except Exception as err:  # noqa: BLE001 - Pillow raises a variety of errors
        raise HomeAssistantError(f"Could not convert the image: {err}") from err

    try:
        await runtime.client.upload_image(bin_data)
    except FraimicError as err:
        raise HomeAssistantError(f"Could not upload to the frame: {err}") from err

    if preview_png and runtime.preview_image is not None:
        runtime.preview_image.set_preview(preview_png)

    # Pull a fresh snapshot so last-refresh / status updates promptly.
    await runtime.coordinator.async_request_refresh()


def _convert(
    raw: bytes, width: int, height: int, fit: str, rotate: int, dither: bool
) -> tuple[bytes, bytes | None]:
    return convert_image(
        raw, width=width, height=height, fit=fit, rotate=rotate, dither=dither
    )
