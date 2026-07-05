"""Fetch raw source-image bytes from a path, URL, or camera/image entity.

Shared by the ``upload_image`` service, picture screens, and the dashboard
``image`` widget. All sources are capped at ``MAX_SOURCE_BYTES``.
"""

from __future__ import annotations

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import MAX_SOURCE_BYTES


def checked_size(data: bytes) -> bytes:
    """Enforce the same source-size cap used for file/URL sources."""
    if len(data) > MAX_SOURCE_BYTES:
        raise ServiceValidationError("Source image is too large")
    return data


async def async_get_source_bytes(
    hass: HomeAssistant,
    *,
    path: str | None = None,
    url: str | None = None,
    entity_id: str | None = None,
    redact_url: bool = False,
) -> bytes:
    """Fetch raw image bytes from exactly one of the three source kinds."""
    if path is not None:
        if not hass.config.is_allowed_path(path):
            raise ServiceValidationError(
                f"Path {path} is not allowed; add its folder to allowlist_external_dirs"
            )

        def _read() -> bytes:
            with open(path, "rb") as file:
                return file.read(MAX_SOURCE_BYTES + 1)

        try:
            data = await hass.async_add_executor_job(_read)
        except OSError as err:
            raise ServiceValidationError(f"Could not read {path}: {err}") from err
        return checked_size(data)

    if url is not None:
        url_label = "image URL" if redact_url else url
        session = async_get_clientsession(hass)
        try:
            resp = await session.get(url, timeout=aiohttp.ClientTimeout(total=30))
        except Exception as err:  # noqa: BLE001 - surfaced to the user
            raise HomeAssistantError(f"Could not download {url_label}: {err}") from err
        async with resp:
            if resp.status != 200:
                raise HomeAssistantError(
                    f"Downloading {url_label} returned HTTP {resp.status}"
                )
            data = await resp.content.read(MAX_SOURCE_BYTES + 1)
            return checked_size(data)

    if entity_id is None:
        raise ServiceValidationError("No image source provided")
    domain = entity_id.split(".", 1)[0]
    if domain == "camera":
        from homeassistant.components.camera import async_get_image

        image = await async_get_image(hass, entity_id)
        return checked_size(image.content)
    if domain == "image":
        from homeassistant.components.image import async_get_image

        image = await async_get_image(hass, entity_id)
        return checked_size(image.content)
    raise ServiceValidationError(f"{entity_id} must be a camera or image entity")
