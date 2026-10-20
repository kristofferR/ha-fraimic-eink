"""Per-frame cloud delivery: Home Assistant-owned albums on the account.

Every rendered image becomes a palette PNG in the account gallery and the
art album's single image. The album's interval schedule wakes the sleeping
frame for each slot, so keep-awake stays off and the LAN is never needed.

Planned wakes (awake windows) use a second, empty album. Any edit to an album
with an image redraws an awake frame, but an empty album only sets the frame's
wake timer, so its schedule can change at any time. See
``docs/fraimic-cloud-api/albums-scheduling.md`` for the verified behaviour.
"""

from __future__ import annotations

import base64
import binascii
import logging
import time
from datetime import UTC, datetime
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .cloud import (
    FraimicCloudClient,
    FraimicCloudError,
    album_interval_minutes,
    cloud_timestamp,
    schedule_for_minutes,
    steered_minutes,
)
from .const import (
    CLOUD_SLOT_LEAD_MINUTES,
    CLOUD_WAKE_WINDOW,
    CONF_HEIGHT,
    CONF_CLOUD_EMAIL,
    CONF_ROTATION,
    CONF_WIDTH,
    DEFAULT_HEIGHT,
    DEFAULT_ROTATION,
    DEFAULT_WIDTH,
    DOMAIN,
)
from .image_convert import indices_to_cloud_png, bin_to_indices, bin_to_png

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
        self.album_active = False
        # A planned wake, carried by the empty wake album; art slots are
        # steered onto it (see ``steered_minutes``). Also the interval the
        # last art edit actually used.
        self.wake_at: float | None = None
        self.wake_album_id: str | None = None
        self.slot_minutes: int | None = None
        self.preview_png: bytes | None = None
        self.preview_title: str | None = None

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
        self.album_active = data.get("album_active", self.album_id is not None)
        wake_at = data.get("wake_at")
        self.wake_at = float(wake_at) if isinstance(wake_at, int | float) else None
        self.wake_album_id = data.get("wake_album_id") or None
        slot_minutes = data.get("slot_minutes")
        self.slot_minutes = slot_minutes if isinstance(slot_minutes, int) and slot_minutes > 0 else None
        try:
            self.preview_png = base64.b64decode(data.get("preview_png") or "", validate=True) or None
        except (ValueError, TypeError, binascii.Error):
            self.preview_png = None
        self.preview_title = data.get("preview_title")

    async def _async_save(self) -> None:
        await self._store.async_save(
            {
                "album_id": self.album_id,
                "album_device_id": self.album_device_id,
                "upload_id": self.upload_id,
                "interval": self.interval,
                "keep_awake_released": self.keep_awake_released,
                "last_anchor": self.last_anchor,
                "album_active": self.album_active,
                "wake_at": self.wake_at,
                "wake_album_id": self.wake_album_id,
                "slot_minutes": self.slot_minutes,
                "preview_png": base64.b64encode(self.preview_png).decode("ascii") if self.preview_png else None,
                "preview_title": self.preview_title,
            }
        )

    @property
    def has_image(self) -> bool:
        """Whether the album already carries an image (frame has a wake slot)."""
        return self.album_active and self.album_id is not None and self.upload_id is not None

    @property
    def holds_account_state(self) -> bool:
        """Whether leaving cloud delivery has anything on the account to undo."""
        return (
            self.album_id is not None
            or self.wake_album_id is not None
            or self.keep_awake_released
        )

    @property
    def wake_interval(self) -> int:
        """Seconds from an album edit made now to the slot that serves it."""
        return self._edit_minutes() * 60

    def _rotating(self) -> bool:
        """Whether the scheduler is producing new art right now."""
        scheduler = getattr(getattr(self.entry, "runtime_data", None), "scheduler", None)
        return bool(getattr(scheduler, "producing", False))

    def _edit_minutes(self, interval: int | None = None) -> int:
        minutes = album_interval_minutes(self.interval if interval is None else interval)
        # Slots before a planned wake each redraw the album image, which only
        # pays off when every one brings new art.
        return steered_minutes(
            time.time(), minutes, self.wake_at, cap=None if self._rotating() else 1440
        )

    @property
    def delivery_deadline(self) -> float | None:
        """End of the current image's wake window, without inferring a redraw."""
        if not self.album_active or not self.last_anchor:
            return None
        minutes = self.slot_minutes or album_interval_minutes(self.interval)
        try:
            return cloud_timestamp(self.last_anchor) + minutes * 60 + CLOUD_WAKE_WINDOW
        except ValueError:
            return None

    def _set_anchor(self, album: dict[str, Any], minutes: int) -> None:
        self.last_anchor = (
            album.get("updated_at") or album.get("created_at")
            or datetime.now(UTC).isoformat()
        )
        self.slot_minutes = minutes

    async def async_expire_delivery(self) -> None:
        """Retire each image after its slot so an idle producer cannot repeat it.

        A planned wake does not need it: the empty wake album carries that.
        """
        deadline = self.delivery_deadline
        if deadline is None or self.album_id is None or time.time() < deadline:
            return
        await self.client.async_update_album(self.album_id, {"active": False})
        self.album_active = False
        await self._async_save()

    async def async_cancel_delivery(self) -> None:
        """Retire a pending album before Hybrid replaces it over the LAN.

        Keep account ownership and keep-awake unchanged so future cloud sends
        can reuse the album and the frame can still sleep between deliveries.
        """
        if self.album_id is None or not self.album_active:
            return
        try:
            await self.client.async_update_album(self.album_id, {"active": False})
        except FraimicCloudError as err:
            if err.status != 404:
                raise
        self.album_active = False
        await self._async_save()

    @property
    def album_name(self) -> str:
        return f"Home Assistant: {self.entry.title}"

    # ------------------------------------------------------------ delivery

    async def async_deliver(
        self, bin_data: bytes, *, title: str, preview_png: bytes | None = None
    ) -> None:
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
        minutes = self._edit_minutes()
        try:
            album = await self._async_point_album(upload_id, minutes)
        except FraimicCloudError:
            # Do not leave an orphan in the gallery.
            await self._async_discard(upload_id)
            raise
        self.upload_id = upload_id
        self.preview_png = preview_png or await self.hass.async_add_executor_job(
            bin_to_png, bin_data, width, height, rotation
        )
        self.preview_title = title
        self._set_anchor(album, minutes)
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
        await self._async_align_wake(minutes)

    async def _async_point_album(self, upload_id: str, minutes: int) -> dict[str, Any]:
        schedule = schedule_for_minutes(minutes)
        if self.album_id is not None:
            payload: dict[str, Any] = {
                "upload_ids": [upload_id], "active": True, "schedule": schedule,
            }
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
                self.album_active = True
                return album
        album = await self.client.async_create_album(
            {
                "name": self.album_name,
                "description": "Managed by Home Assistant. Edits here are overwritten.",
                "active": True,
                "device_assignments": [{"device_id": self.device_id}],
                "schedule": schedule,
                "playback_mode": "sequential",
                "upload_ids": [upload_id],
            }
        )
        self.album_id = str(album["id"])
        self.album_device_id = self.device_id
        self.album_active = True
        return album

    async def _async_discard(self, upload_id: str) -> None:
        try:
            await self.client.async_delete_uploads([upload_id])
        except FraimicCloudError as err:
            _LOGGER.debug("Could not delete cloud upload %s: %s", upload_id, err)

    async def async_set_keep_awake(self, on: bool) -> None:
        """Awake windows own keep-awake from now on.

        Marking it released stops the first cloud delivery from turning it
        off in the middle of a window.
        """
        await self.client.async_set_keep_awake(self.device_id, on)
        if not self.keep_awake_released:
            self.keep_awake_released = True
            await self._async_save()

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
        minutes = self._edit_minutes(interval)
        try:
            album = await self.client.async_update_album(
                self.album_id, {"schedule": schedule_for_minutes(minutes)}
            )
        except FraimicCloudError as err:
            # Keep the old interval so the next sync retries the update.
            _LOGGER.warning("Could not update the cloud album schedule: %s", err)
            return
        self._set_anchor(album, minutes)
        try:
            await self._async_align_wake(minutes)
        except FraimicCloudError as err:
            # Keep the old interval so the next sync retries both edits.
            _LOGGER.warning("Could not align the wake album with the cloud album: %s", err)
            await self._async_save()
            return
        self.interval = interval
        await self._async_save()

    async def async_plan_wake(self, wake_at: float | None) -> None:
        """Keep a slot at ``wake_at`` on the wake album; None removes the album.

        Re-anchoring also turns a slot the frame already learned into a short
        check wake, which is how a sleeping frame picks up a changed plan. The
        album has no image, so this never redraws the frame, even an awake one.
        A failed cloud call leaves the previous plan in place.
        """
        previous = self.wake_at
        self.wake_at = wake_at
        try:
            if wake_at is None:
                await self._async_drop_wake_album()
            else:
                await self._async_point_wake_album(self._edit_minutes())
        except BaseException:
            self.wake_at = previous
            raise
        await self._async_save()

    @property
    def wake_album_name(self) -> str:
        return f"Home Assistant wake: {self.entry.title}"

    async def _async_point_wake_album(self, minutes: int) -> None:
        payload: dict[str, Any] = {
            "active": True,
            "schedule": schedule_for_minutes(minutes),
            "device_assignments": [{"device_id": self.device_id}],
            # Edits keep other fields, so drop any image added in the app.
            "upload_ids": [],
        }
        if self.wake_album_id is not None:
            try:
                await self.client.async_update_album(self.wake_album_id, payload)
                return
            except FraimicCloudError as err:
                if err.status != 404:
                    raise
                _LOGGER.info("Wake album %s is gone; creating a new one", self.wake_album_id)
        album = await self.client.async_create_album(
            {
                "name": self.wake_album_name,
                "description": "Managed by Home Assistant. Wakes the frame; never shows a picture.",
                "playback_mode": "sequential",
                **payload,
            }
        )
        self.wake_album_id = str(album["id"])

    async def _async_align_wake(self, minutes: int) -> None:
        """Give a sleeping frame a wake at the art album's first slot.

        Both albums then share one grid. The art album retires after that
        slot, so a failure here fails the delivery: the frame could sleep
        through the slot and never show the image.
        """
        if self.wake_at is None or self.wake_at - time.time() < CLOUD_SLOT_LEAD_MINUTES * 60:
            # Too close to steer: the planned wake comes first and stays.
            return
        await self._async_point_wake_album(minutes)
        await self._async_save()

    async def _async_drop_wake_album(self) -> None:
        if self.wake_album_id is None:
            return
        try:
            await self.client.async_delete_album(self.wake_album_id)
        except FraimicCloudError as err:
            if err.status != 404:
                raise
        self.wake_album_id = None

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
                self.album_active = False
            except FraimicCloudError as err:
                _LOGGER.warning("Could not deactivate the cloud album: %s", err)
                ok = err.status == 404
        try:
            await self._async_drop_wake_album()
        except FraimicCloudError as err:
            _LOGGER.warning("Could not delete the wake album: %s", err)
            ok = False
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

    async def async_clear_preview(self) -> None:
        """A newer local upload supersedes the last cloud-submitted preview."""
        self.preview_png = None
        self.preview_title = None
        await self._async_save()

    async def async_forget_album(self) -> None:
        """Drop the stored album so a later switch to cloud starts clean."""
        self.album_id = None
        self.preview_png = None
        self.preview_title = None
        self.album_device_id = None
        self.upload_id = None
        self.album_active = False
        self.wake_at = None
        self.wake_album_id = None
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
            "slot_minutes": self.slot_minutes,
            "wake_at": self.wake_at,
            "wake_album_id": self.wake_album_id,
            "keep_awake_released": self.keep_awake_released,
            "last_anchor": self.last_anchor,
            "album_active": self.album_active,
        }


