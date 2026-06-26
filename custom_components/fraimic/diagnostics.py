"""Diagnostics support for the Fraimic E-Ink Canvas."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .coordinator import FraimicConfigEntry

TO_REDACT = {"ssid", "ip", "wifi_ssid", "ip_address", "device_id"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: FraimicConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data.coordinator
    return {
        "entry": {
            "title": entry.title,
            "options": dict(entry.options),
        },
        "data": async_redact_data(coordinator.data or {}, TO_REDACT),
    }
