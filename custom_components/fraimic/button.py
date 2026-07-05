"""Button platform for the Fraimic E-Ink Canvas."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import FraimicApiError, FraimicClient, FraimicError
from .coordinator import FraimicConfigEntry
from .entity import FraimicEntity


@dataclass(frozen=True, kw_only=True)
class FraimicButtonDescription(ButtonEntityDescription):
    """Describes a Fraimic action button."""

    press_fn: Callable[[FraimicClient], Awaitable[dict[str, Any]]]


BUTTONS: tuple[FraimicButtonDescription, ...] = (
    FraimicButtonDescription(
        key="refresh",
        translation_key="refresh",
        icon="mdi:monitor-shimmer",
        press_fn=lambda client: client.refresh(),
    ),
    FraimicButtonDescription(
        key="sleep",
        translation_key="sleep",
        icon="mdi:sleep",
        press_fn=lambda client: client.sleep(),
    ),
    FraimicButtonDescription(
        key="restart",
        translation_key="restart",
        device_class=ButtonDeviceClass.RESTART,
        press_fn=lambda client: client.restart(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FraimicConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Fraimic buttons from a config entry."""
    coordinator = entry.runtime_data.coordinator
    entities: list[ButtonEntity] = [
        FraimicButton(coordinator, desc) for desc in BUTTONS
    ]
    scheduler = entry.runtime_data.scheduler
    if scheduler is not None and scheduler.screens:
        entities += [
            FraimicPlaylistStepButton(coordinator, "next_screen", 1),
            FraimicPlaylistStepButton(coordinator, "previous_screen", -1),
        ]
    async_add_entities(entities)


class FraimicButton(FraimicEntity, ButtonEntity):
    """A single Fraimic action button."""

    entity_description: FraimicButtonDescription

    def __init__(self, coordinator, description: FraimicButtonDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"

    async def async_press(self) -> None:
        client = self.coordinator.client
        try:
            await self.entity_description.press_fn(client)
        except FraimicApiError as err:
            # e.g. POST /api/sleep is blocked while a charging cable is connected.
            raise HomeAssistantError(
                f"Fraimic rejected the {self.entity_description.key} command: "
                f"{err.error or err}"
            ) from err
        except FraimicError as err:
            raise HomeAssistantError(
                f"Could not reach the frame to {self.entity_description.key}: {err}"
            ) from err
        # Reflect the new state (e.g. uptime reset, sleeping) without waiting for
        # the next poll.
        await self.coordinator.async_request_refresh()


class FraimicPlaylistStepButton(FraimicEntity, ButtonEntity):
    """Show the next / previous stored screen immediately."""

    def __init__(self, coordinator, key: str, step: int) -> None:
        super().__init__(coordinator)
        self._attr_translation_key = key
        self._attr_icon = "mdi:skip-next" if step > 0 else "mdi:skip-previous"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{key}"
        self._step = step

    @property
    def available(self) -> bool:
        # Stepping renders locally and uploads; let the press surface a clear
        # error if the frame is asleep instead of greying the button out.
        return self.coordinator.config_entry.runtime_data.scheduler is not None

    async def async_press(self) -> None:
        scheduler = self.coordinator.config_entry.runtime_data.scheduler
        if self._step > 0:
            await scheduler.async_next()
        else:
            await scheduler.async_previous()
