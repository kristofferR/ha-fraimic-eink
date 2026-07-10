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
    entities += [
        FraimicNewArtworkButton(coordinator),
        FraimicDataRefreshButton(coordinator),
        FraimicTryQueuedSendButton(coordinator),
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


class FraimicDataRefreshButton(FraimicEntity, ButtonEntity):
    """Explicitly refresh normal and otherwise-on-demand frame metadata."""

    _attr_translation_key = "refresh_data"
    _attr_icon = "mdi:database-refresh"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_refresh_data"

    @property
    def available(self) -> bool:
        return True

    async def async_press(self) -> None:
        await self.coordinator.async_request_refresh()
        if not self.coordinator.last_update_success:
            raise HomeAssistantError("The frame is asleep or unreachable")
        await self.coordinator.async_refresh_info_page()
        await self.coordinator.async_refresh_albums()


class FraimicTryQueuedSendButton(FraimicEntity, ButtonEntity):
    """Try a persisted queued send after the user wakes the frame."""

    _attr_translation_key = "try_queued_send"
    _attr_icon = "mdi:send-clock"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_try_queued_send"

    @property
    def available(self) -> bool:
        return self.coordinator.config_entry.runtime_data.send_queue is not None

    async def async_press(self) -> None:
        await self.coordinator.config_entry.runtime_data.send_queue.async_try_send()


class FraimicNewArtworkButton(FraimicEntity, ButtonEntity):
    """Fetch and display a fresh online artwork (default provider option)."""

    _attr_translation_key = "new_artwork"
    _attr_icon = "mdi:palette"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_new_artwork"

    async def async_press(self) -> None:
        from .const import CONF_DEFAULT_PROVIDER, PROVIDER_SHUFFLE
        from .render.display import async_show_screen
        from .render.schema import SCREEN_SCHEMA, screen_from_dict

        entry = self.coordinator.config_entry
        provider = entry.options.get(CONF_DEFAULT_PROVIDER, PROVIDER_SHUFFLE)
        stopper = entry.runtime_data.stop_camera_loop
        if stopper is not None:
            stopper()
        screen = screen_from_dict(
            SCREEN_SCHEMA(
                {
                    "name": "Online image",
                    "kind": "picture",
                    "provider": provider,
                    "caption": True,
                }
            )
        )
        await async_show_screen(self.hass, entry, screen)


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
        scheduler.raise_if_upload_active()
        stopper = self.coordinator.config_entry.runtime_data.stop_camera_loop
        if stopper is not None:
            stopper()
        if self._step > 0:
            await scheduler.async_next()
        else:
            await scheduler.async_previous()
