"""Diagnostics support for the Fraimic E-Ink Canvas."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import (
    CONF_NASA_API_KEY,
    CONF_PEXELS_KEY,
    CONF_SMITHSONIAN_KEY,
    CONF_UNSPLASH_KEY,
)
from .coordinator import FraimicConfigEntry

TO_REDACT = {
    "ssid",
    "ip",
    "wifi_ssid",
    "ip_address",
    "device_id",
    CONF_NASA_API_KEY,
    CONF_SMITHSONIAN_KEY,
    CONF_UNSPLASH_KEY,
    CONF_PEXELS_KEY,
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: FraimicConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data.coordinator
    return {
        # entry.title embeds the host/IP, so it's omitted from shared diagnostics.
        "entry": {
            "options": async_redact_data(dict(entry.options), TO_REDACT),
            "resolution": [entry.data.get("width"), entry.data.get("height")],
        },
        "data": async_redact_data(coordinator.data or {}, TO_REDACT),
    }
