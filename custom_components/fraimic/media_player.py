"""Media player platform — display images on the frame via HA's media browser.

Exposing each frame as a media_player lets you push artwork the native HA way:
browse any media source (local media, etc.) and click to send, or call
``media_player.play_media`` with a media-source URI or URL. The image is run
through the frame's configured conversion settings, same as the service.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import timedelta

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
from homeassistant.helpers.event import async_track_time_interval

from .const import CONF_CAMERA_INTERVAL, DEFAULT_CAMERA_INTERVAL
from .const import MAX_SOURCE_BYTES as MAX_DOWNLOAD_BYTES
from .coordinator import FraimicConfigEntry
from .entity import FraimicEntity
from .services import async_render_and_upload

_LOGGER = logging.getLogger(__name__)


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
        MediaPlayerEntityFeature.PLAY_MEDIA
        | MediaPlayerEntityFeature.BROWSE_MEDIA
        | MediaPlayerEntityFeature.STOP
    )

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_media_player"
        self._camera_entity: str | None = None
        self._camera_unsub = None

    @property
    def state(self) -> MediaPlayerState:
        # "Playing" while a camera is being periodically refreshed onto the
        # frame; otherwise the frame just idles on its last image.
        if self._camera_unsub is not None:
            return MediaPlayerState.PLAYING
        return MediaPlayerState.IDLE

    def _stop_camera_loop(self) -> None:
        if self._camera_unsub is not None:
            self._camera_unsub()
            self._camera_unsub = None
        self._camera_entity = None

    def _stop_camera_loop_and_write(self) -> None:
        self._stop_camera_loop()
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.coordinator.config_entry.runtime_data.stop_camera_loop = (
            self._stop_camera_loop_and_write
        )

    async def async_will_remove_from_hass(self) -> None:
        runtime = self.coordinator.config_entry.runtime_data
        if runtime.stop_camera_loop == self._stop_camera_loop_and_write:
            runtime.stop_camera_loop = None
        self._stop_camera_loop()
        await super().async_will_remove_from_hass()

    async def async_media_stop(self) -> None:
        """Stop the periodic camera refresh (the last image stays displayed)."""
        self._stop_camera_loop()
        self.async_write_ha_state()

    async def _async_show_camera(self, camera_entity: str) -> None:
        """Snapshot ``camera_entity`` and display it on the frame."""
        from homeassistant.components.camera import async_get_image

        image = await async_get_image(self.hass, camera_entity)
        await async_render_and_upload(
            self.hass, self.coordinator.config_entry, image.content
        )

    async def _async_camera_tick(self, _now) -> None:
        """Periodic camera re-snapshot; failures are logged, the loop lives on
        (the frame may simply be asleep or mid-render right now)."""
        if self._camera_entity is None:
            return
        try:
            await self._async_show_camera(self._camera_entity)
        except HomeAssistantError as err:
            _LOGGER.warning(
                "Periodic camera refresh of %s failed (will retry next cycle): %s",
                self._camera_entity,
                err,
            )

    async def async_browse_media(
        self,
        media_content_type: MediaType | str | None = None,
        media_content_id: str | None = None,
    ) -> BrowseMedia:
        """Browse media sources: images, plus cameras (snapshotted on play)."""
        return await media_source.async_browse_media(
            self.hass,
            media_content_id,
            content_filter=lambda item: (
                item.media_content_type.startswith("image/")
                or (item.media_content_id or "").startswith("media-source://camera/")
            ),
        )

    async def async_play_media(
        self, media_type: MediaType | str, media_id: str, **kwargs
    ) -> None:
        """Display an image on the frame."""
        # Playing anything replaces whatever camera loop was running.
        self._stop_camera_loop()

        # Camera media-source items resolve to *live stream* URLs (HLS/MJPEG),
        # which aren't decodable images — take a still snapshot instead, and
        # keep re-snapshotting on the frame's configured camera interval.
        if media_id.startswith("media-source://camera/") or media_id.startswith(
            "camera."
        ):
            camera_entity = media_id.rsplit("/", 1)[-1]
            interval = self.coordinator.config_entry.options.get(
                CONF_CAMERA_INTERVAL, DEFAULT_CAMERA_INTERVAL
            )
            if interval > 0:
                # Two competing periodic pushers make no sense — starting a
                # camera loop switches the screen playlist off explicitly.
                scheduler = self.coordinator.config_entry.runtime_data.scheduler
                disabled_scheduler = False
                if scheduler is not None and scheduler.enabled:
                    await scheduler.async_set_enabled(False)
                    disabled_scheduler = True
            else:
                scheduler = None
                disabled_scheduler = False
            try:
                await self._async_show_camera(camera_entity)
            except Exception:
                if disabled_scheduler and scheduler is not None:
                    await scheduler.async_set_enabled(True)
                raise
            if interval > 0:
                self._camera_entity = camera_entity
                self._camera_unsub = async_track_time_interval(
                    self.hass, self._async_camera_tick, timedelta(seconds=interval)
                )
            self._attr_media_title = camera_entity
            self.async_write_ha_state()
            return

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

    @property
    def media_image_hash(self) -> str | None:
        """Hash of the current artwork so HA refetches it when it changes."""
        preview = self.coordinator.config_entry.runtime_data.last_preview
        if preview is None:
            return None
        return hashlib.sha1(preview).hexdigest()[:16]

    async def async_get_media_image(self) -> tuple[bytes | None, str | None]:
        """Return the current artwork preview as the player's media image."""
        preview = self.coordinator.config_entry.runtime_data.last_preview
        if preview is not None:
            return preview, "image/png"
        return None, None
