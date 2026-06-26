"""Binary sensor platform for the Fraimic E-Ink Canvas."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import FraimicConfigEntry
from .entity import FraimicEntity


def _g(data: dict[str, Any], *path: str) -> Any:
    cur: Any = data
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


@dataclass(frozen=True, kw_only=True)
class FraimicBinaryDescription(BinarySensorEntityDescription):
    """Describes a Fraimic binary sensor."""

    value_fn: Callable[[dict[str, Any]], bool | None]


BINARY_SENSORS: tuple[FraimicBinaryDescription, ...] = (
    FraimicBinaryDescription(
        key="charging",
        translation_key="charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=lambda d: _g(d, "battery", "charging"),
    ),
    FraimicBinaryDescription(
        key="cable_connected",
        translation_key="cable_connected",
        device_class=BinarySensorDeviceClass.PLUG,
        value_fn=lambda d: _g(d, "battery", "cable_connected"),
    ),
    FraimicBinaryDescription(
        key="wifi_connected",
        translation_key="wifi_connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: _g(d, "wifi", "connected"),
    ),
    FraimicBinaryDescription(
        key="registered",
        translation_key="registered",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: _g(d, "device", "registered"),
    ),
    FraimicBinaryDescription(
        key="time_synced",
        translation_key="time_synced",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: _g(d, "device", "time_synced"),
    ),
    FraimicBinaryDescription(
        key="voice_recording",
        translation_key="voice_recording",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: _g(d, "settings", "voice_recording"),
    ),
    FraimicBinaryDescription(
        key="keep_awake",
        translation_key="keep_awake",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: _g(d, "settings", "keep_awake"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FraimicConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Fraimic binary sensors from a config entry."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(FraimicBinarySensor(coordinator, desc) for desc in BINARY_SENSORS)


class FraimicBinarySensor(FraimicEntity, BinarySensorEntity):
    """A single Fraimic binary sensor."""

    entity_description: FraimicBinaryDescription

    def __init__(self, coordinator, description: FraimicBinaryDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data
        if not isinstance(data, dict):
            return None
        value = self.entity_description.value_fn(data)
        return None if value is None else bool(value)
