"""Diagnostics support for the Fraimic E-Ink Canvas."""

from __future__ import annotations

import re
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .api import FraimicError
from .const import (
    CONF_CLOUD_EMAIL,
    CONF_CLOUD_DEVICE_ID,
    CONF_CLOUD_PASSWORD,
    CONF_NASA_API_KEY,
    CONF_PEXELS_KEY,
    CONF_SMITHSONIAN_KEY,
    CONF_UNSPLASH_KEY,
)
from .coordinator import FraimicConfigEntry
from .log_page import parse_logs_page

# Values under these keys are redacted in the structured data and also
# scrubbed wherever they appear verbatim in the free-text frame logs.
TO_REDACT = {
    "ssid", "wifi_ssid", "ip", "ip_address",
    "mac", "mac_address", "bssid", "wifi_mac",
    CONF_CLOUD_PASSWORD,
    CONF_CLOUD_EMAIL,
    CONF_CLOUD_DEVICE_ID,
    "album_device_id",
    "album_id",
    "wake_album_id",
    "upload_id",
    "device_key",
    "device_id",
    CONF_NASA_API_KEY,
    CONF_SMITHSONIAN_KEY,
    CONF_UNSPLASH_KEY,
    CONF_PEXELS_KEY,
}

# How many recent log lines per boot to include from the /logs admin page.
LOG_TAIL = 80


def _identifiers(data: Any) -> list[str]:
    """Collect every string value diagnostics redact, including nested ones."""
    values: list[str] = []
    if isinstance(data, dict):
        for key, value in data.items():
            if key in TO_REDACT and isinstance(value, str) and value:
                values.append(value)
            else:
                values.extend(_identifiers(value))
    elif isinstance(data, list):
        for item in data:
            values.extend(_identifiers(item))
    return values


def _scrub(lines: list[str], secrets: list[str]) -> list[str]:
    """Blank identifiers that appear verbatim in free-text log lines.

    The structured diagnostics redact by key; the /logs text is free-form, so
    scrub the same values there. The firmware's album proxy logs its upstream
    path, ``/api/v1/albums/<device_key>``, and the device key alone is enough
    to list the account's albums.
    """
    unique = sorted({s for s in secrets if s}, key=len, reverse=True)
    if not unique:
        return list(lines)
    pattern = re.compile("|".join(map(re.escape, unique)), re.IGNORECASE)
    return [pattern.sub("**REDACTED**", line) for line in lines]


async def _async_logs(entry: FraimicConfigEntry) -> dict[str, Any]:
    """Best-effort recent frame logs; never raises."""
    runtime = entry.runtime_data
    coordinator = runtime.coordinator
    try:
        parsed = parse_logs_page(await coordinator.client.get_logs(verbose=True))
    except FraimicError as err:
        return {"error": str(err)}
    secrets = [
        *_identifiers(coordinator.data or {}),
        *_identifiers(dict(entry.options)),
        *(_identifiers(runtime.cloud.diagnostics()) if runtime.cloud else ()),
        # The device-key unique_id, even when this poll's data is missing.
        entry.unique_id or "",
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
    # Slow health data is fetched only for this explicit diagnostics request.
    await coordinator.async_refresh_info_page()
    return {
        # entry.title embeds the host/IP, so it's omitted from shared diagnostics.
        "entry": {
            "options": async_redact_data(dict(entry.options), TO_REDACT),
            "resolution": [entry.data.get("width"), entry.data.get("height")],
        },
        "data": async_redact_data(coordinator.data or {}, TO_REDACT),
        "battery_health": dict(coordinator.info_page),
        "power": entry.runtime_data.power.diagnostics(),
        "cloud": (
            async_redact_data(entry.runtime_data.cloud.diagnostics(), TO_REDACT)
            if entry.runtime_data.cloud is not None
            else None
        ),
        "awake_window": (
            window.diagnostics()
            if (window := getattr(entry.runtime_data, "awake_window", None))
            else None
        ),
        # Recent frame logs (/logs admin page) — the only source for the WiFi
        # drop / upload-wedge symptoms; fetched on demand, never fatal.
        "logs": await _async_logs(entry),
    }
