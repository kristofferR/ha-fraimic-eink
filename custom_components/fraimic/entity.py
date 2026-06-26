"""Base entity for the Fraimic E-Ink Canvas integration."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_HEIGHT, CONF_WIDTH, DOMAIN, MANUFACTURER, MODEL, MODEL_NAMES
from .coordinator import FraimicDataUpdateCoordinator


class FraimicEntity(CoordinatorEntity[FraimicDataUpdateCoordinator]):
    """Common base wiring all entities to the single frame device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: FraimicDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        width = entry.data.get(CONF_WIDTH)
        height = entry.data.get(CONF_HEIGHT)
        model = MODEL
        if width and height:
            friendly = MODEL_NAMES.get((width, height))
            model = f"{friendly} {width}x{height}" if friendly else f"{MODEL} ({width}x{height})"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            manufacturer=MANUFACTURER,
            model=model,
            name=entry.title,
            serial_number=self._info_get("device_id"),
            sw_version=self._info_get("firmware_version"),
            configuration_url=f"http://{coordinator.client.host}/info",
        )

    def _info_get(self, *path: str) -> Any:
        """Safely walk the nested ``/api/info`` payload."""
        data: Any = self.coordinator.data
        for key in path:
            if not isinstance(data, dict):
                return None
            data = data.get(key)
        return data
