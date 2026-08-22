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
import random
import time
from collections import Counter
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import FraimicConfigEntry
from .power import TRIGGER_MANUAL, TRIGGER_PLAYLIST
from .providers.ha import ArtFetchError
from .render.display import async_show_screen
from .render.playlist import eligible, next_screen
from .render.schema import ScreenConfig
from .screens import screens_from_entry
from .services import FrameUploadError

if TYPE_CHECKING:
    from .playlists import PlaylistManager

_LOGGER = logging.getLogger(__name__)

TICK = timedelta(seconds=60)
STORE_VERSION = 1


class FraimicScheduler:
    """Rotates a config entry's stored screens on its frame."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: FraimicConfigEntry,
        playlists: PlaylistManager | None = None,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self._playlists = playlists
        self.playlist_id: str | None = None
        self.shuffle = False
        self.screens: list[ScreenConfig] = []
        self._playback_order: list[str] = []
        self._load_assigned_playlist()
        self.enabled = False
        self._stored_enabled = False
        self.current_id: str | None = None
        self._playlist_cursor_id: str | None = None
        self.displayed_hash: str | None = None
        self._last_rotation: datetime | None = None
        self._hold_until: datetime | None = None
        self._pending: ScreenConfig | None = None
        self._pending_requires_enabled = True
        self._pending_from_queue = False
        self._pending_hold_on_success = False
        self._queued_ids: list[str] = []
        self._playlist_order: list[str] = []
        self._external_upload_count = 0
        self._external_upload_started_at: float | None = None
        self._busy = False
        self._last_show_permanently_rejected = False
        self._busy_started_at: float | None = None
        self._sending_slide_name: str | None = None
        self._store: Store[dict[str, Any]] = Store(
            hass, STORE_VERSION, f"{DOMAIN}_playlist_{entry.entry_id}"
        )
        self._unsub_timer: Callable[[], None] | None = None
        self._unsub_coordinator: Callable[[], None] | None = None
        self._listeners: list[Callable[[], None]] = []

    def _load_assigned_playlist(self) -> None:
        """Refresh the assigned catalog playlist or use the legacy slide list."""
        if self._playlists is None:
            self.screens = screens_from_entry(self.entry)
            self._playback_order = [screen.screen_id for screen in self.screens]
            return
        playlist = self._playlists.assigned_to(self.entry.entry_id)
        self.playlist_id = playlist.playlist_id if playlist is not None else None
        self.shuffle = playlist.shuffle if playlist is not None else False
        self.screens = self._playlists.render_slides(self.playlist_id)
        self._playback_order = [screen.screen_id for screen in self.screens]
        if self.shuffle:
            random.shuffle(self._playback_order)

    def _rotation_screens(self) -> list[ScreenConfig]:
        """Catalog slides in the current playback order."""
        if not self._playback_order:
            return self.screens
        by_id = {screen.screen_id: screen for screen in self.screens}
        return [
            by_id[slide_id]
            for slide_id in self._playback_order
            if slide_id in by_id
        ]

    # -- lifecycle --------------------------------------------------------

    async def async_start(self) -> None:
        """Load persisted state and start ticking."""
        data = await self._store.async_load() or {}
        self.enabled = bool(data.get("enabled", False))
        self._stored_enabled = self.enabled
        self.current_id = data.get("current_screen_id")
        self._playlist_cursor_id = data.get("playlist_cursor_id", self.current_id)
        self.displayed_hash = data.get("displayed_hash")
        self._queued_ids = [
            slide_id
            for slide_id in data.get("queued_slide_ids", [])
            if isinstance(slide_id, str)
        ]
        self._playlist_order = [
            slide_id
            for slide_id in data.get("playlist_order", [])
            if isinstance(slide_id, str)
        ]
        if self._playlists is None:
            self._apply_playlist_order()
        valid_ids = {screen.screen_id for screen in self.screens}
        self._queued_ids = [
            slide_id
            for slide_id in self._queued_ids
            if self._slide_by_id(slide_id) is not None
        ]
        pending_queue_id = data.get("pending_queue_id")
        if pending_queue_id in self._queued_ids:
            self._pending = self._slide_by_id(pending_queue_id)
            if self._pending is not None:
                self._pending_from_queue = True
                self._pending_requires_enabled = bool(
                    data.get("pending_requires_enabled", True)
                )
        if self._playlist_cursor_id not in valid_ids:
            self._playlist_cursor_id = (
                self.current_id if self.current_id in valid_ids else None
            )
        if raw := data.get("hold_until"):
            self._hold_until = dt_util.parse_datetime(raw)
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
    def stored_enabled(self) -> bool:
        return self._stored_enabled

    @property
    def external_upload_active(self) -> bool:
        return self._external_upload_count > 0

    @property
    def sending_started_at(self) -> float | None:
        """Epoch timestamp for the upload currently represented in the player."""
        return self._busy_started_at or self._external_upload_started_at

    @property
    def sending_slide_name(self) -> str | None:
        """Title of the scheduler slide currently being rendered or sent."""
        return self._sending_slide_name

    @property
    def last_rotation(self) -> datetime | None:
        """When the currently displayed scheduler slide last changed."""
        return self._last_rotation

    @property
    def hold_until(self) -> datetime | None:
        """When a one-off manual display stops holding rotation."""
        return self._hold_until

    @property
    def current_screen(self) -> ScreenConfig | None:
        if self.current_id is None:
            return None
        return self._slide_by_id(self.current_id)

    @property
    def playlist_name(self) -> str | None:
        if self._playlists is None:
            return self.entry.title if self.screens else None
        playlist = self._playlists.get(self.playlist_id)
        return playlist.name if playlist is not None else None

    @property
    def playlist_interval(self) -> int | None:
        if self._playlists is not None:
            playlist = self._playlists.get(self.playlist_id)
            return playlist.interval if playlist is not None else None
        return self.screens[0].interval if self.screens else None

    @property
    def queued_slides(self) -> list[ScreenConfig]:
        """Hand-added, play-once slides in their persisted order."""
        return [
            screen
            for slide_id in self._queued_ids
            if (screen := self._slide_by_id(slide_id)) is not None
        ]

    def _slide_by_id(self, slide_id: str) -> ScreenConfig | None:
        screen = next(
            (item for item in self.screens if item.screen_id == slide_id), None
        )
        if screen is not None or self._playlists is None:
            return screen
        return self._playlists.render_slide_by_id(slide_id)

    def playlist_up_next(self, *, limit: int = 10) -> list[ScreenConfig]:
        """Return the next distinct eligible playlist slides after the current one."""
        if limit <= 0:
            return []
        upcoming: list[ScreenConfig] = []
        cursor = self._playlist_cursor_id or self.current_id
        seen = {cursor} if cursor is not None else set()
        now = dt_util.now()
        rotation = self._rotation_screens()
        for _ in range(len(rotation)):
            candidate = next_screen(rotation, cursor, now)
            if candidate is None or candidate.screen_id in seen:
                break
            upcoming.append(candidate)
            seen.add(candidate.screen_id)
            cursor = candidate.screen_id
            if len(upcoming) >= limit:
                break
        return upcoming

    def raise_if_upload_active(self) -> None:
        if self._busy or self.external_upload_active:
            raise HomeAssistantError("An upload is already in progress")

    # -- controls ----------------------------------------------------------

    async def async_set_enabled(
        self,
        enabled: bool,
        *,
        rotate: bool = True,
        clear_hold: bool = True,
        persist: bool = True,
    ) -> None:
        changed = enabled != self.enabled
        hold_changed = clear_hold and self._hold_until is not None
        if persist:
            self._stored_enabled = enabled
        if not changed and not hold_changed:
            if persist:
                await self._async_save()
            return
        self.enabled = enabled
        if clear_hold:
            self._hold_until = None
        if persist:
            await self._async_save()
        if changed or hold_changed:
            self._notify()
        if changed and enabled and rotate:
            screen = self._pending
            if screen is not None and self._can_retry_pending(screen):
                await self._async_retry_pending(screen)
                return
            await self._async_rotate(force=False)

    async def async_next(self) -> bool:
        return await self._async_step(1)

    async def async_previous(self) -> bool:
        return await self._async_step(-1)

    async def async_select(self, screen: ScreenConfig, *, hold: bool = False) -> None:
        """Show a specific screen now and pin rotation to it."""
        await self._async_show(
            screen,
            manual=True,
            advance_playlist=not hold,
            clear_hold_on_success=not hold,
            hold_on_success=hold,
        )

    async def _async_step(self, step: int) -> bool:
        if step > 0 and self.queued_slides:
            return await self._async_show_queued(
                self.queued_slides[0], manual=True
            )
        candidate = next_screen(
            self._rotation_screens(),
            self._playlist_cursor_id or self.current_id,
            dt_util.now(),
            step=step,
        )
        if candidate is None:
            raise HomeAssistantError("No screen is eligible to show right now")
        return await self._async_show(candidate, manual=True)

    async def async_add_to_queue(
        self, slide: ScreenConfig, *, play_next: bool = False
    ) -> None:
        """Add a stored slide to the hand-added, play-once queue."""
        if self._slide_by_id(slide.screen_id) is None:
            raise HomeAssistantError("That slide is no longer available")
        if play_next:
            self._queued_ids.insert(0, slide.screen_id)
            self._sync_pending_queue_head()
        else:
            self._queued_ids.append(slide.screen_id)
        await self._async_save()
        self._notify()

    async def async_remove_from_queue(self, index: int, slide_id: str) -> None:
        """Remove one hand-added queue item by its visible position."""
        if (
            not 0 <= index < len(self._queued_ids)
            or self._queued_ids[index] != slide_id
        ):
            raise HomeAssistantError("That queue item is no longer available")
        self._queued_ids.pop(index)
        self._sync_pending_queue_head()
        await self._async_save()
        self._notify()

    async def async_clear_queue(self) -> None:
        """Clear every hand-added queue item."""
        if not self._queued_ids:
            return
        self._queued_ids.clear()
        self._sync_pending_queue_head()
        await self._async_save()
        self._notify()

    async def async_reorder_queue(self, ordered_ids: list[str]) -> None:
        """Replace the hand-added order after validating an optimistic reorder."""
        if Counter(ordered_ids) != Counter(self._queued_ids):
            raise HomeAssistantError("The queue changed before it could be reordered")
        self._queued_ids = list(ordered_ids)
        self._sync_pending_queue_head()
        await self._async_save()
        self._notify()

    def _sync_pending_queue_head(self) -> None:
        """Keep a sleeping frame's pending retry aligned with the queue head."""
        if not self._pending_from_queue:
            return
        queued = self.queued_slides
        if queued:
            self._pending = queued[0]
            catalog_ids = {screen.screen_id for screen in self.screens}
            self._pending_hold_on_success = self._pending.screen_id not in catalog_ids
            return
        self._pending = None
        self._pending_from_queue = False
        self._pending_hold_on_success = False

    async def async_reorder_upcoming(self, ordered_ids: list[str]) -> None:
        """Reorder the visible playlist window while keeping hidden slides stable."""
        if self.shuffle:
            raise HomeAssistantError("A shuffled playlist cannot be reordered")
        expected = [
            slide.screen_id
            for slide in self.playlist_up_next(limit=len(ordered_ids))
        ]
        if Counter(ordered_ids) != Counter(expected):
            raise HomeAssistantError(
                "The playlist changed before it could be reordered"
            )
        by_id = {screen.screen_id: screen for screen in self.screens}
        positions = {
            screen.screen_id: index for index, screen in enumerate(self.screens)
        }
        if self._playlists is not None and self.playlist_id is not None:
            await self._playlists.async_reorder(self.playlist_id, ordered_ids)
        reordered = list(self.screens)
        for expected_id, ordered_id in zip(expected, ordered_ids, strict=True):
            reordered[positions[expected_id]] = by_id[ordered_id]
        self.screens = reordered
        self._playback_order = [screen.screen_id for screen in self.screens]
        self._playlist_order = [screen.screen_id for screen in self.screens]
        await self._async_save()
        self._notify()

    async def async_refresh_playlist(
        self, *, reset: bool = False, start: bool = False
    ) -> None:
        """Apply catalog assignment/settings changes to this frame scheduler."""
        if self._playlists is None:
            return
        self._load_assigned_playlist()
        valid_ids = {screen.screen_id for screen in self.screens}
        self._queued_ids = [
            slide_id
            for slide_id in self._queued_ids
            if self._slide_by_id(slide_id) is not None
        ]
        if reset or self.current_id not in valid_ids:
            self.current_id = None
            self._playlist_cursor_id = None
            self._last_rotation = None
            self.displayed_hash = None
            self._pending = None
            self._pending_from_queue = False
            self._pending_hold_on_success = False
        elif self._pending is not None:
            replacement = self._slide_by_id(self._pending.screen_id)
            if replacement is None:
                self._pending = None
                self._pending_from_queue = False
                self._pending_hold_on_success = False
            else:
                self._pending = replacement
        if start:
            self.enabled = True
            self._stored_enabled = True
            self._hold_until = None
        await self._async_save()
        self._notify()
        if start and self.screens:
            await self._async_rotate(force=True)

    def _apply_playlist_order(self) -> None:
        """Apply the persisted order and append newly created slides."""
        if not self._playlist_order:
            return
        positions = {
            slide_id: index for index, slide_id in enumerate(self._playlist_order)
        }
        fallback = len(positions)
        self.screens.sort(
            key=lambda screen: positions.get(screen.screen_id, fallback)
        )

    # -- external-upload interplay ------------------------------------------

    @callback
    def begin_external_upload(self) -> None:
        """A manual upload is starting; keep playlist work out of the way."""
        if self._external_upload_count == 0:
            self._external_upload_started_at = time.time()
        self._external_upload_count += 1
        self._notify()

    @callback
    def finish_external_upload(self, *, uploaded: bool, hold: bool = True) -> None:
        self._external_upload_count = max(0, self._external_upload_count - 1)
        if self._external_upload_count == 0:
            self._external_upload_started_at = None
        if uploaded:
            self.notify_external_upload(hold=hold)
        else:
            self._notify()

    @callback
    def notify_external_upload(self, *, hold: bool = True) -> None:
        """A manual upload put unknown content on the glass.

        Hold the playlist for the current screen's interval (so the manual
        image gets its screen time) and forget the displayed hash so the next
        playlist upload can never be skipped as "unchanged".
        """
        self._pending = None
        self._pending_from_queue = False
        self.displayed_hash = None
        if hold:
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
                or self.displayed_hash is None
                or self._last_rotation is None
                or (dt_util.utcnow() - self._last_rotation).total_seconds()
                >= current.interval
            )
            if not due:
                return
        if self.queued_slides:
            await self._async_show_queued(self.queued_slides[0], manual=False)
            return
        candidate = next_screen(
            self._rotation_screens(), self._playlist_cursor_id or self.current_id, now
        )
        if candidate is None:
            return  # nothing in window right now; leave the frame as-is
        await self._async_show(candidate)

    async def _async_show_queued(
        self, slide: ScreenConfig, *, manual: bool
    ) -> bool:
        """Show the first hand-added slide and consume it only once displayed."""
        self._pending_from_queue = True
        try:
            displayed = await self._async_show(
                slide,
                manual=manual,
                advance_playlist=False,
                hold_on_success=slide.screen_id
                not in {screen.screen_id for screen in self.screens},
            )
        except Exception:
            self._pending_from_queue = False
            raise
        if self._last_show_permanently_rejected:
            await self._async_consume_queued(slide.screen_id)
        elif self._pending is not slide:
            self._pending_from_queue = False
        return displayed

    async def _async_consume_queued(self, slide_id: str) -> None:
        """Consume the first matching queue occurrence after a confirmed display."""
        try:
            self._queued_ids.remove(slide_id)
        except ValueError:
            pass
        self._pending_from_queue = False
        self._pending_hold_on_success = False
        await self._async_save()
        self._notify()

    async def _async_show(
        self,
        screen: ScreenConfig,
        *,
        manual: bool = False,
        clear_hold_on_success: bool | None = None,
        advance_playlist: bool = True,
        hold_on_success: bool = False,
    ) -> bool:
        self._last_show_permanently_rejected = False
        if self._busy or self.external_upload_active:
            if manual:
                self.raise_if_upload_active()
            return False
        if clear_hold_on_success is None:
            clear_hold_on_success = manual
        self._busy = True
        self._busy_started_at = time.time()
        self._sending_slide_name = screen.name
        self._notify()
        try:
            try:
                result = await async_show_screen(
                    self.hass,
                    self.entry,
                    screen,
                    skip_if_hash=self.displayed_hash,
                    hold_playlist=False,
                    trigger=TRIGGER_MANUAL if manual else TRIGGER_PLAYLIST,
                )
            except ArtFetchError as err:
                # The online image source failed — the frame itself is fine. Keep
                # the current slide, back off so the 60 s tick doesn't hammer a
                # struggling API, and leave the sleep-pending machinery alone.
                if manual:
                    raise
                self._pending = None
                _LOGGER.warning(
                    "Playlist: online image for %r unavailable, keeping current "
                    "slide: %s",
                    screen.name,
                    err,
                )
                self._hold_until = dt_util.utcnow() + timedelta(seconds=300)
                return False
            except FrameUploadError as err:
                if self._pending is not screen or manual:
                    self._pending_requires_enabled = not manual
                self._pending = screen
                self._pending_hold_on_success = hold_on_success
                send_queue = getattr(self.entry.runtime_data, "send_queue", None)
                if (
                    manual
                    and send_queue is not None
                    and send_queue.pending is not None
                ):
                    await send_queue.async_discard()
                self.entry.runtime_data.coordinator.async_set_frame_online(False)
                await self._async_save()
                _LOGGER.debug(
                    "Playlist could not show %r (frame asleep?): %s", screen.name, err
                )
                return False
            except HomeAssistantError as err:
                self._pending = None
                self._pending_hold_on_success = False
                if manual:
                    raise
                self._last_show_permanently_rejected = True
                if advance_playlist:
                    self.current_id = screen.screen_id
                    self._playlist_cursor_id = screen.screen_id
                    self._last_rotation = dt_util.utcnow()
                    await self._async_save()
                    self._notify()
                _LOGGER.warning("Playlist skipped %r: %s", screen.name, err)
                return False
            displayed = result.get("displayed", result.get("uploaded", True))
            if not displayed:
                # Power policy/coalescing skipped this redraw. Never claim its hash
                # is on the glass or count the skipped work as a completed rotation.
                _LOGGER.debug(
                    "Playlist deferred %r without changing the display (%s)",
                    screen.name,
                    result.get("skip_reason", "power policy"),
                )
                return False
            self._pending = None
            self._pending_hold_on_success = False
            if self._pending_from_queue:
                try:
                    self._queued_ids.remove(screen.screen_id)
                except ValueError:
                    pass
                self._pending_from_queue = False
            self.current_id = screen.screen_id
            if advance_playlist:
                self._playlist_cursor_id = screen.screen_id
            self.displayed_hash = result.get("content_hash")
            self._last_rotation = dt_util.utcnow()
            if hold_on_success:
                self._hold_until = dt_util.utcnow() + timedelta(
                    seconds=screen.interval
                )
            elif clear_hold_on_success:
                self._hold_until = None
            if not result.get("uploaded", True):
                _LOGGER.debug(
                    "Playlist: %r content unchanged, upload skipped", screen.name
                )
            await self._async_save()
            self._notify()
            return True
        finally:
            self._busy = False
            self._busy_started_at = None
            self._sending_slide_name = None
            self._notify()

    @callback
    def _coordinator_updated(self) -> None:
        """Frame answered a poll — if a push failed while it slept, retry now."""
        if self._can_retry_pending():
            screen = self._pending
            assert screen is not None
            self.entry.async_create_task(
                self.hass,
                self._async_retry_pending(screen),
                "fraimic_playlist_wake_push",
            )

    def _can_retry_pending(self, screen: ScreenConfig | None = None) -> bool:
        return (
            self._pending is not None
            and (screen is None or self._pending is screen)
            and (self.enabled or not self._pending_requires_enabled)
            and self.entry.runtime_data.coordinator.last_update_success
            and not self._busy
            and not self.external_upload_active
        )

    async def _async_retry_pending(self, screen: ScreenConfig) -> None:
        if not self._can_retry_pending(screen):
            return
        pending_requires_enabled = self._pending_requires_enabled
        if pending_requires_enabled and not eligible(screen, dt_util.now()):
            self._pending = None
            await self._async_rotate(force=True)
            return
        pending_from_queue = self._pending_from_queue
        pending_hold_on_success = self._pending_hold_on_success
        displayed = await self._async_show(
            screen,
            manual=False,
            clear_hold_on_success=not pending_requires_enabled,
            advance_playlist=not pending_from_queue and not pending_hold_on_success,
            hold_on_success=pending_hold_on_success,
        )
        if self._last_show_permanently_rejected and pending_from_queue:
            await self._async_consume_queued(screen.screen_id)
        if self._pending is screen:
            self._pending_requires_enabled = pending_requires_enabled
        elif not displayed:
            self._pending_from_queue = False
            self._pending_hold_on_success = False

    async def _async_save(self) -> None:
        data = {
            "enabled": self._stored_enabled,
            "current_screen_id": self.current_id,
            "playlist_cursor_id": self._playlist_cursor_id,
            "displayed_hash": self.displayed_hash,
            "hold_until": self._hold_until.isoformat() if self._hold_until else None,
            "last_rotation": (
                self._last_rotation.isoformat() if self._last_rotation else None
            ),
            "queued_slide_ids": self._queued_ids,
            "pending_queue_id": (
                self._pending.screen_id
                if self._pending_from_queue and self._pending is not None
                else None
            ),
            "pending_requires_enabled": self._pending_requires_enabled,
        }
        if self._playlists is None:
            data["playlist_order"] = [screen.screen_id for screen in self.screens]
        await self._store.async_save(data)
