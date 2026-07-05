"""Playlist scheduler: rotate stored dashboard screens on the frame.

One scheduler per config entry. A 60 s tick decides whether the current
screen's interval has elapsed (or its time window closed), renders the next
eligible screen, and uploads — unless the packed ``.bin`` hash matches what
is already on the glass, in which case the upload (a full ~30 s e-ink
refresh + battery) is skipped while the data refresh still happened.

Battery/sleep awareness: when the frame is unreachable the cycle is skipped
quietly and a pending flag is set; the next successful coordinator poll (the
frame woke up) triggers an immediate fresh render + push. Manual uploads
hold the playlist for one interval and clear the known-content hash so the
next playlist upload is never skipped.

State (enabled, current screen, last rotation, displayed hash) persists in a
Store — NOT entry options, which would reload the integration every
rotation.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import FraimicConfigEntry
from .render.display import async_show_screen
from .render.playlist import eligible, next_screen
from .render.schema import ScreenConfig
from .screens import screens_from_entry
from .services import FrameUploadError

_LOGGER = logging.getLogger(__name__)

TICK = timedelta(seconds=60)
STORE_VERSION = 1


class FraimicScheduler:
    """Rotates a config entry's stored screens on its frame."""

    def __init__(self, hass: HomeAssistant, entry: FraimicConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.screens: list[ScreenConfig] = screens_from_entry(entry)
        self.enabled = False
        self.current_id: str | None = None
        self.displayed_hash: str | None = None
        self._last_rotation: datetime | None = None
        self._hold_until: datetime | None = None
        self._pending: ScreenConfig | None = None
        self._pending_requires_enabled = True
        self._external_upload_count = 0
        self._busy = False
        self._store: Store[dict[str, Any]] = Store(
            hass, STORE_VERSION, f"{DOMAIN}_playlist_{entry.entry_id}"
        )
        self._unsub_timer: Callable[[], None] | None = None
        self._unsub_coordinator: Callable[[], None] | None = None
        self._listeners: list[Callable[[], None]] = []

    # -- lifecycle --------------------------------------------------------

    async def async_start(self) -> None:
        """Load persisted state and start ticking."""
        data = await self._store.async_load() or {}
        self.enabled = bool(data.get("enabled", False))
        self.current_id = data.get("current_screen_id")
        self.displayed_hash = data.get("displayed_hash")
        if raw := data.get("last_rotation"):
            self._last_rotation = dt_util.parse_datetime(raw)
        self._unsub_timer = async_track_time_interval(self.hass, self._async_tick, TICK)
        self._unsub_coordinator = self.entry.runtime_data.coordinator.async_add_listener(
            self._coordinator_updated
        )

    @callback
    def async_stop(self) -> None:
        if self._unsub_timer is not None:
            self._unsub_timer()
            self._unsub_timer = None
        if self._unsub_coordinator is not None:
            self._unsub_coordinator()
            self._unsub_coordinator = None

    # -- entity plumbing ---------------------------------------------------

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(listener)

        def _remove() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return _remove

    @callback
    def _notify(self) -> None:
        for listener in list(self._listeners):
            listener()

    @property
    def busy(self) -> bool:
        return self._busy

    @property
    def external_upload_active(self) -> bool:
        return self._external_upload_count > 0

    @property
    def current_screen(self) -> ScreenConfig | None:
        for screen in self.screens:
            if screen.screen_id == self.current_id:
                return screen
        return None

    # -- controls ----------------------------------------------------------

    async def async_set_enabled(self, enabled: bool, *, rotate: bool = True) -> None:
        if enabled == self.enabled:
            return
        self.enabled = enabled
        self._hold_until = None
        await self._async_save()
        self._notify()
        if enabled and rotate:
            await self._async_rotate(force=True)

    async def async_next(self) -> None:
        await self._async_step(1)

    async def async_previous(self) -> None:
        await self._async_step(-1)

    async def async_select(self, screen: ScreenConfig) -> None:
        """Show a specific screen now and pin rotation to it."""
        self._hold_until = None
        await self._async_show(screen, manual=True)

    async def _async_step(self, step: int) -> None:
        candidate = next_screen(self.screens, self.current_id, dt_util.now(), step=step)
        if candidate is None:
            raise HomeAssistantError("No screen is eligible to show right now")
        self._hold_until = None
        await self._async_show(candidate, manual=True)

    # -- external-upload interplay ------------------------------------------

    @callback
    def begin_external_upload(self) -> None:
        """A manual upload is starting; keep playlist work out of the way."""
        self._external_upload_count += 1

    @callback
    def finish_external_upload(self, *, uploaded: bool) -> None:
        self._external_upload_count = max(0, self._external_upload_count - 1)
        if uploaded:
            self.notify_external_upload()

    @callback
    def notify_external_upload(self) -> None:
        """A manual upload put unknown content on the glass.

        Hold the playlist for the current screen's interval (so the manual
        image gets its screen time) and forget the displayed hash so the next
        playlist upload can never be skipped as "unchanged".
        """
        self._pending = None
        self.displayed_hash = None
        screen = self.current_screen
        interval = screen.interval if screen else 1800
        self._hold_until = dt_util.utcnow() + timedelta(seconds=interval)
        self.entry.async_create_task(
            self.hass, self._async_save(), "fraimic_playlist_external_save"
        )
        self._notify()

    # -- the loop ------------------------------------------------------------

    async def _async_tick(self, _now: datetime | None = None) -> None:
        await self._async_rotate(force=False)

    async def _async_rotate(self, *, force: bool) -> None:
        if (
            not self.enabled
            or self._busy
            or self.external_upload_active
            or not self.screens
        ):
            return
        now = dt_util.now()
        if not force:
            if self._pending is not None:
                return
            if self._hold_until and dt_util.utcnow() < self._hold_until:
                return
            current = self.current_screen
            due = (
                current is None
                or not eligible(current, now)
                or self._last_rotation is None
                or (dt_util.utcnow() - self._last_rotation).total_seconds()
                >= current.interval
            )
            if not due:
                return
        candidate = next_screen(self.screens, self.current_id, now)
        if candidate is None:
            return  # nothing in window right now; leave the frame as-is
        await self._async_show(candidate)

    async def _async_show(self, screen: ScreenConfig, *, manual: bool = False) -> None:
        if self._busy:
            if manual:
                raise HomeAssistantError("A playlist upload is already in progress")
            return
        self._busy = True
        try:
            result = await async_show_screen(
                self.hass,
                self.entry,
                screen,
                skip_if_hash=self.displayed_hash,
                hold_playlist=False,
            )
        except FrameUploadError as err:
            self._pending = screen
            self._pending_requires_enabled = not manual
            _LOGGER.debug(
                "Playlist could not show %r (frame asleep?): %s", screen.name, err
            )
            return
        except HomeAssistantError as err:
            self._pending = None
            if manual:
                raise
            self.current_id = screen.screen_id
            self._last_rotation = dt_util.utcnow()
            await self._async_save()
            self._notify()
            _LOGGER.warning("Playlist skipped %r: %s", screen.name, err)
            return
        finally:
            self._busy = False
        self._pending = None
        self.current_id = screen.screen_id
        self.displayed_hash = result.get("content_hash")
        self._last_rotation = dt_util.utcnow()
        if not result.get("uploaded", True):
            _LOGGER.debug(
                "Playlist: %r content unchanged, upload skipped", screen.name
            )
        await self._async_save()
        self._notify()

    @callback
    def _coordinator_updated(self) -> None:
        """Frame answered a poll — if a push failed while it slept, retry now."""
        if (
            self._pending is not None
            and (self.enabled or not self._pending_requires_enabled)
            and self.entry.runtime_data.coordinator.last_update_success
            and not self._busy
        ):
            screen = self._pending
            manual = not self._pending_requires_enabled
            self.entry.async_create_task(
                self.hass,
                self._async_show(screen, manual=manual),
                "fraimic_playlist_wake_push",
            )

    async def _async_save(self) -> None:
        await self._store.async_save(
            {
                "enabled": self.enabled,
                "current_screen_id": self.current_id,
                "displayed_hash": self.displayed_hash,
                "last_rotation": (
                    self._last_rotation.isoformat() if self._last_rotation else None
                ),
            }
        )
