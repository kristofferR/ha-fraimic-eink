"""Select platform — show a specific stored screen now."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import FraimicConfigEntry
from .entity import FraimicEntity
from .render.schema import ScreenConfig
from .scheduler import FraimicScheduler


def _option(screen: ScreenConfig) -> str:
    return f"{screen.name} ({screen.screen_id})"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FraimicConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the screen select so later playlist assignments appear live."""
    runtime = entry.runtime_data
    if runtime.scheduler is None:
        return
    async_add_entities([FraimicScreenSelect(runtime.coordinator)])


class FraimicScreenSelect(FraimicEntity, SelectEntity):
    """Selecting a screen renders it immediately and pins rotation to it."""

    _attr_translation_key = "screen"
    _attr_icon = "mdi:view-dashboard"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_screen"

    @property
    def _scheduler(self) -> FraimicScheduler | None:
        return self.coordinator.config_entry.runtime_data.scheduler

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        scheduler = self._scheduler
        if scheduler is not None:
            self.async_on_remove(scheduler.async_add_listener(self.async_write_ha_state))

    @property
    def available(self) -> bool:
        return self._scheduler is not None

    @property
    def options(self) -> list[str]:
        scheduler = self._scheduler
        return [_option(screen) for screen in scheduler.screens] if scheduler else []

    @property
    def current_option(self) -> str | None:
        scheduler = self._scheduler
        current = scheduler.current_screen if scheduler else None
        return _option(current) if current else None

    async def async_select_option(self, option: str) -> None:
        scheduler = self._scheduler
        if scheduler is None:
            raise HomeAssistantError("The playlist scheduler is not loaded")
        for screen in scheduler.screens:
            if _option(screen) == option:
                scheduler.raise_if_upload_active()
                stopper = self.coordinator.config_entry.runtime_data.stop_camera_loop
                if stopper is not None:
                    stopper()
                await scheduler.async_select(screen)
                return
        raise HomeAssistantError(f"No stored screen option {option!r}")
