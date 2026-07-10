"""Diagnostics support for the Fraimic E-Ink Canvas."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .api import FraimicError
from .const import (
    CONF_NASA_API_KEY,
    CONF_PEXELS_KEY,
    CONF_SMITHSONIAN_KEY,
    CONF_UNSPLASH_KEY,
)
from .coordinator import FraimicConfigEntry
from .log_page import parse_logs_page

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

# How many recent log lines per boot to include from the /logs admin page.
LOG_TAIL = 80


def _scrub(lines: list[str], secrets: list[str]) -> list[str]:
    """Blank the frame's own network identifiers in free-text log lines.

    The structured diagnostics redact ssid/ip; the /logs text is free-form, so
    scrub the same values (SSID, BSSID, IP, MAC) where they appear verbatim.
    """
    result = []
    for line in lines:
        for secret in secrets:
            if secret:
                line = line.replace(secret, "**REDACTED**")
        result.append(line)
    return result


async def _async_logs(coordinator) -> dict[str, Any]:
    """Best-effort recent frame logs; never raises."""
    try:
        parsed = parse_logs_page(await coordinator.client.get_logs(verbose=True))
    except FraimicError as err:
        return {"error": str(err)}
    data = coordinator.data or {}
    wifi = data.get("wifi") if isinstance(data, dict) else None
    secrets = [
        str(value)
        for value in (
            (wifi or {}).get("ssid"),
            (wifi or {}).get("ip"),
            (wifi or {}).get("mac"),
            (wifi or {}).get("bssid"),
        )
        if value
    ]
    return {
        boot: _scrub(lines[-LOG_TAIL:], secrets)
        for boot, lines in parsed.items()
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
        # Recent frame logs (/logs admin page) — the only source for the WiFi
        # drop / upload-wedge symptoms; fetched on demand, never fatal.
        "logs": await _async_logs(coordinator),
    }