async def async_release_for_account_change(hass, entry, email: str) -> bool:
    """Retire ownership with the old credentials before saving another account."""
    old_email = entry.options.get(CONF_CLOUD_EMAIL, "")
    if not old_email or old_email.strip().casefold() == email.strip().casefold():
        return True
    runtime = getattr(entry, "runtime_data", None)
    delivery = getattr(runtime, "cloud", None)
    if delivery is None:
        from . import _async_load_cloud

        delivery = await _async_load_cloud(hass, entry)
    if delivery is None:
        return True

    async def release() -> bool:
        if not await delivery.async_release():
            return False
        await delivery.async_forget_album()
        return True

    lock = getattr(runtime, "upload_lock", None)
    if lock is not None:
        async with lock:
            return await release()
    return await release()


def cloud_device_snapshot(
    device: dict[str, Any], previous: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Shape a cloud device record like the frame's ``/api/info`` payload.

    Used when the frame sleeps and the LAN poll fails: the coordinator can
    still surface battery, network and settings without the frame answering.
    """
    settings = device.get("settings") or {}
    snapshot = {
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
    previous = previous or {}
    for key in ("device_id", "device_key", "model", "firmware_version"):
        if snapshot.get(key) is None:
            snapshot[key] = previous.get(key)
    display = previous.get("display") or {}
    snapshot["display"] = {key: display.get(key) for key in ("width", "height")}
    return snapshot
