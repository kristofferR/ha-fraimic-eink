"""Switch platform — playlist on/off."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import FraimicConfigEntry
from .entity import FraimicEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FraimicConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the playlist switch (only when the frame has stored screens)."""
    runtime = entry.runtime_data
    if runtime.scheduler is None or not runtime.scheduler.screens:
        return
    async_add_entities([FraimicPlaylistSwitch(runtime.coordinator)])


class FraimicPlaylistSwitch(FraimicEntity, SwitchEntity):
    """Enables the playlist: stored screens rotate on the frame."""

    _attr_translation_key = "playlist"
    _attr_icon = "mdi:playlist-play"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_playlist"

    @property
    def _scheduler(self):
        return self.coordinator.config_entry.runtime_data.scheduler

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._scheduler.async_add_listener(self.async_write_ha_state))

    @property
    def available(self) -> bool:
        # Playlist state is local; it must stay controllable while the frame
        # sleeps (the scheduler pushes as soon as it wakes).
        return self._scheduler is not None

    @property
    def is_on(self) -> bool:
        return self._scheduler.enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        stopper = self.coordinator.config_entry.runtime_data.stop_camera_loop
        if stopper is not None:
            stopper()
        await self._scheduler.async_set_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._scheduler.async_set_enabled(False)
