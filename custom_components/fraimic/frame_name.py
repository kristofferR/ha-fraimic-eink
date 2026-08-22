"""Resolve the current Home Assistant display name for a Fraimic frame."""

from __future__ import annotations

from typing import Any

from .const import DOMAIN


def frame_display_name(hass: Any, entry: Any) -> str:
    """Prefer a user-renamed device over the config entry's original title."""
    from homeassistant.helpers import device_registry as dr

    registry = dr.async_get(hass)
    device = registry.async_get_device(
        identifiers={(DOMAIN, entry.unique_id or entry.entry_id)}
    )
    if device is None:
        return entry.title
    return device.name_by_user or device.name or entry.title
