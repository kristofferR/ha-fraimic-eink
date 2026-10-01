"""Data update coordinator for the Fraimic E-Ink Canvas."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    FraimicClient,
    FraimicConnectionError,
    FraimicError,
    firmware_supports_api_image,
)
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
REDISCOVERY_CONCURRENCY = 32
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
        # Serialize uploads; the frame can only process one long refresh.
        self.upload_lock = asyncio.Lock()
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
        client.on_response = self._async_contact_seen

    async def async_restore(self) -> None:
        """Restore the last snapshot without contacting a sleeping frame."""
        cached = await self._store.async_load() or {}
        data = cached.get("data")
        if isinstance(data, dict):
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
        self._async_schedule_expiry()

    def _cache_payload(self) -> dict[str, Any]:
        return {
            "data": self.data,
            "info_page": self.info_page,
            "albums": self.albums,
            "last_seen": self.last_seen,
            "expected_asleep": self._expected_asleep,
        }

    async def _async_save_cache(self) -> None:
        await self._store.async_save(self._cache_payload())

    @callback
    def _async_contact_seen(self) -> None:
        """Any frame response: persist it, move the deadline, refresh entities."""
        self.frame_online = True
        self._expected_asleep = False
        if self.data is not None:
            self._store.async_delay_save(self._cache_payload, CONTACT_SAVE_DELAY)
        self._async_schedule_expiry()
        self._async_notify_availability()

    @callback
    def _async_notify_availability(self) -> None:
        # Entities only: data listeners (scheduler, send queue) would read
        # this as fresh frame data and retry sends.
        for listener in list(self._availability_listeners):
            listener()

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
        if expires is None or (delay := expires - time.time()) <= 0:
            return

        @callback
        def _expired(_now: Any) -> None:
            self._unsub_expiry = None
            self._async_notify_availability()
            # Newer contact may have moved the deadline; keep watching it.
            self._async_schedule_expiry()

        self._unsub_expiry = async_call_later(self.hass, delay, _expired)

    @callback
    def async_add_availability_listener(
        self, listener: Callable[[], None]
    ) -> Callable[[], None]:
        """Call ``listener`` when the grace window lapses without new data."""
        self._availability_listeners.add(listener)
        return lambda: self._availability_listeners.discard(listener)

    async def async_shutdown(self) -> None:
        await super().async_shutdown()
        if self._unsub_expiry is not None:
            self._unsub_expiry()
            self._unsub_expiry = None

    @property
    def expected_asleep(self) -> bool:
        """Whether Home Assistant intentionally put the frame to sleep."""
        return self._expected_asleep

    @callback
    def async_set_frame_online(
        self, online: bool, *, expected_sleep: bool = False
    ) -> None:
        """Record liveness observed outside the normal coordinator poll."""
        if online:
            self._consecutive_failures = 0
            self._last_seen = time.time()
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

    async def _async_probe(self) -> None:
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
        self._async_backfill_unique_id(data)
        runtime = getattr(self.config_entry, "runtime_data", None)
        if runtime is not None and runtime.power is not None:
            await runtime.power.async_observe_frame(data)
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

    def _async_backfill_unique_id(self, data: dict[str, Any]) -> None:
        """Adopt the frame's stable ``device_key`` as the entry's unique_id.

        Entries created before device_key support (or while the frame was
        asleep) carry a host-based unique_id; upgrade it on the first
        successful poll so an IP change can never look like a new device.
        """
        device_key = data.get("device_key")
        entry = self.config_entry
        if not device_key or entry.unique_id == device_key:
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

    def _async_maybe_rediscover(self) -> None:
        """Kick off a subnet scan for the frame's new IP, heavily rate-limited."""
        if self._consecutive_failures < REDISCOVERY_FAIL_THRESHOLD:
            return
        device_key = self.config_entry.unique_id
        if not device_key:
            return
        try:
            ipaddress.IPv4Address(self.client.host)
        except ValueError:
            # Hostname-configured entries (fraimic.local) re-resolve on their
            # own; scanning is only useful when a raw IP went stale.
            return
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
            self._async_rediscover(self.client.host, device_key),
            name=f"fraimic-rediscover-{self.config_entry.entry_id}",
        )

    async def _async_rediscover(self, last_ip: str, device_key: str) -> None:
        """Scan the /24 around the last known IP for this frame's device_key."""
        network = ipaddress.ip_network(f"{last_ip}/24", strict=False)
        session = async_get_clientsession(self.hass)
        semaphore = asyncio.Semaphore(REDISCOVERY_CONCURRENCY)

        async def probe(ip: str) -> str | None:
            async with semaphore:
                try:
                    async with session.get(
                        f"http://{ip}/api/info",
                        timeout=aiohttp.ClientTimeout(total=REDISCOVERY_PROBE_TIMEOUT),
                    ) as resp:
                        if resp.status != 200:
                            return None
                        raw = await resp.json(content_type=None)
                except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
                    return None
            if not isinstance(raw, dict):
                return None
            return ip if normalize_info(raw).get("device_key") == device_key else None

        results = await asyncio.gather(*(probe(str(ip)) for ip in network.hosts()))
        found = next((ip for ip in results if ip), None)
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


def _cloud_last_seen(data: dict[str, Any]) -> float | None:
    """Epoch of the frame's last cloud check-in, from a cloud snapshot."""
    device = data.get("device")
    value = device.get("cloud_last_seen") if isinstance(device, dict) else None
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value).timestamp()
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
