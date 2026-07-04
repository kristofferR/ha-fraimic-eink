"""Image platform — shows a preview of the artwork last pushed to the frame.

The frame's API is write-only for images (there is no "get current image"
endpoint), so this entity reflects what *this integration* last uploaded. It is
empty until the first successful ``fraimic.upload_image`` call.
"""

from __future__ import annotations

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import FraimicConfigEntry
from .entity import FraimicEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FraimicConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Fraimic preview image entities."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        [FraimicPreviewImage(hass, coordinator), FraimicScreenPreviewImage(hass, coordinator)]
    )


class FraimicPreviewImage(FraimicEntity, ImageEntity):
    """Holds the most recently uploaded artwork as a PNG preview."""

    _attr_translation_key = "preview"
    _attr_content_type = "image/png"

    def __init__(self, hass: HomeAssistant, coordinator) -> None:
        FraimicEntity.__init__(self, coordinator)
        ImageEntity.__init__(self, hass)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_preview"
        self._image: bytes | None = None
        self._attr_extra_state_attributes = {}

    async def async_added_to_hass(self) -> None:
        """Expose this entity to the upload path only once it's actually added.

        Registering it earlier would let the upload service call set_preview() on
        an entity that HA never added (e.g. if the user disabled it), which would
        raise on async_write_ha_state.
        """
        await super().async_added_to_hass()
        self.coordinator.config_entry.runtime_data.preview_image = self

    async def async_will_remove_from_hass(self) -> None:
        runtime = self.coordinator.config_entry.runtime_data
        if runtime.preview_image is self:
            runtime.preview_image = None
        await super().async_will_remove_from_hass()

    @property
    def available(self) -> bool:
        # The preview is local state; it stays available even while the frame
        # sleeps so you can still see what was last shown.
        return self._image is not None

    def set_preview(self, png_bytes: bytes, mode: str | None = None) -> None:
        """Store a new PNG preview (and the dither mode used) and notify HA."""
        self._image = png_bytes
        # Surfaces what `auto` actually chose; cleared if the new preview has none
        # so a stale mode from a previous upload isn't shown.
        self._attr_extra_state_attributes = {"dither_mode": mode} if mode else {}
        self._attr_image_last_updated = dt_util.utcnow()
        self.async_write_ha_state()

    async def async_image(self) -> bytes | None:
        return self._image


class FraimicScreenPreviewImage(FraimicPreviewImage):
    """Preview of the last rendered dashboard screen.

    Unlike the main preview (what's actually on the frame), this also updates
    on ``render_screen`` calls with ``preview_only: true`` — the zero-battery
    way to iterate on a screen design without burning ~30 s e-ink refreshes.
    """

    _attr_translation_key = "screen_preview"

    def __init__(self, hass: HomeAssistant, coordinator) -> None:
        super().__init__(hass, coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_screen_preview"

    async def async_added_to_hass(self) -> None:
        # Skip FraimicPreviewImage's hook (it would overwrite the *main*
        # preview registration) and register on the screen-preview slot.
        await FraimicEntity.async_added_to_hass(self)
        self.coordinator.config_entry.runtime_data.screen_preview_image = self

    async def async_will_remove_from_hass(self) -> None:
        runtime = self.coordinator.config_entry.runtime_data
        if runtime.screen_preview_image is self:
            runtime.screen_preview_image = None
        await FraimicEntity.async_will_remove_from_hass(self)
