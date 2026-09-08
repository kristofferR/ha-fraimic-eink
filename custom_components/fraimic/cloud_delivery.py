"""Per-frame cloud delivery: one Home Assistant-owned album on the account.

Every rendered image becomes a palette PNG in the account gallery and the
album's single image. The album's interval schedule wakes the sleeping frame
for each slot, so keep-awake stays off and the LAN is never needed. See
``docs/fraimic-cloud-api/albums-scheduling.md`` for the verified behaviour.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .cloud import (
    FraimicCloudClient,
    FraimicCloudError,
    album_interval_minutes,
    album_schedule,
)
from .const import (
    CONF_HEIGHT,
    CONF_ROTATION,
    CONF_WIDTH,
    DEFAULT_HEIGHT,
    DEFAULT_ROTATION,
    DEFAULT_WIDTH,
    DOMAIN,
)
from .image_convert import indices_to_cloud_png, bin_to_indices

_LOGGER = logging.getLogger(__name__)

STORE_VERSION = 1
# Fallback rotation cadence for the album before a playlist interval is known.
DEFAULT_INTERVAL = 3600


def _cloud_png(bin_data: bytes, width: int, height: int, rotation: int) -> bytes:
    return indices_to_cloud_png(bin_to_indices(bin_data, width, height), width, height, rotation)


class FraimicCloudDelivery:
    """Keeps the frame's album pointed at the latest rendered image."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry,
        client: FraimicCloudClient,
        device_id: str,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.client = client
        self.device_id = device_id
        self._store: Store[dict[str, Any]] = Store(
            hass, STORE_VERSION, f"{DOMAIN}_cloud_{entry.entry_id}"
        )
        self.album_id: str | None = None
        # Canvas the album is assigned to; differs from ``device_id`` after the
        # user picks another canvas, until the next delivery reassigns it.
        self.album_device_id: str | None = None
        self.upload_id: str | None = None
        self.interval = DEFAULT_INTERVAL
        self.camera_interval: int | None = None
        # True once the frame has been told to stop keeping awake: done after
        # the first delivery so the (still awake) frame learns the album slot
        # before it is allowed to sleep.
        self.keep_awake_released = False
        self.last_anchor: str | None = None

    async def async_setup(self) -> None:
        data = await self._store.async_load() or {}
        self.album_id = data.get("album_id") or None
        self.album_device_id = data.get("album_device_id") or None
        self.upload_id = data.get("upload_id") or None
        interval = data.get("interval")
        if isinstance(interval, int) and interval > 0:
            self.interval = interval
        self.keep_awake_released = data.get("keep_awake_released") is True
        self.last_anchor = data.get("last_anchor") or None

    async def _async_save(self) -> None:
        await self._store.async_save(
            {
                "album_id": self.album_id,
                "album_device_id": self.album_device_id,
                "upload_id": self.upload_id,
                "interval": self.interval,
                "keep_awake_released": self.keep_awake_released,
                "last_anchor": self.last_anchor,
            }
        )

    @property
    def has_image(self) -> bool:
        """Whether the album already carries an image (frame has a wake slot)."""
        return self.album_id is not None and self.upload_id is not None

    @property
    def album_name(self) -> str:
        return f"Home Assistant: {self.entry.title}"

    # ------------------------------------------------------------ delivery

    async def async_deliver(self, bin_data: bytes, *, title: str) -> None:
        """Upload ``bin_data`` as a PNG and make it the album's image."""
        width = self.entry.data.get(CONF_WIDTH, DEFAULT_WIDTH)
        height = self.entry.data.get(CONF_HEIGHT, DEFAULT_HEIGHT)
        # The base rotation turns the *source* clockwise into the native
        # buffer, so the wall view is the native buffer turned back the other
        # way (same convention as the dashboard preview).
        rotation = (-self.entry.options.get(CONF_ROTATION, DEFAULT_ROTATION)) % 360
        png = await self.hass.async_add_executor_job(
            _cloud_png, bin_data, width, height, rotation
        )
        upload_id = await self.client.async_upload_png(png)
        previous = self.upload_id
        try:
            album = await self._async_point_album(upload_id)
        except FraimicCloudError:
            # Do not leave an orphan in the gallery.
            await self._async_discard(upload_id)
            raise
        self.upload_id = upload_id
        self.last_anchor = album.get("updated_at") or album.get("created_at")
        await self._async_save()
        _LOGGER.debug(
            "Cloud delivery of %r queued on album %s; frame wakes about %s min after %s",
            title,
            self.album_id,
            album_interval_minutes(self.interval),
            self.last_anchor,
        )
        if previous and previous != upload_id:
            await self._async_discard(previous)
        if not self.keep_awake_released:
            await self._async_release_keep_awake()

    async def _async_point_album(self, upload_id: str) -> dict[str, Any]:
        if self.album_id is not None:
            payload: dict[str, Any] = {"upload_ids": [upload_id]}
            if self.album_device_id != self.device_id:
                if self.keep_awake_released and self.album_device_id:
                    await self.client.async_set_keep_awake(self.album_device_id, True)
                self.keep_awake_released = False
                await self._async_save()
                payload["device_assignments"] = [{"device_id": self.device_id}]
            try:
                album = await self.client.async_update_album(self.album_id, payload)
            except FraimicCloudError as err:
                if err.status != 404:
                    raise
                _LOGGER.info("Cloud album %s is gone; creating a new one", self.album_id)
                self.album_id = None
            else:
                self.album_device_id = self.device_id
                return album
        album = await self.client.async_create_album(
            {
                "name": self.album_name,
                "description": "Managed by Home Assistant. Edits here are overwritten.",
                "active": True,
                "device_assignments": [{"device_id": self.device_id}],
                "schedule": album_schedule(self.interval),
                "playback_mode": "sequential",
                "upload_ids": [upload_id],
            }
        )
        self.album_id = str(album["id"])
        self.album_device_id = self.device_id
        return album

    async def _async_discard(self, upload_id: str) -> None:
        try:
            await self.client.async_delete_uploads([upload_id])
        except FraimicCloudError as err:
            _LOGGER.debug("Could not delete cloud upload %s: %s", upload_id, err)

    async def _async_release_keep_awake(self) -> None:
        try:
            await self.client.async_set_keep_awake(self.device_id, False)
        except FraimicCloudError as err:
            _LOGGER.warning("Could not turn keep-awake off in the Fraimic cloud: %s", err)
            return
        self.keep_awake_released = True
        await self._async_save()
        _LOGGER.info(
            "Keep-awake turned off for %s; the frame now wakes for album slots only",
            self.entry.title,
        )

    # ------------------------------------------------------------ schedule

    async def async_sync_interval(self, playlist_interval: int | None) -> None:
        """Keep the album cadence equal to the playlist rotation."""
        interval = self.camera_interval or playlist_interval or DEFAULT_INTERVAL
        if interval == self.interval and self.album_id is not None:
            return
        changed = album_interval_minutes(interval) != album_interval_minutes(self.interval)
        if self.album_id is None or not changed:
            self.interval = interval
            await self._async_save()
            return
        try:
            album = await self.client.async_update_album(
                self.album_id, {"schedule": album_schedule(interval)}
            )
        except FraimicCloudError as err:
            # Keep the old interval so the next sync retries the update.
            _LOGGER.warning("Could not update the cloud album schedule: %s", err)
            return
        self.interval = interval
        self.last_anchor = album.get("updated_at") or self.last_anchor
        await self._async_save()

    # ------------------------------------------------------------ teardown

    async def async_remove(self) -> None:
        """Release a deleted entry; retain ownership and a repair notice on failure."""
        from homeassistant.helpers import issue_registry as ir

        issue_id = f"cloud_cleanup_{self.entry.entry_id}"
        if await self.async_release():
            await self.async_forget_album()
            await self._store.async_remove()
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)
            return
        # HA removes the entry even when its removal hook raises. Keep the
        # album IDs in storage and make the required account cleanup visible.
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            is_persistent=True,
            severity=ir.IssueSeverity.WARNING,
            translation_key="cloud_cleanup",
            translation_placeholders={
                "frame": self.entry.title,
                "album": self.album_id or self.album_name,
                "device": self.album_device_id or self.device_id,
            },
        )

    async def async_release(self) -> bool:
        """Hand the frame back to local delivery: keep-awake on, album off.

        Returns whether everything succeeded; on failure the state is kept so
        the next entry setup retries.
        """
        ok = True
        if self.album_id is not None:
            try:
                await self.client.async_update_album(self.album_id, {"active": False})
            except FraimicCloudError as err:
                _LOGGER.warning("Could not deactivate the cloud album: %s", err)
                ok = err.status == 404
        if self.keep_awake_released:
            try:
                await self.client.async_set_keep_awake(
                    self.album_device_id or self.device_id, True
                )
            except FraimicCloudError as err:
                _LOGGER.warning("Could not turn keep-awake back on: %s", err)
                ok = False
            else:
                self.keep_awake_released = False
        await self._async_save()
        return ok

    async def async_forget_album(self) -> None:
        """Drop the stored album so a later switch to cloud starts clean."""
        self.album_id = None
        self.album_device_id = None
        self.upload_id = None
        await self._async_save()

    # ------------------------------------------------------------ status

    async def async_device(self) -> dict[str, Any] | None:
        """The account's record of this frame (battery, last seen, settings)."""
        return await self.client.async_device(self.device_id)

    def diagnostics(self) -> dict[str, Any]:
        return {
            "album_id": self.album_id,
            "album_device_id": self.album_device_id,
            "upload_id": self.upload_id,
            "interval": self.interval,
            "album_interval_minutes": album_interval_minutes(self.interval),
            "keep_awake_released": self.keep_awake_released,
            "last_anchor": self.last_anchor,
        }


def cloud_device_snapshot(device: dict[str, Any]) -> dict[str, Any]:
    """Shape a cloud device record like the frame's ``/api/info`` payload.

    Used when the frame sleeps and the LAN poll fails: the coordinator can
    still surface battery, network and settings without the frame answering.
    """
    settings = device.get("settings") or {}
    return {
        "firmware_version": None,
        "display_type": device.get("display_type"),
        "wifi": {
            "ssid": device.get("wifi_ssid"),
            "ip": device.get("ip_address"),
        },
        "battery": {"percent": device.get("battery_pct")},
        "settings": {
            "voice_recording": settings.get("voiceRecordingEnabled"),
            "keep_awake": settings.get("keepAwakeEnabled"),
            "charging_led": settings.get("chargingLedEnabled"),
        },
        "device": {"registered": True, "cloud_last_seen": device.get("last_seen_at")},
    }
