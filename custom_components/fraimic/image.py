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


def _register_preview_slot(entity: FraimicPreviewImage) -> None:
    setattr(
        entity.coordinator.config_entry.runtime_data,
        entity._runtime_preview_slot,
        entity,
    )


def _clear_preview_slot(entity: FraimicPreviewImage) -> None:
    runtime = entity.coordinator.config_entry.runtime_data
    if getattr(runtime, entity._runtime_preview_slot) is entity:
        setattr(runtime, entity._runtime_preview_slot, None)


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
    _runtime_preview_slot = "preview_image"

    def __init__(self, hass: HomeAssistant, coordinator) -> None:
        FraimicEntity.__init__(self, coordinator)
        ImageEntity.__init__(self, hass)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_preview"
        self._image: bytes | None = None
        self._mode: str | None = None

    async def async_added_to_hass(self) -> None:
        """Expose this entity to the upload path only once it's actually added.

        Registering it earlier would let the upload service call set_preview() on
        an entity that HA never added (e.g. if the user disabled it), which would
            raise on async_write_ha_state.
        """
        await super().async_added_to_hass()
        _register_preview_slot(self)

    async def async_will_remove_from_hass(self) -> None:
        _clear_preview_slot(self)
        await super().async_will_remove_from_hass()

    @property
    def available(self) -> bool:
        # The preview is local state; it stays available even while the frame
        # sleeps so you can still see what was last shown.
        return self._image is not None

    def set_preview(self, png_bytes: bytes, mode: str | None = None) -> None:
        """Store a new PNG preview (and the dither mode used) and notify HA."""
        self._image = png_bytes
        self._mode = mode
        self._attr_image_last_updated = dt_util.utcnow()
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict:
        """Dither mode used, plus attribution when online artwork is showing.

        Read live so the coordinator-refresh state write that follows every
        upload picks up ``runtime.last_art`` (set just after the preview).
        """
        attrs: dict = {"dither_mode": self._mode} if self._mode else {}
        art = self.coordinator.config_entry.runtime_data.last_art
        if art:
            attrs.update(
                {
                    key: art[key]
                    for key in ("provider", "title", "artist", "license", "attribution")
                    if art.get(key)
                }
            )
        return attrs

    async def async_image(self) -> bytes | None:
        return self._image


class FraimicScreenPreviewImage(FraimicPreviewImage):
    """Preview of the last rendered dashboard screen.

    Unlike the main preview (what's actually on the frame), this also updates
    on ``render_screen`` calls with ``preview_only: true`` — the zero-battery
    way to iterate on a screen design without burning ~30 s e-ink refreshes.
    """

    _attr_translation_key = "screen_preview"
    _runtime_preview_slot = "screen_preview_image"

    def __init__(self, hass: HomeAssistant, coordinator) -> None:
        super().__init__(hass, coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_screen_preview"

    @property
    def extra_state_attributes(self) -> dict:
        """Screen previews are design artifacts, not displayed artwork."""
        return {"dither_mode": self._mode} if self._mode else {}
