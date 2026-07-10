"""Sensor platform for the Fraimic E-Ink Canvas."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import FraimicConfigEntry
from .entity import FraimicEntity


def _parse_timestamp(value: Any) -> datetime | None:
    """Parse a naive ISO timestamp from the frame into a local-aware datetime."""
    if not isinstance(value, str) or not value:
        return None
    parsed = dt_util.parse_datetime(value)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
    return parsed


@dataclass(frozen=True, kw_only=True)
class FraimicSensorDescription(SensorEntityDescription):
    """Describes a Fraimic sensor and how to read it from ``/api/info``."""

    value_fn: Callable[[dict[str, Any]], Any]


def _g(data: dict[str, Any], *path: str) -> Any:
    cur: Any = data
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


SENSORS: tuple[FraimicSensorDescription, ...] = (
    FraimicSensorDescription(
        key="battery_percent",
        translation_key="battery_percent",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _g(d, "battery", "percent"),
    ),
    FraimicSensorDescription(
        key="battery_voltage",
        translation_key="battery_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.MILLIVOLT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: _g(d, "battery", "voltage_mv"),
    ),
    FraimicSensorDescription(
        key="battery_source",
        translation_key="battery_source",
        device_class=SensorDeviceClass.ENUM,
        options=["fuel_gauge", "adc"],
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: _g(d, "battery", "source"),
    ),
    FraimicSensorDescription(
        key="wifi_rssi",
        translation_key="wifi_rssi",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: _g(d, "wifi", "rssi"),
    ),
    FraimicSensorDescription(
        key="wifi_ssid",
        translation_key="wifi_ssid",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: _g(d, "wifi", "ssid"),
    ),
    FraimicSensorDescription(
        key="wifi_channel",
        translation_key="wifi_channel",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: _g(d, "wifi", "channel"),
    ),
    FraimicSensorDescription(
        key="ip_address",
        translation_key="ip_address",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: _g(d, "wifi", "ip"),
    ),
    FraimicSensorDescription(
        key="firmware_version",
        translation_key="firmware_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("firmware_version"),
    ),
    FraimicSensorDescription(
        key="uptime",
        translation_key="uptime",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: _g(d, "device", "uptime_s"),
    ),
    FraimicSensorDescription(
        key="last_refresh",
        translation_key="last_refresh",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: _parse_timestamp(_g(d, "display", "last_refresh")),
    ),
    FraimicSensorDescription(
        key="next_refresh",
        translation_key="next_refresh",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: _parse_timestamp(_g(d, "display", "next_refresh")),
    ),
)

# Battery-health diagnostics scraped from the /info HTML page (see
# info_page.py) — data absent from every JSON endpoint. These read
# ``coordinator.info_page`` instead of the poll data and show unknown until
# the first successful scrape.
INFO_PAGE_SENSORS: tuple[FraimicSensorDescription, ...] = (
    FraimicSensorDescription(
        key="battery_cycles",
        translation_key="battery_cycles",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("battery_cycles"),
    ),
    FraimicSensorDescription(
        key="battery_soh",
        translation_key="battery_soh",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("battery_soh"),
    ),
    FraimicSensorDescription(
        key="battery_current",
        translation_key="battery_current",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.MILLIAMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.get("battery_current_ma"),
    ),
    FraimicSensorDescription(
        key="battery_temperature",
        translation_key="battery_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("battery_temperature_c"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FraimicConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Fraimic sensors from a config entry."""
    coordinator = entry.runtime_data.coordinator
    entities: list[FraimicSensor] = [
        FraimicSensor(coordinator, desc) for desc in SENSORS
    ]
    entities.extend(
        FraimicInfoPageSensor(coordinator, desc) for desc in INFO_PAGE_SENSORS
    )
    async_add_entities(entities)


class FraimicSensor(FraimicEntity, SensorEntity):
    """A single Fraimic sensor."""

    entity_description: FraimicSensorDescription

    def __init__(self, coordinator, description: FraimicSensorDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"

    @property
    def native_value(self) -> Any:
        data = self.coordinator.data
        if not isinstance(data, dict):
            return None
        return self.entity_description.value_fn(data)


class FraimicInfoPageSensor(FraimicSensor):
    """A sensor fed by the scraped /info HTML page instead of the poll data."""

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.info_page)
