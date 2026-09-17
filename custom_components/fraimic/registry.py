"""Device lookups across supported Home Assistant versions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.helpers.device_registry import DeviceEntry, DeviceRegistry


def device_by_identifier(
    registry: DeviceRegistry, identifier: tuple[str, str], config_entry_id: str
) -> DeviceEntry | None:
    """Scope identifiers to their owning entry on HA 2026.8 and newer."""
    if lookup := getattr(registry, "async_get_device_by_identifier", None):
        return lookup(identifier, config_entry_id)
    # HA 2025.12–2026.7 still uses globally unique identifiers.
    return registry.async_get_device(identifiers={identifier})


def remove_legacy_scene_devices(registry: DeviceRegistry) -> None:
    """Remove the shared scene device even if its former host entry is disabled."""
    identifiers = {(DOMAIN, "fraimic_scenes")}
    if lookup := getattr(registry, "async_get_devices", None):
        devices = lookup(identifiers=identifiers)
    else:
        device = registry.async_get_device(identifiers=identifiers)
        devices = [device] if device is not None else []
    for device in devices:
        registry.async_remove_device(device.id)
