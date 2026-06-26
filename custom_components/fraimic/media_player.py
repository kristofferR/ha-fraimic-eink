"""Media player platform — display images on the frame via HA's media browser.

Exposing each frame as a media_player lets you push artwork the native HA way:
browse any media source (local media, etc.) and click to send, or call
``media_player.play_media`` with a media-source URI or URL. The image is run
through the frame's configured conversion settings, same as the service.
"""

from __future__ import annotations

import aiohttp
from homeassistant.components import media_source
from homeassistant.components.media_player import (
    BrowseMedia,
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
    async_process_play_media_url,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import MAX_SOURCE_BYTES as MAX_DOWNLOAD_BYTES
from .coordinator import FraimicConfigEntry
from .entity import FraimicEntity
from .services import async_render_and_upload


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FraimicConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Fraimic media player."""
    async_add_entities([FraimicMediaPlayer(entry.runtime_data.coordinator)])


class FraimicMediaPlayer(FraimicEntity, MediaPlayerEntity):
    """A frame as a media player that 'plays' (displays) images."""

    _attr_name = None  # the media player IS the frame (uses the device name)
    _attr_device_class = MediaPlayerDeviceClass.RECEIVER
    _attr_media_content_type = MediaType.IMAGE
    _attr_supported_features = (
        MediaPlayerEntityFeature.PLAY_MEDIA | MediaPlayerEntityFeature.BROWSE_MEDIA
    )

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_media_player"

    @property
    def state(self) -> MediaPlayerState:
        return MediaPlayerState.IDLE

    async def async_browse_media(
        self,
        media_content_type: MediaType | str | None = None,
        media_content_id: str | None = None,
    ) -> BrowseMedia:
        """Browse media sources, showing only images."""
        return await media_source.async_browse_media(
            self.hass,
            media_content_id,
            content_filter=lambda item: item.media_content_type.startswith("image/"),
        )

    async def async_play_media(
        self, media_type: MediaType | str, media_id: str, **kwargs
    ) -> None:
        """Display an image on the frame."""
        if media_source.is_media_source_id(media_id):
            sourced = await media_source.async_resolve_media(
                self.hass, media_id, self.entity_id
            )
            media_id = sourced.url

        url = async_process_play_media_url(self.hass, media_id)
        session = async_get_clientsession(self.hass)
        try:
            resp = await session.get(url, timeout=aiohttp.ClientTimeout(total=30))
        except Exception as err:  # noqa: BLE001 - surfaced to the user
            raise HomeAssistantError(f"Could not download {url}: {err}") from err
        async with resp:
            if resp.status != 200:
                raise HomeAssistantError(f"Downloading image returned HTTP {resp.status}")
            raw = await resp.content.read(MAX_DOWNLOAD_BYTES + 1)
        if len(raw) > MAX_DOWNLOAD_BYTES:
            raise HomeAssistantError("Image is too large")

        await async_render_and_upload(self.hass, self.coordinator.config_entry, raw)
        self._attr_media_title = media_id.rsplit("/", 1)[-1]
        self.async_write_ha_state()

    async def async_get_media_image(self) -> tuple[bytes | None, str | None]:
        """Return the current artwork preview as the player's media image."""
        preview = self.coordinator.config_entry.runtime_data.last_preview
        if preview is not None:
            return preview, "image/png"
        return None, None
