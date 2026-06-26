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
    """Set up the Fraimic preview image entity."""
    coordinator = entry.runtime_data.coordinator
    entity = FraimicPreviewImage(hass, coordinator)
    # Expose the entity to the upload service so it can refresh the preview.
    entry.runtime_data.preview_image = entity
    async_add_entities([entity])


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

    @property
    def available(self) -> bool:
        # The preview is local state; it stays available even while the frame
        # sleeps so you can still see what was last shown.
        return self._image is not None

    def set_preview(self, png_bytes: bytes, mode: str | None = None) -> None:
        """Store a new PNG preview (and the dither mode used) and notify HA."""
        self._image = png_bytes
        if mode is not None:
            # Surfaces what `auto` actually chose, so it's visible in the UI.
            self._attr_extra_state_attributes = {"dither_mode": mode}
        self._attr_image_last_updated = dt_util.utcnow()
        self.async_write_ha_state()

    async def async_image(self) -> bytes | None:
        return self._image
