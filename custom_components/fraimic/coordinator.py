"""Data update coordinator for the Fraimic E-Ink Canvas."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import time
from datetime import timedelta
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    FraimicClient,
    FraimicConnectionError,
    FraimicError,
    firmware_supports_api_image,
)
from .const import DOMAIN
from .info_page import parse_info_page
from .send_queue import FAST_POLL_SECONDS

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

# The /info HTML page (panel size, battery health) changes slowly; scrape it
# on the first successful poll and then daily, retrying hourly on failure. A
# scrape failure must never fail the coordinator.
INFO_PAGE_INTERVAL = 24 * 3600
INFO_PAGE_RETRY_INTERVAL = 3600

# The albums list is proxied by the frame to the Fraimic cloud — poll it on
# its own slow cadence, gated on the frame being reachable at all. LAN-only
# frames answer 502 server_unreachable; that simply leaves albums as None.
ALBUMS_INTERVAL = 30 * 60

type FraimicConfigEntry = ConfigEntry[FraimicRuntimeData]


class FraimicRuntimeData:
    """Objects shared across the integration's platforms."""

    def __init__(self, coordinator: FraimicDataUpdateCoordinator, client: FraimicClient) -> None:
        self.coordinator = coordinator
        self.client = client
        # Set by the image platform once its preview entity is created, so the
        # upload service can refresh the on-dashboard preview.
        self.preview_image: Any = None
        # Ditto for the dashboard-screen preview entity (render_screen output,
        # including preview-only renders that never reach the frame).
        self.screen_preview_image: Any = None
        # Last preview PNG, also exposed as the media_player's artwork.
        self.last_preview: bytes | None = None
        # Playlist scheduler (set during entry setup; None until then).
        self.scheduler: Any = None
        # Queued-send manager (send_queue.FraimicSendQueue; set during setup).
        self.send_queue: Any = None
        # Serialize uploads; the frame can only process one long refresh.
        self.upload_lock = asyncio.Lock()
        # Set by the media player so enabling playlists can stop camera loops.
        self.stop_camera_loop: Any = None
        # Attribution info for online artwork currently on the frame
        # (asdict of providers.base.ArtCandidate), or None.
        self.last_art: dict[str, Any] | None = None
        # Fallback media-player title for non-provider content currently on the frame.
        self.media_title: str | None = None


class FraimicDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls ``/api/info`` and exposes the latest device snapshot."""

    config_entry: FraimicConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: FraimicConfigEntry,
        client: FraimicClient,
        scan_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self._scan_interval = scan_interval
        # Parsed /info HTML diagnostics (panel size, battery health); empty
        # until the first successful scrape.
        self.info_page: dict[str, Any] = {}
        self._info_page_next = 0.0
        # Cloud albums proxied via the frame; None until (unless) fetched.
        self.albums: list[dict[str, Any]] | None = None
        self._albums_next = 0.0
        self._consecutive_failures = 0
        self._last_rediscovery = 0.0
        self._rediscovery_task: asyncio.Task | None = None

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            data = normalize_info(await self.client.get_info())
        except FraimicConnectionError as err:
            # The frame is unreachable — most likely in deep sleep. Surface this
            # as a (non-noisy) UpdateFailed so entities go unavailable cleanly.
            self._consecutive_failures += 1
            self._async_maybe_rediscover()
            raise UpdateFailed(str(err)) from err
        except FraimicError as err:
            raise UpdateFailed(str(err)) from err
        self._consecutive_failures = 0
        # Newer firmware accepts the simpler (and structured-error) upload
        # path; the client stays on multipart /upload until confirmed.
        self.client.prefer_api_image = firmware_supports_api_image(
            data.get("firmware_version")
        )
        self._async_backfill_unique_id(data)
        await self._async_maybe_scrape_info_page()
        await self._async_maybe_fetch_albums()
        return data

    async def _async_maybe_fetch_albums(self) -> None:
        """Refresh the cloud albums list on a slow cadence (never fatal)."""
        now = time.monotonic()
        if now < self._albums_next:
            return
        self._albums_next = now + ALBUMS_INTERVAL
        try:
            self.albums = await self.client.get_albums()
        except FraimicError as err:
            _LOGGER.debug("Fetching albums failed (frame offline or LAN-only): %s", err)

    def expire_albums_cache(self) -> None:
        """Force the next poll to re-fetch albums (after an album edit)."""
        self._albums_next = 0.0

    def set_fast_poll(self, enabled: bool) -> None:
        """Poll every 30 s while a send is queued so the wake is noticed fast."""
        seconds = FAST_POLL_SECONDS if enabled else self._scan_interval
        self.update_interval = timedelta(seconds=seconds)

    async def _async_maybe_scrape_info_page(self) -> None:
        """Refresh the parsed /info HTML diagnostics on a slow cadence."""
        now = time.monotonic()
        if now < self._info_page_next:
            return
        try:
            parsed = parse_info_page(await self.client.get_info_page())
        except FraimicError as err:
            _LOGGER.debug("Scraping /info failed (retrying later): %s", err)
            self._info_page_next = now + INFO_PAGE_RETRY_INTERVAL
            return
        self._info_page_next = now + INFO_PAGE_INTERVAL
        if parsed:
            self.info_page = parsed

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
        _LOGGER.debug(
            "Backfilling unique_id %s for entry %s", device_key, entry.title
        )
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
        if now - self._last_rediscovery < REDISCOVERY_MIN_INTERVAL:
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
            "voltage_mv": pick(("battery", "voltage_mv"), "battery_voltage_mv", "voltage_mv"),
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
