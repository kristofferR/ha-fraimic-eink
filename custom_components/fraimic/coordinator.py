"""Data update coordinator for the Fraimic E-Ink Canvas."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import FraimicClient, FraimicConnectionError, FraimicError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

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

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return normalize_info(await self.client.get_info())
        except FraimicConnectionError as err:
            # The frame is unreachable — most likely in deep sleep. Surface this
            # as a (non-noisy) UpdateFailed so entities go unavailable cleanly.
            raise UpdateFailed(str(err)) from err
        except FraimicError as err:
            raise UpdateFailed(str(err)) from err


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
        "model": pick(
            "display_type", "model", "device_type", "variant", ("device", "model")
        ),
        "wifi": {
            "connected": pick(("wifi", "connected"), "wifi_connected"),
            "ssid": pick(("wifi", "ssid"), "wifi_ssid", "ssid"),
            "rssi": pick(("wifi", "rssi"), "wifi_rssi", "rssi"),
            "channel": pick(("wifi", "channel"), "wifi_channel"),
            "ip": pick(("wifi", "ip"), "ip_address", "ip"),
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
        },
        "display": {
            "last_refresh": pick(("display", "last_refresh"), "last_refresh"),
            "next_refresh": pick(("display", "next_refresh"), "next_refresh"),
            "width": pick(("display", "width"), "display_width", "width"),
            "height": pick(("display", "height"), "display_height", "height"),
        },
        "raw": info,
    }
