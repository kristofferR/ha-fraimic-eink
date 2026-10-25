"""Data update coordinator for the Fraimic E-Ink Canvas."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    FraimicClient,
    FraimicConnectionError,
    FraimicError,
    firmware_supports_api_image,
)
from .cloud import cloud_timestamp
from .const import DOMAIN
from .info_page import parse_info_page

_LOGGER = logging.getLogger(__name__)

# IP-change rediscovery: after this many consecutive failed polls the frame is
# considered missing (not just mid-wake), and the local /24 may be scanned for
# a device answering /api/info with this entry's device_key. Deep sleep also
# looks like consecutive failures, so scans are rate-limited hard — a sleeping
# frame costs one ~15 s LAN sweep per interval, a moved frame recovers within
# one interval of waking at its new address.
REDISCOVERY_FAIL_THRESHOLD = 3
REDISCOVERY_MIN_INTERVAL = 3600  # seconds between subnet scans
REDISCOVERY_PROBE_TIMEOUT = 2.0  # per-host /api/info probe
# Minimum power mode never polls by itself. Someone looking at the dashboard
# gets at most one liveness probe per this many seconds instead.
DASHBOARD_PROBE_MAX_AGE = 300
# Reuse the account's device record this long between failed LAN polls.
CLOUD_SNAPSHOT_TTL = 300
# Entities keep their last-known values while the frame sleeps and only go
# unavailable after this long without any confirmed contact.
UNAVAILABLE_AFTER = 72 * 3600

CACHE_VERSION = 1
# Contact seen outside a poll (uploads, commands) is batched into one cache
# write; Store flushes pending delayed saves when Home Assistant stops.
CONTACT_SAVE_DELAY = 60
# How often a non-polling cloud frame past its window re-asks the account.
CLOUD_CHECK_IN_RETRY = 1800
# A reported charging cable while the battery keeps falling (seen once on a
# Large: about 35-40 mA drain, sleep refused). Conservative thresholds; the
# gauge plateaus at 95-100 % while plugged in, so only lower readings count.
CABLE_DRAIN_POINTS = 5
CABLE_DRAIN_SECONDS = 6 * 3600
CABLE_DRAIN_PLATEAU = 95
# Without internet time the frame fails over between access points, opens an
# unprotected setup AP and falls back to 24-hour timer wakes. Report it once
# the clock is still unsynced this long after boot, on consecutive polls.
UNSYNCED_UPTIME = 300
UNSYNCED_POLLS = 2
AP_SWITCH_WINDOW = 24 * 3600

type FraimicConfigEntry = ConfigEntry[FraimicRuntimeData]


class FraimicRuntimeData:
    """Objects shared across the integration's platforms."""

    def __init__(
        self, coordinator: FraimicDataUpdateCoordinator, client: FraimicClient
    ) -> None:
        self.coordinator = coordinator
        self.client = client
        # Set by the image platform once its preview entity is created, so the
        # upload service can refresh the on-dashboard preview.
        self.preview_image: Any = None
        # Ditto for the dashboard-screen preview entity (render_screen output,
        # including preview-only renders that never reach the frame).
        self.screen_preview_image: Any = None
        # Most recently rendered preview, including preview-only/deferred work.
        self.last_preview: bytes | None = None
        # Preview known (or accepted-with-timeout) to be on the frame. Player
        # artwork must use this so deferred renders never replace the glass.
        self.displayed_preview: bytes | None = None
        # Cache-buster for the fixed player-artwork URL. Incrementing on every
        # accepted preview keeps the now-playing thumbnail in lockstep with the
        # panel even when the browser retains an older signed URL in memory.
        self.displayed_preview_version = 0
        # Artwork currently being submitted, separate from the confirmed display.
        self.sending_preview: tuple[bytes, str] | None = None
        # Playlist scheduler (set during entry setup; None until then).
        self.scheduler: Any = None
        # Queued-send manager (send_queue.FraimicSendQueue; set during setup).
        self.send_queue: Any = None
        # Battery policy / redraw accounting (set during entry setup).
        self.power: Any = None
        # Cloud delivery (cloud_delivery.FraimicCloudDelivery) when the frame's
        # delivery mode is ``cloud`` or ``hybrid``; None for local-only delivery.
        self.cloud: Any = None
        # Stock-protocol companion. It serves pull assets, never LAN uploads.
        self.backend: Any = None
        # Serialize uploads; the frame can only process one long refresh.
        self.upload_lock = asyncio.Lock()
        # Incremented per send; a send that waited for a render and sees a
        # newer number drops out so the newest content wins.
        self.send_seq = 0
        # Set by the media player so enabling playlists can stop camera loops.
        self.stop_camera_loop: Any = None
        # Attribution info for online artwork currently on the frame
        # (asdict of providers.base.ArtCandidate), or None.
        self.last_art: dict[str, Any] | None = None
        # Fallback media-player title for non-provider content currently on the frame.
        self.media_title: str | None = None
        # Count of frame-owned overlays in the last composed picture.
        self.last_overlay_count = 0
        self.temporary_overlays: Any = None
        # Planned awake windows (awake_window.AwakeWindow) for Hybrid frames.
        self.awake_window: Any = None

    def set_displayed_preview(
        self, preview_png: bytes, mode: str, *, overlay_count: int = 0
    ) -> None:
        """Keep every representation of the preview on the glass in sync."""
        self.last_preview = preview_png
        self.displayed_preview = preview_png
        self.displayed_preview_version += 1
        self.last_overlay_count = overlay_count
        if self.preview_image is not None:
            self.preview_image.set_preview(preview_png, mode)


class FraimicDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls ``/api/info`` and exposes the latest device snapshot."""

    config_entry: FraimicConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: FraimicConfigEntry,
        client: FraimicClient,
        scan_interval: int | None,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=(
                timedelta(seconds=scan_interval) if scan_interval is not None else None
            ),
        )
        self.client = client
        # Separate current reachability from last_update_success: restoring a
        # cached snapshot makes entities usable, but does not prove the frame
        # is awake in this Home Assistant session.
        self.frame_online = False
        # Parsed /info HTML diagnostics (panel size, battery health); empty
        # until the first successful scrape.
        self.info_page: dict[str, Any] = {}
        # Cloud albums proxied via the frame; None until (unless) fetched.
        self.albums: list[dict[str, Any]] | None = None
        self._store: Store[dict[str, Any]] = Store(
            hass, CACHE_VERSION, f"{DOMAIN}_coordinator_{entry.entry_id}"
        )
        self._consecutive_failures = 0
        self._expected_asleep = False
        self._last_seen: float | None = None
        self._last_probe_attempt = 0.0
        self._cloud_snapshot: tuple[float, dict[str, Any]] | None = None
        self._last_rediscovery: float | None = None
        self._rediscovery_task: asyncio.Task | None = None
        self._unsub_expiry: Callable[[], None] | None = None
        self._availability_listeners: set[Callable[[], None]] = set()
        # Start of a stretch with a reported cable and no charge gain:
        # {"since": epoch, "high": percent}; persisted with the cache.
        self._cable_drain: dict[str, float] | None = None
        self._unsynced_polls = 0
        # Epochs of access-point changes (wifi.bssid/channel) in the last day.
        self.ap_switches: list[float] = []
        self._last_ap: tuple[Any, Any] | None = None
        client.on_response = self._async_contact_seen

    async def async_restore(self) -> None:
        """Restore the last snapshot without contacting a sleeping frame."""
        cached = await self._store.async_load() or {}
        data = cached.get("data")
        if isinstance(data, dict):
            from homeassistant.util import dt as dt_util

            # Snapshots cached before the epoch fields existed; Minimum mode
            # may not poll for a long time, and the send queue needs them.
            restore_frame_times(data, dt_util.get_default_time_zone())
            self.data = data
            self.last_update_success = True
            # Power-saving modes can intentionally skip the startup poll. Keep
            # using the firmware-gated upload path established by the last
            # successful poll instead of falling back to legacy multipart.
            self.client.prefer_api_image = firmware_supports_api_image(
                data.get("firmware_version")
            )
        info_page = cached.get("info_page")
        if isinstance(info_page, dict):
            self.info_page = info_page
        albums = cached.get("albums")
        if isinstance(albums, list):
            self.albums = albums
        last_seen = cached.get("last_seen")
        if isinstance(last_seen, (int, float)):
            self._last_seen = float(last_seen)
        self._expected_asleep = cached.get("expected_asleep") is True
        drain = cached.get("cable_drain")
        if isinstance(drain, dict):
            self._cable_drain = drain
        switches = cached.get("ap_switches")
        if isinstance(switches, list):
            self.ap_switches = [t for t in switches if isinstance(t, (int, float))]
        self._async_schedule_expiry()

    def _cache_payload(self) -> dict[str, Any]:
        return {
            "data": self.data,
            "info_page": self.info_page,
            "albums": self.albums,
            "last_seen": self.last_seen,
            "expected_asleep": self._expected_asleep,
            "cable_drain": self._cable_drain,
            "ap_switches": self.ap_switches,
        }

    async def _async_save_cache(self) -> None:
        await self._store.async_save(self._cache_payload())

    @callback
    def _async_contact_seen(self) -> None:
        """Any frame response: persist it, move the deadline, refresh entities."""
        self._consecutive_failures = 0
        self._store.async_delay_save(self._cache_payload, CONTACT_SAVE_DELAY)
        self._async_schedule_expiry()
        self._async_notify_availability()

    @callback
    def _async_notify_availability(self) -> None:
        # Entities only: data listeners (scheduler, send queue) would read
        # this as fresh frame data and retry sends.
        for listener in list(self._availability_listeners):
            listener()

    @callback
    def async_backend_contact(self, telemetry: dict[str, Any]) -> None:
        """Use an authenticated companion poll as contact, without marking LAN awake."""
        seen = telemetry.get("last_seen")
        if isinstance(seen, (float, int)) and (self.last_seen or 0) < seen <= time.time():
            self._last_seen = float(seen)
            data = dict(self.data or {})
            percent = telemetry.get("battery_percent")
            if isinstance(percent, int) and 0 <= percent <= 100:
                battery = dict(data.get("battery") or {})
                battery["percent"] = percent
                # Poll telemetry does not report cable/charging. Don't let an
                # old cable observation override a newer low battery reading.
                battery.pop("charging", None)
                battery.pop("cable_connected", None)
                data["battery"] = battery
            data["source"] = "backend"
            self.data = data
            self._store.async_delay_save(self._cache_payload, CONTACT_SAVE_DELAY)
            self._async_schedule_expiry()
        self._async_notify_availability()

    @property
    def consecutive_failures(self) -> int:
        """Number of polls that have failed since the frame last answered."""
        return self._consecutive_failures

    @property
    def last_seen(self) -> float | None:
        """Epoch timestamp of the latest confirmed frame response."""
        seen = [t for t in (self._last_seen, self.client.last_response) if t is not None]
        return max(seen) if seen else None

    @property
    def device_reachable(self) -> bool:
        """Entity-availability verdict that rides out normal deep sleep.

        Only confirmed contact counts: a LAN response, or the account's own
        check-in time for cloud-delivered frames. A restored cache or cloud
        snapshot alone never extends the window. Only availability is
        affected; failed polls still raise UpdateFailed and count towards
        rediscovery.
        """
        if self.data is None:
            return False
        expires = self._reachable_until()
        return expires is not None and time.time() < expires

    def _reachable_until(self) -> float | None:
        contacts = [
            seen
            for seen in (self.last_seen, _cloud_last_seen(self.data or {}))
            if seen is not None
        ]
        return max(contacts) + UNAVAILABLE_AFTER if contacts else None

    @callback
    def async_update_listeners(self) -> None:
        super().async_update_listeners()
        self._async_schedule_expiry()

    @callback
    def _async_schedule_expiry(self) -> None:
        """Rewrite entity states when the grace window lapses.

        Availability is time-based, but Home Assistant only re-reads it when
        listeners fire; a frame nobody polls would otherwise stay available.
        """
        if self._unsub_expiry is not None:
            self._unsub_expiry()
            self._unsub_expiry = None
        expires = self._reachable_until()
        if expires is not None and (delay := expires - time.time()) > 0:
            self._unsub_expiry = async_call_later(self.hass, delay, self._async_expired)
        elif self._needs_cloud_check_in():
            # The account check-in is the only evidence left; keep asking.
            self._unsub_expiry = async_call_later(
                self.hass, CLOUD_CHECK_IN_RETRY, self._async_expired
            )

    @callback
    def _async_expired(self, _now: Any) -> None:
        self._unsub_expiry = None
        self.config_entry.async_create_task(
            self.hass, self.async_refresh_availability(), "fraimic-availability-expiry"
        )

    def _needs_cloud_check_in(self) -> bool:
        """Cloud frame that no poll will ever revisit (Minimum power mode)."""
        runtime = getattr(self.config_entry, "runtime_data", None)
        return getattr(runtime, "cloud", None) is not None and self.update_interval is None

    async def async_refresh_availability(self) -> None:
        """Re-evaluate availability, re-reading the cloud check-in if needed.

        Cloud-delivered frames wake for album slots without any LAN poll, so
        in non-polling modes the account's check-in is the only evidence they
        are still alive. Polling modes already fall back to it on failed polls.
        """
        if self._needs_cloud_check_in():
            before = self.data
            self._cloud_snapshot = None  # judge expiry on a fresh account read
            cloud_data = await self._async_cloud_snapshot()
            # A LAN poll that stored data meanwhile is fresher; keep it.
            if cloud_data is not None and self.data is before:
                self.data = cloud_data
                await self._async_save_cache()
        self._async_notify_availability()
        # Newer contact may have moved the deadline; keep watching it.
        self._async_schedule_expiry()

    @callback
    def async_add_availability_listener(
        self, listener: Callable[[], None]
    ) -> Callable[[], None]:
        """Call ``listener`` when the grace window lapses without new data."""
        self._availability_listeners.add(listener)
        return lambda: self._availability_listeners.discard(listener)

    async def async_shutdown(self) -> None:
        await super().async_shutdown()
        # A reload builds a new coordinator on the same cache key; late
        # responses must not reach this one. async_save also cancels any
        # pending delayed save.
        self.client.on_response = None
        if self._unsub_expiry is not None:
            self._unsub_expiry()
            self._unsub_expiry = None
        await self._async_save_cache()

    @property
    def expected_asleep(self) -> bool:
        """Whether Home Assistant intentionally put the frame to sleep."""
        return self._expected_asleep

    @callback
    def async_set_frame_online(
        self, online: bool, *, expected_sleep: bool = False
    ) -> None:
        """Record liveness observed outside the normal coordinator poll.

        Contact time is not set here: the client records every real frame
        response, while some callers report success without a LAN request.
        """
        if online:
            self._consecutive_failures = 0
            self._expected_asleep = False
        elif expected_sleep:
            self._expected_asleep = True
        if online or expected_sleep:
            self.config_entry.async_create_task(
                self.hass, self._async_save_cache(), "fraimic-save-liveness"
            )
        self.frame_online = online
        self.async_update_listeners()

    @callback
    def async_probe_if_stale(self, max_age: float = DASHBOARD_PROBE_MAX_AGE) -> None:
        """Check liveness in the background for a dashboard viewer.

        Cached sensors stay as they are when the frame does not answer; only
        the online flag changes. An answering frame gets a full refresh.
        """
        now = time.time()
        if now - self._last_probe_attempt < max_age:
            return
        self._last_probe_attempt = now
        self.config_entry.async_create_task(
            self.hass, self._async_probe(), "fraimic-dashboard-probe"
        )

    @property
    def frame_busy(self) -> bool:
        """Whether an upload (or awake-window step) holds the frame's HTTP task.

        The firmware serves every client from one task with blocking handlers,
        so any other request waits behind an upload body or a held render reply
        and times out, which would look like the frame going offline.
        """
        runtime = getattr(self.config_entry, "runtime_data", None)
        lock = getattr(runtime, "upload_lock", None)
        return lock is not None and lock.locked()

    async def _async_probe(self) -> None:
        if self.frame_busy:
            return
        if self.client.wrong_device is not None:
            # Only the identity poll can tell whether the right frame is back.
            await self.async_request_refresh()
            return
        try:
            await self.client.get_battery()
        except FraimicError:
            self.async_set_frame_online(False)
            cloud_data = await self._async_cloud_snapshot()
            if cloud_data is not None:
                self.async_set_updated_data(cloud_data)
                await self._async_save_cache()
            return
        # The frame answered: confirmed contact even if the full poll fails.
        self.async_set_frame_online(True)
        await self.async_request_refresh()

    async def _async_update_data(self) -> dict[str, Any]:
        self._last_probe_attempt = time.time()
        window = getattr(getattr(self.config_entry, "runtime_data", None), "awake_window", None)
        if window is not None and window.resting:
            # A LAN poll counts as activity and would keep the frame awake
            # between its windows; the account knows its last state.
            cloud_data = await self._async_cloud_snapshot()
            if cloud_data is not None:
                self.data = cloud_data
                return cloud_data
            raise UpdateFailed("The frame rests between its awake windows")
        if self.frame_busy:
            # Skip the poll without counting a failure, keeping the previous
            # poll's outcome; the next scheduled poll contacts the frame.
            if self.data is not None and self.last_update_success:
                return self.data
            raise UpdateFailed("An upload to the frame is in progress")
        contact_before = self.client.last_response
        try:
            data = normalize_info(await self.client.get_info())
        except FraimicConnectionError as err:
            # The frame is unreachable, most likely in deep sleep. Raise a
            # (non-noisy) UpdateFailed; entities ride it out via device_reachable.
            self._consecutive_failures += 1
            self.frame_online = False
            cloud_data = await self._async_cloud_snapshot()
            if cloud_data is not None:
                # Cloud delivery keeps the frame asleep on purpose; the account
                # still knows its battery and settings from the last wake.
                self.data = cloud_data
                await self._async_save_cache()
                return cloud_data
            self._async_maybe_rediscover()
            raise UpdateFailed(str(err)) from err
        except FraimicError as err:
            self.frame_online = False
            # An error response is still contact; keep it across restarts.
            await self._async_save_cache()
            raise UpdateFailed(str(err)) from err
        if (foreign := self._foreign_device_key(data)) is not None:
            # Not this entry's frame: keep its data out, and don't count the
            # reply as contact with the frame this entry represents.
            self.client.last_response = contact_before
            # The reply already armed expiry and told entities the frame was
            # reachable; recompute both from the restored contact time.
            self._async_schedule_expiry()
            self._async_notify_availability()
            self.frame_online = False
            if self.client.wrong_device != foreign:
                _LOGGER.warning(
                    "A different frame answers at %s for %s; holding its sends "
                    "and searching the network for the right one",
                    self.client.host,
                    self.config_entry.title,
                )
            self.client.wrong_device = foreign
            self._async_maybe_rediscover(force=True, near=data["wifi"].get("ip"))
            raise UpdateFailed(f"A different frame answers at {self.client.host}")
        if self.client.wrong_device is not None:
            _LOGGER.info("%s answers at %s again", self.config_entry.title, self.client.host)
            self.client.wrong_device = None
            # The identity poll itself wasn't counted while the flag was set.
            self.client.last_response = time.time()
            self._async_contact_seen()
        self._consecutive_failures = 0
        self.frame_online = True
        self._cloud_snapshot = None
        self._expected_asleep = False
        self._last_seen = time.time()
        # Newer firmware accepts the simpler (and structured-error) upload
        # path; the client stays on multipart /upload until confirmed.
        self.client.prefer_api_image = firmware_supports_api_image(
            data.get("firmware_version")
        )
        from homeassistant.util import dt as dt_util

        annotate_frame_times(data, time.time(), dt_util.get_default_time_zone())
        self._async_update_timezone_issue(data["device"]["utc_offset_minutes"])
        self._async_watch_cable_drain(data["battery"], time.time())
        self._async_watch_connectivity(data, time.time())
        self._async_backfill_unique_id(data)
        self.data = data
        await self._async_save_cache()
        return data

    async def _async_cloud_snapshot(self) -> dict[str, Any] | None:
        """Use the account record while retaining only static LAN identity."""
        runtime = getattr(self.config_entry, "runtime_data", None)
        cloud = getattr(runtime, "cloud", None)
        if cloud is None:
            return None
        # The account record only changes when the frame wakes, so a failed
        # LAN poll every few seconds must not turn into a cloud call each time.
        now = time.time()
        if self._cloud_snapshot and now - self._cloud_snapshot[0] < CLOUD_SNAPSHOT_TTL:
            return self._cloud_snapshot[1]
        from .cloud import FraimicCloudError
        from .cloud_delivery import cloud_device_snapshot

        try:
            device = await cloud.async_device()
        except FraimicCloudError as err:
            _LOGGER.debug("Cloud device lookup failed: %s", err)
            return None
        if device is None:
            return None
        base = dict(self.data) if isinstance(self.data, dict) else {}
        merged = cloud_device_snapshot(device, base)
        merged["source"] = "cloud"
        self._cloud_snapshot = (now, merged)
        return merged

    async def async_refresh_albums(self) -> list[dict[str, Any]] | None:
        """Fetch cloud albums on demand; normal coordinator polls never do this."""
        if self.frame_busy:
            return self.albums
        try:
            self.albums = await self.client.get_albums()
        except FraimicError as err:
            _LOGGER.debug("On-demand album fetch failed: %s", err)
            return self.albums
        await self._async_save_cache()
        self.async_update_listeners()
        return self.albums

    def expire_albums_cache(self) -> None:
        """Invalidate albums after an edit without causing a background fetch."""
        self.albums = None
        self.config_entry.async_create_task(
            self.hass,
            self._async_save_cache(),
            "fraimic-save-albums-invalidation",
        )

    async def async_refresh_info_page(self) -> dict[str, Any]:
        """Scrape slow battery-health diagnostics only when explicitly needed."""
        if self.frame_busy:
            return self.info_page
        try:
            parsed = parse_info_page(await self.client.get_info_page())
        except FraimicError as err:
            _LOGGER.debug("On-demand /info scrape failed: %s", err)
            return self.info_page
        if parsed:
            self.info_page = parsed
            await self._async_save_cache()
            self.async_update_listeners()
        return self.info_page

    @callback
    def _async_update_timezone_issue(self, offset: int | None) -> None:
        """Explain a frame clock in another timezone; it can't be changed."""
        if offset is None:
            return
        from homeassistant.helpers import issue_registry as ir
        from homeassistant.util import dt as dt_util

        issue_id = f"frame_timezone_{self.config_entry.entry_id}"
        now = dt_util.now()
        ha_offset = now.utcoffset() or timedelta()
        if timedelta(minutes=offset) == ha_offset:
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)
            return
        frame_tz = timezone(timedelta(minutes=offset))
        maintenance = now.astimezone(frame_tz).replace(
            hour=3, minute=0, second=0, microsecond=0
        )
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="frame_timezone",
            translation_placeholders={
                "frame": self.config_entry.title,
                "frame_offset": format_utc_offset(offset),
                "ha_offset": format_utc_offset(int(ha_offset.total_seconds() // 60)),
                "maintenance": dt_util.as_local(maintenance).strftime("%H:%M"),
            },
        )

    @callback
    def _async_watch_connectivity(self, data: dict[str, Any], now: float) -> None:
        """Count AP switches and explain a frame that can't get internet time."""
        from homeassistant.helpers import issue_registry as ir

        wifi = data["wifi"]
        ap = (wifi.get("bssid"), wifi.get("channel"))
        if None not in ap:
            if self._last_ap is not None and ap != self._last_ap:
                self.ap_switches.append(now)
            self._last_ap = ap
        self.ap_switches = [t for t in self.ap_switches if now - t < AP_SWITCH_WINDOW]

        device = data["device"]
        issue_id = f"time_unsynced_{self.config_entry.entry_id}"
        synced = device.get("time_synced")
        if synced is True:
            self._unsynced_polls = 0
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)
            return
        uptime = device.get("uptime_s")
        if synced is not False or not isinstance(uptime, (int, float)):
            return
        if uptime < UNSYNCED_UPTIME:
            return
        self._unsynced_polls += 1
        if self._unsynced_polls < UNSYNCED_POLLS:
            return
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="time_unsynced",
            translation_placeholders={
                "frame": self.config_entry.title,
                "switches": str(len(self.ap_switches)),
            },
        )

    @property
    def _phantom_cable_issue(self) -> str:
        return f"phantom_cable_{self.config_entry.entry_id}"

    @callback
    def _async_watch_cable_drain(self, battery: dict[str, Any], now: float) -> None:
        """Raise a repair when a reported cable doesn't stop the battery falling.

        While the cable is reported the frame refuses to sleep, so a phantom
        cable can drain the battery in days. Uses poll data only.
        """
        from homeassistant.helpers import issue_registry as ir

        percent = battery.get("percent")
        cable = battery.get("cable_connected") is True or battery.get("charging") is True
        drain = self._cable_drain
        if not cable or not isinstance(percent, (int, float)):
            if drain is not None:
                self._cable_drain = None
                ir.async_delete_issue(self.hass, DOMAIN, self._phantom_cable_issue)
            return
        if percent >= CABLE_DRAIN_PLATEAU:
            return
        if drain is None or percent > drain["high"]:
            # A new stretch, or the battery gained charge: really charging.
            self._cable_drain = {"since": now, "high": float(percent)}
            if drain is not None:
                ir.async_delete_issue(self.hass, DOMAIN, self._phantom_cable_issue)
            return
        if (
            drain["high"] - percent < CABLE_DRAIN_POINTS
            or now - drain["since"] < CABLE_DRAIN_SECONDS
        ):
            return
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            self._phantom_cable_issue,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="phantom_cable",
            translation_placeholders={
                "frame": self.config_entry.title,
                "hours": str(int((now - drain["since"]) // 3600)),
                "start": str(int(drain["high"])),
                "percent": str(int(percent)),
            },
        )

    def _replaceable_unique_id(self, data: dict[str, Any]) -> bool:
        """Whether the unique_id predates device_key support (host or device_id)."""
        unique_id = self.config_entry.unique_id
        if not unique_id or unique_id == data.get("device_id"):
            return True
        hosts = (self.client.host, str(self.config_entry.data.get(CONF_HOST, "")))
        return unique_id.lower() in {host.lower() for host in hosts}

    def _foreign_device_key(self, data: dict[str, Any]) -> str | None:
        """The answering frame's key when it isn't this entry's frame."""
        identity = data.get("device_key") or data.get("device_id")
        if not identity or self.config_entry.unique_id in (
            data.get("device_key"),
            data.get("device_id"),
        ):
            return None
        if self._replaceable_unique_id(data):
            return None
        return str(identity)

    def _async_backfill_unique_id(self, data: dict[str, Any]) -> None:
        """Adopt the frame's stable ``device_key`` as the entry's unique_id.

        Entries created before device_key support (or while the frame was
        asleep) carry a host-based unique_id; upgrade it on the first
        successful poll so an IP change can never look like a new device.
        A device-key unique_id is never replaced: a different key at this
        host is another frame (see ``_foreign_device_key``).
        """
        device_key = data.get("device_key")
        entry = self.config_entry
        if (
            not device_key
            or entry.unique_id == device_key
            or not self._replaceable_unique_id(data)
        ):
            return
        for other in self.hass.config_entries.async_entries(DOMAIN):
            if other.entry_id != entry.entry_id and other.unique_id == device_key:
                _LOGGER.warning(
                    "Frame at %s reports device_key %s, already claimed by "
                    "entry %s — leaving unique_id unchanged",
                    self.client.host,
                    device_key,
                    other.title,
                )
                return
        _LOGGER.debug("Backfilling unique_id %s for entry %s", device_key, entry.title)
        self.hass.config_entries.async_update_entry(entry, unique_id=device_key)

    def _async_maybe_rediscover(
        self, *, force: bool = False, near: str | None = None
    ) -> None:
        """Kick off a subnet scan for the frame's new IP, heavily rate-limited.

        ``force`` skips the failure threshold (another frame answers at the
        host, so the address is certainly stale); ``near`` is an address on
        the frame's LAN to scan around when the host is a hostname.
        """
        if not force and self._consecutive_failures < REDISCOVERY_FAIL_THRESHOLD:
            return
        device_key = self.config_entry.unique_id
        if not device_key:
            return
        last_ip = self.client.host
        try:
            ipaddress.IPv4Address(last_ip)
        except ValueError:
            # A hostname that simply fails to answer re-resolves on its own;
            # scanning is only useful when a raw IP went stale, or when the
            # name now resolves to another frame.
            if near is None:
                return
            try:
                ipaddress.IPv4Address(near)
            except ValueError:
                return
            last_ip = near
        if self._rediscovery_task is not None and not self._rediscovery_task.done():
            return
        now = time.monotonic()
        if (
            self._last_rediscovery is not None
            and now - self._last_rediscovery < REDISCOVERY_MIN_INTERVAL
        ):
            return
        self._last_rediscovery = now
        self._rediscovery_task = self.config_entry.async_create_background_task(
            self.hass,
            self._async_rediscover(last_ip, device_key),
            name=f"fraimic-rediscover-{self.config_entry.entry_id}",
        )

    async def _async_rediscover(self, last_ip: str, device_key: str) -> None:
        """Scan the /24 around the last known IP for this frame's device_key."""
        # Lazy: discovery imports normalize_info from this module.
        from .discovery import async_scan_subnet

        subnet = ipaddress.IPv4Network(f"{last_ip}/24", strict=False)
        scan = await async_scan_subnet(
            self.hass, subnet, timeout=REDISCOVERY_PROBE_TIMEOUT
        )
        found = scan[device_key][0] if device_key in scan else None
        if found is None or found == self.client.host:
            return
        _LOGGER.warning(
            "Frame %s moved from %s to %s — updating the config entry",
            self.config_entry.title,
            last_ip,
            found,
        )
        # The entry's update listener reloads it, rebuilding the client with
        # the new host.
        self.hass.config_entries.async_update_entry(
            self.config_entry,
            data={**self.config_entry.data, CONF_HOST: found},
        )


# Frame timestamps (``device.local_time``, ``display.last_refresh`` and
# ``next_refresh``) are local calendar strings without a UTC offset, in the
# frame's stored POSIX timezone. That is often not Home Assistant's: signing in
# through the setup portal stores none (``EST5EDT`` fallback), and an IANA name
# such as ``Europe/Oslo`` parses as UTC.
FRAME_OFFSET_STEP = 15  # minutes; real offsets are whole quarter hours
MAX_FRAME_OFFSET = 14 * 60


def frame_utc_offset(local_time: Any, now: float) -> int | None:
    """The frame's current UTC offset in minutes, from its synced local clock."""
    if not isinstance(local_time, str) or not local_time:
        return None
    try:
        local = datetime.fromisoformat(local_time).replace(tzinfo=None)
    except ValueError:
        return None
    utc = datetime.fromtimestamp(now, timezone.utc).replace(tzinfo=None)
    steps = round((local - utc).total_seconds() / (FRAME_OFFSET_STEP * 60))
    minutes = steps * FRAME_OFFSET_STEP
    return minutes if abs(minutes) <= MAX_FRAME_OFFSET else None


def frame_timestamp(value: Any, offset: int | None, fallback: tzinfo) -> float | None:
    """Epoch of a frame-local timestamp; ``fallback`` when the offset is unknown.

    Offsets change with DST, so a time across a transition can be an hour off.
    """
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        zone = timezone(timedelta(minutes=offset)) if offset is not None else fallback
        parsed = parsed.replace(tzinfo=zone)
    return parsed.timestamp()


def annotate_frame_times(data: dict[str, Any], now: float, fallback: tzinfo) -> None:
    """Add ``utc_offset_minutes`` and epoch ``*_at`` fields to a fresh poll.

    The offset is only known while the frame reports a synced clock. Every
    consumer reads the epoch fields; nothing parses the frame strings itself.
    """
    device = data["device"]
    offset = (
        frame_utc_offset(device.get("local_time"), now)
        if device.get("time_synced") is True
        else None
    )
    device["utc_offset_minutes"] = offset
    display = data["display"]
    for key in ("last_refresh", "next_refresh"):
        display[f"{key}_at"] = frame_timestamp(display.get(key), offset, fallback)


def restore_frame_times(data: dict[str, Any], fallback: tzinfo) -> None:
    """Fill missing epoch ``*_at`` fields of a cached snapshot.

    Uses the cached offset when there is one; the snapshot's ``local_time``
    is stale, so no new offset is derived here.
    """
    device = data.get("device")
    display = data.get("display")
    if not isinstance(display, dict):
        return
    offset = device.get("utc_offset_minutes") if isinstance(device, dict) else None
    for key in ("last_refresh", "next_refresh"):
        if f"{key}_at" not in display:
            display[f"{key}_at"] = frame_timestamp(
                display.get(key), offset if isinstance(offset, int) else None, fallback
            )


def format_utc_offset(minutes: int) -> str:
    """``UTC+02:00`` style label for an offset in minutes."""
    sign = "+" if minutes >= 0 else "-"
    hours, rest = divmod(abs(minutes), 60)
    return f"UTC{sign}{hours:02d}:{rest:02d}"


def _cloud_last_seen(data: dict[str, Any]) -> float | None:
    """Epoch of the frame's last cloud check-in, from a cloud snapshot."""
    device = data.get("device")
    value = device.get("cloud_last_seen") if isinstance(device, dict) else None
    if not isinstance(value, str):
        return None
    try:
        return cloud_timestamp(value)
    except ValueError:
        return None


def normalize_info(info: dict[str, Any]) -> dict[str, Any]:
    """Map the frame's ``/api/info`` payload into one canonical shape.

    The official guide documents a nested schema (``battery.percent``,
    ``wifi.rssi``), while real frames have been observed returning a flat schema
    (``battery_pct``, ``wifi_ssid``, ``device_id``). We accept either so the
    entities don't care which firmware is talking to us.
    """

    def pick(*candidates: Any) -> Any:
        for candidate in candidates:
            if isinstance(candidate, tuple):
                cur: Any = info
                for key in candidate:
                    if isinstance(cur, dict) and cur.get(key) is not None:
                        cur = cur[key]
                    else:
                        cur = None
                        break
                if cur is not None:
                    return cur
            elif isinstance(info, dict) and info.get(candidate) is not None:
                return info[candidate]
        return None

    return {
        "firmware_version": pick("firmware_version", ("device", "firmware_version")),
        "device_id": pick("device_id", ("device", "device_id"), ("device", "id")),
        # Stable per-device identifier (also the frame's cloud credential id);
        # used as the config entry unique_id.
        "device_key": pick(("device", "device_key"), "device_key"),
        "model": pick(
            "display_type", "model", "device_type", "variant", ("device", "model")
        ),
        "wifi": {
            "connected": pick(("wifi", "connected"), "wifi_connected"),
            "ssid": pick(("wifi", "ssid"), "wifi_ssid", "ssid"),
            "rssi": pick(("wifi", "rssi"), "wifi_rssi", "rssi"),
            "channel": pick(("wifi", "channel"), "wifi_channel"),
            "bssid": pick(("wifi", "bssid"), "bssid", "wifi_bssid"),
            "ip": pick(("wifi", "ip"), "ip_address", "ip"),
            "mac": pick(("wifi", "mac"), "mac", "mac_address"),
        },
        "battery": {
            "percent": pick(("battery", "percent"), "battery_pct", "battery_percent"),
            "voltage_mv": pick(
                ("battery", "voltage_mv"), "battery_voltage_mv", "voltage_mv"
            ),
            "charging": pick(("battery", "charging"), "charging", "battery_charging"),
            "cable_connected": pick(("battery", "cable_connected"), "cable_connected"),
            "source": pick(("battery", "source"), "battery_source"),
        },
        "device": {
            "registered": pick(("device", "registered"), "registered"),
            "time_synced": pick(("device", "time_synced"), "time_synced"),
            "local_time": pick(("device", "local_time"), "local_time"),
            "uptime_s": pick(("device", "uptime_s"), "uptime_s", "uptime"),
        },
        "settings": {
            "voice_recording": pick(("settings", "voice_recording"), "voice_recording"),
            "keep_awake": pick(("settings", "keep_awake"), "keep_awake"),
            "auto_update": pick(("settings", "auto_update"), "auto_update"),
            "charging_led": pick(("settings", "charging_led"), "charging_led"),
        },
        "display": {
            "last_refresh": pick(("display", "last_refresh"), "last_refresh"),
            "next_refresh": pick(("display", "next_refresh"), "next_refresh"),
            "render_attempts": pick(("display", "render_attempts"), "render_attempts"),
            "render_failures": pick(("display", "render_failures"), "render_failures"),
            "width": pick(("display", "width"), "display_width", "width"),
            "height": pick(("display", "height"), "display_height", "height"),
        },
        "raw": info,
    }
