"""Persistent per-frame playback queue and battery-aware delivery."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import CONF_PLAYLIST_PREFETCH, DEFAULT_PLAYLIST_PREFETCH, DOMAIN
from .coordinator import FraimicConfigEntry
from .playback_queue import PlaybackQueue, QueueItem
from .power import TRIGGER_MANUAL, TRIGGER_PLAYLIST
from .providers.ha import ArtFetchError
from .render.display import (
    async_show_screen,
    discard_prepared_thumbnails,
    prepared_thumbnail_fingerprint,
)
from .render.playlist import eligible
from .render.schema import KIND_PICTURE, MIN_SCREEN_INTERVAL, ScreenConfig
from .screens import screens_from_entry
from .services import CloudDeliveryError, FrameUploadError

if TYPE_CHECKING:
    from .playlists import PlaylistManager

_LOGGER = logging.getLogger(__name__)
TICK = timedelta(seconds=60)
STORE_VERSION = 1


class FraimicScheduler:
    """Owns playback; playlists are only sources of queue snapshots."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: FraimicConfigEntry,
        playlists: PlaylistManager | None = None,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self._playlists = playlists
        self.queue = PlaybackQueue()
        self.enabled = False
        self._stored_enabled = False
        self.current_id: str | None = None
        self._displayed_item: QueueItem | None = None
        self.displayed_hash: str | None = None
        self._last_rotation: datetime | None = None
        self._paused_at: datetime | None = None
        self._hold_until: datetime | None = None
        self._pending: ScreenConfig | None = None
        self._pending_requires_enabled = True
        self._pending_hold_on_success = False
        self._external_upload_count = 0
        self._external_upload_started_at: float | None = None
        self._busy = False
        self._busy_started_at: float | None = None
        self._sending_slide_name: str | None = None
        self.sending_screen: ScreenConfig | None = None
        self.blocked_reason: str | None = None
        self.retry_at: datetime | None = None
        self._store: Store[dict[str, Any]] = Store(
            hass, STORE_VERSION, f"{DOMAIN}_playlist_{entry.entry_id}"
        )
        self._unsub_timer: Callable[[], None] | None = None
        self._unsub_coordinator: Callable[[], None] | None = None
        self._listeners: list[Callable[[], None]] = []
        self._prefetch_task: asyncio.Task | None = None
        self._prefetch_again = False
        self._playlist_preprocess_done: str | None = None

    @property
    def screens(self) -> list[ScreenConfig]:
        return [item.screen for item in self.queue.items]

    @property
    def shuffle(self) -> bool:
        return self.queue.shuffle

    @property
    def playlist_id(self) -> str | None:
        item = self.queue.get(self.queue.cursor)
        return item.playlist_id if item else None

    @property
    def playlist_name(self) -> str | None:
        item = self.queue.get(self.queue.cursor)
        return item.playlist_name if item else None

    @property
    def playlist_interval(self) -> int:
        return self.queue.interval

    @property
    def queued_slides(self) -> list[ScreenConfig]:
        return [item.screen for item in self.queue.upcoming]

    @property
    def current_screen(self) -> ScreenConfig | None:
        return self._displayed_item.screen if self._displayed_item else None

    @property
    def exhausted(self) -> bool:
        return not self.queue.upcoming and not (
            self.queue.repeat and any(item.screen.enabled for item in self.queue.items)
        )

    def slide_by_id(self, slide_id: str) -> ScreenConfig | None:
        item = self.queue.get(slide_id)
        if item:
            return item.screen
        if self.current_id == slide_id:
            return self.current_screen
        if self._playlists is not None:
            return self._playlists.render_slide_by_id(slide_id)
        return None

    def playlist_up_next(self, *, limit: int | None = 10) -> list[ScreenConfig]:
        """Legacy callers must not append a second playback source."""
        return []

    async def async_start(self) -> None:
        data = await self._store.async_load() or {}
        self.enabled = self._stored_enabled = bool(data.get("enabled", False))
        if "playback_queue" in data:
            self.queue = PlaybackQueue.from_dict(data["playback_queue"])
            if data.get("displayed_item"):
                self._displayed_item = QueueItem.from_dict(data["displayed_item"])
        else:
            self._migrate_queue(data)
        self.current_id = self.current_screen.screen_id if self.current_screen else None
        self.displayed_hash = data.get("displayed_hash")
        for attr, key in (
            ("_hold_until", "hold_until"),
            ("_last_rotation", "last_rotation"),
            ("_paused_at", "paused_at"),
        ):
            if data.get(key):
                setattr(self, attr, dt_util.parse_datetime(data[key]))
        if self.enabled:
            self._paused_at = None
        pending_id = data.get("pending_queue_id")
        self._pending = self.slide_by_id(pending_id) if pending_id else None
        self._pending_requires_enabled = bool(
            data.get("pending_requires_enabled", True)
        )
        await self._async_sync_cloud_interval()
        await self._async_save()
        self._unsub_timer = async_track_time_interval(self.hass, self._async_tick, TICK)
        self._unsub_coordinator = (
            self.entry.runtime_data.coordinator.async_add_listener(
                self._coordinator_updated
            )
        )
        self._schedule_prefetch()

    def _migrate_queue(self, data: dict) -> None:
        """Snapshot the old assigned rotation and its priority queue once."""
        playlist = (
            self._playlists.assigned_to(self.entry.entry_id)
            if self._playlists
            else None
        )
        screens = (
            self._playlists.render_slides(playlist.playlist_id)
            if playlist
            else screens_from_entry(self.entry)
        )
        lookup = {screen.screen_id: screen for screen in screens}
        from .render.schema import SCREEN_SCHEMA, screen_from_dict

        for item_id, raw in data.get("external_queue", {}).items():
            try:
                lookup[item_id] = screen_from_dict(SCREEN_SCHEMA(raw), item_id)
            except (ValueError, TypeError, KeyError):
                _LOGGER.warning("Ignoring invalid legacy queue item %s", item_id)

        def resolve(item_id):
            return lookup.get(item_id) or (
                self._playlists.render_slide_by_id(item_id)
                if self._playlists and item_id
                else None
            )

        order = (
            (data.get("session") or {}).get("order")
            or data.get("playlist_order")
            or [screen.screen_id for screen in screens]
        )
        cursor = data.get("playlist_cursor_id", data.get("current_screen_id"))
        if cursor in order:
            at = order.index(cursor)
            order = order[at + 1 :] + order[:at]
        current = resolve(data.get("current_screen_id"))
        origin = (
            {"playlist_id": playlist.playlist_id, "playlist_name": playlist.name}
            if playlist
            else {}
        )
        pending_id = data.get("pending_queue_id")
        if current:
            item = self.queue.add([current], **origin)[0]
            self.queue.cursor = item.screen.screen_id
            self._displayed_item = item
            if pending_id == data.get("current_screen_id"):
                data["pending_queue_id"] = self.queue.cursor
                pending_id = None
        for item_id in [*data.get("queued_slide_ids", []), *order]:
            screen = resolve(item_id)
            if screen:
                item = self.queue.add([screen], **origin)[0]
                if item_id == pending_id:
                    data["pending_queue_id"] = item.screen.screen_id
                    pending_id = None
        if playlist:
            self.queue.interval = playlist.interval
            self.queue.shuffle = playlist.shuffle
        elif screens:
            self.queue.interval = screens[0].interval
        self.queue.repeat = bool(screens)

    @callback
    def async_stop(self) -> None:
        if self._unsub_timer is not None:
            self._unsub_timer()
            self._unsub_timer = None
        if self._unsub_coordinator is not None:
            self._unsub_coordinator()
            self._unsub_coordinator = None
        if self._prefetch_task is not None:
            self._prefetch_task.cancel()
            self._prefetch_task = None
        discard_prepared_thumbnails(self.hass, entry_id=self.entry.entry_id)

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
        if self._last_rotation is not None and self._paused_at is not None:
            return self._last_rotation + (dt_util.utcnow() - self._paused_at)
        return self._last_rotation

    @property
    def hold_until(self) -> datetime | None:
        """When a one-off manual display stops holding rotation."""
        return self._hold_until

    def raise_if_upload_active(self) -> None:
        if self._busy or self.external_upload_active:
            raise HomeAssistantError("An upload is already in progress")

    async def _queue_changed(self) -> None:
        if self._pending is not None:
            candidate = (
                self.queue.candidate(dt_util.now())
                if self._pending_requires_enabled
                else self.queue.get(self._pending.screen_id)
            )
            self._pending = candidate.screen if candidate else None
        self.blocked_reason = None
        self.retry_at = None
        await self._async_save()
        self._notify()
        self._schedule_prefetch()

    async def async_add_to_queue(
        self,
        slide: ScreenConfig,
        *,
        play_next: bool = False,
        insert_at: int | None = None,
        raw_data: dict | None = None,
    ) -> None:
        self.raise_if_upload_active()
        if insert_at is not None and (
            isinstance(insert_at, bool) or not isinstance(insert_at, int)
        ):
            raise HomeAssistantError("Queue position must be a number")
        self.queue.add(
            [slide],
            index=insert_at if insert_at is not None else (0 if play_next else None),
        )
        await self._queue_changed()

    async def async_enqueue_playlist(self, playlist_id: str, *, action: str) -> None:
        self.raise_if_upload_active()
        playlist = self._playlists.require(playlist_id)
        screens = self._playlists.render_slides(playlist_id)
        if not screens:
            raise HomeAssistantError("This playlist is empty")
        if action == "play":
            self.queue = PlaybackQueue(
                interval=self.queue.interval,
                shuffle=self.queue.shuffle,
                repeat=self.queue.repeat,
            )
            self._pending = None
            self._last_rotation = None
            self.enabled = self._stored_enabled = True
            self._paused_at = None
            self._hold_until = None
        self.queue.add(
            screens,
            index=0 if action == "play_next" else None,
            playlist_id=playlist_id,
            playlist_name=playlist.name,
        )
        if action == "play" and self.queue.shuffle:
            self.queue.set_shuffle(True)
        await self._queue_changed()
        if action == "play":
            await self.async_next()

    async def async_set_playback(
        self,
        *,
        interval: int | None = None,
        shuffle: bool | None = None,
        repeat: bool | None = None,
    ) -> None:
        self.raise_if_upload_active()
        if interval is not None:
            if (
                isinstance(interval, bool)
                or not isinstance(interval, int)
                or interval < MIN_SCREEN_INTERVAL
            ):
                raise HomeAssistantError(
                    f"Interval must be at least {MIN_SCREEN_INTERVAL} seconds"
                )
            self.queue.interval = interval
            await self._async_sync_cloud_interval()
        if shuffle is not None:
            if not isinstance(shuffle, bool):
                raise HomeAssistantError("Shuffle must be a boolean")
            self.queue.set_shuffle(shuffle)
        if repeat is not None:
            if not isinstance(repeat, bool):
                raise HomeAssistantError("Repeat must be a boolean")
            self.queue.repeat = repeat
        await self._queue_changed()

    async def async_remove_from_queue(self, index: int, slide_id: str) -> None:
        self.raise_if_upload_active()
        try:
            self.queue.remove(index, slide_id)
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err
        await self._queue_changed()

    async def async_clear_queue(self) -> None:
        self.raise_if_upload_active()
        self.queue.clear()
        await self._queue_changed()

    async def async_reorder_queue(self, ordered_ids: list[str]) -> None:
        self.raise_if_upload_active()
        try:
            self.queue.reorder(ordered_ids)
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err
        await self._queue_changed()

    async def async_play_queue_item(
        self, section: str, index: int, slide_id: str
    ) -> None:
        self.raise_if_upload_active()
        upcoming = self.queue.upcoming
        if (
            section != "queue"
            or not 0 <= index < len(upcoming)
            or upcoming[index].screen.screen_id != slide_id
        ):
            raise HomeAssistantError("That queue item is no longer available")
        await self._async_show(upcoming[index].screen, manual=True)

    async def async_prune_library_image(self, image_id: str) -> bool:
        removed = {
            item.screen.screen_id
            for item in self.queue.items
            if (item.screen.source or {}).get("library_image") == image_id
        }
        if not removed:
            return False
        position = self.queue.position
        previous = self.queue.items[: position + 1]
        self.queue.items = [
            item for item in self.queue.items if item.screen.screen_id not in removed
        ]
        if self.queue.cursor in removed:
            self.queue.cursor = next(
                (
                    item.screen.screen_id
                    for item in reversed(previous)
                    if item.screen.screen_id not in removed
                ),
                None,
            )
        await self._queue_changed()
        return True

    async def async_refresh_playlist(
        self, *, reset: bool = False, start: bool = False
    ) -> None:
        """Catalog edits do not mutate snapshots already in playback."""
        self.invalidate_preprocessing()

    async def async_next(self) -> bool:
        self.raise_if_upload_active()
        candidate = self.queue.candidate(dt_util.now())
        if candidate is None:
            return False
        return await self._async_show(candidate.screen, manual=True)

    async def async_previous(self) -> bool:
        self.raise_if_upload_active()
        candidate = self.queue.candidate(dt_util.now(), previous=True)
        if candidate is None:
            return False
        return await self._async_show(candidate.screen, manual=True)

    async def async_select(self, screen: ScreenConfig, *, hold: bool = False) -> None:
        self.raise_if_upload_active()
        if self.queue.get(screen.screen_id) is None:
            screen = self.queue.add([screen], index=0)[0].screen
            await self._async_save()
        await self._async_show(screen, manual=True, hold_on_success=hold)

    async def async_set_enabled(
        self,
        enabled: bool,
        *,
        rotate: bool = True,
        clear_hold: bool = True,
        persist: bool = True,
    ) -> None:
        restart = enabled and rotate and self.exhausted and bool(self.queue.items)
        if restart:
            self.queue.cursor = None
            self._last_rotation = None
        changed = enabled != self.enabled or restart
        hold_changed = clear_hold and self._hold_until is not None
        if persist:
            self._stored_enabled = enabled
        if not changed and not hold_changed:
            if persist:
                await self._async_save()
            return
        now = dt_util.utcnow()
        if changed and not enabled:
            self._paused_at = now
        elif changed and enabled and self._paused_at is not None:
            if self._last_rotation is not None:
                self._last_rotation += now - self._paused_at
            self._paused_at = None
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

    async def _async_sync_cloud_interval(self) -> None:
        """Cloud delivery: the album slot cadence must follow the playlist."""
        cloud = getattr(self.entry.runtime_data, "cloud", None)
        if cloud is None:
            return
        try:
            await cloud.async_sync_interval(self.playlist_interval)
            if cloud.delivery_deadline is not None:
                self._hold_until = dt_util.utc_from_timestamp(cloud.delivery_deadline)
        except Exception:
            _LOGGER.debug("Cloud album interval sync failed", exc_info=True)

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
        became_idle = self._external_upload_count == 0
        if became_idle:
            self._external_upload_started_at = None
        if uploaded:
            self.notify_external_upload(hold=hold)
        else:
            self._notify()
        if became_idle:
            self._schedule_prefetch()

    @callback
    def notify_external_upload(self, *, hold: bool = True) -> None:
        """A manual upload put unknown content on the glass.

        Hold the playlist for the current screen's interval (so the manual
        image gets its screen time) and forget the displayed hash so the next
        playlist upload can never be skipped as "unchanged".
        """
        self._mark_external_upload(hold=hold)
        self.entry.async_create_task(
            self.hass, self._async_save(), "fraimic_playlist_external_save"
        )
        self._notify()

    def _mark_external_upload(self, *, hold: bool) -> None:
        """Reset scheduler state after external content reaches the frame."""
        self._pending = None
        self._pending_hold_on_success = False
        self.displayed_hash = None
        if hold:
            interval = self.queue.interval
            self._hold_until = dt_util.utcnow() + timedelta(seconds=interval)

    async def async_notify_external_upload(self, *, hold: bool = True) -> None:
        """Durably record a deferred external delivery."""
        self._mark_external_upload(hold=hold)
        await self._async_save()
        self._notify()

    async def async_discard_pending_retry(self) -> None:
        """Let a newer direct send supersede an older scheduler retry."""
        if self._pending is None:
            return
        self._pending = None
        self._pending_hold_on_success = False
        await self._async_save()
        self._notify()

    async def async_cloud_delivery_accepted(self) -> None:
        """Reserve the cloud wake slot without claiming the image is on glass."""
        cloud = self.entry.runtime_data.cloud
        self._pending = None
        self._pending_hold_on_success = False
        # Every album edit reanchors the wake. Allow the scheduled slot to pass
        # before the next automatic upload replaces its image.
        self._hold_until = dt_util.utcnow() + timedelta(
            seconds=cloud.wake_interval + 60
        )
        if getattr(cloud, "delivery_deadline", None) is not None:
            self._hold_until = dt_util.utc_from_timestamp(cloud.delivery_deadline)
        await self._async_save()
        self._notify()

    async def _async_tick(self, _now: datetime | None = None) -> None:
        runtime = self.entry.runtime_data
        cloud = getattr(runtime, "cloud", None)
        if cloud is not None and not self._busy and not self.external_upload_active:
            try:
                async with runtime.upload_lock:
                    await cloud.async_expire_delivery()
            except Exception:
                _LOGGER.debug("Could not retire the cloud image", exc_info=True)
        await self._async_rotate(force=False)

    async def _async_rotate(self, *, force: bool) -> None:
        if (
            not self.enabled
            or self._busy
            or self.external_upload_active
            or self.exhausted
        ):
            return
        now = dt_util.utcnow()
        if not force:
            if self._pending is not None or (
                self._hold_until and now < self._hold_until
            ):
                return
            if self.retry_at and now < self.retry_at:
                return
            if (
                self._last_rotation
                and (self.current_screen is None or eligible(self.current_screen, dt_util.now()))
                and (now - self._last_rotation).total_seconds() < self.queue.interval
            ):
                return
        candidate = self.queue.candidate(dt_util.now())
        if candidate:
            await self._async_show(candidate.screen)

    def _defer(self, reason: str, seconds: int | None = None) -> None:
        self.blocked_reason = reason
        if seconds is not None:
            self.retry_at = dt_util.utcnow() + timedelta(seconds=seconds)
        else:
            power = self.entry.runtime_data.power
            retry = power.retry_at(reason)
            self.retry_at = dt_util.utc_from_timestamp(retry) if retry else None
        self._notify()

    async def _async_show(
        self,
        screen: ScreenConfig,
        *,
        manual: bool = False,
        hold_on_success: bool = False,
    ) -> bool:
        if self._busy or self.external_upload_active:
            if manual:
                self.raise_if_upload_active()
            return False
        self._busy = True
        self._busy_started_at = time.time()
        self._sending_slide_name = screen.name
        self.sending_screen = screen
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
            except (ArtFetchError, CloudDeliveryError) as err:
                self._pending = None
                self._defer(
                    "source_unavailable"
                    if isinstance(err, ArtFetchError)
                    else "cloud_unavailable",
                    300,
                )
                if manual:
                    raise
                _LOGGER.warning("Queue could not show %r: %s", screen.name, err)
                return False
            except FrameUploadError:
                send_queue = getattr(self.entry.runtime_data, "send_queue", None)
                if send_queue is not None and send_queue.pending is not None:
                    if not manual:
                        self._pending = None
                        return False
                    await send_queue.async_discard()
                self._pending = screen
                self._pending_requires_enabled = not manual
                self._pending_hold_on_success = hold_on_success
                self.blocked_reason = "asleep"
                self.entry.runtime_data.coordinator.async_set_frame_online(False)
                await self._async_save()
                return False
            except HomeAssistantError as err:
                self._pending = None
                if manual:
                    await self._async_save()
                    raise
                # A permanently invalid item must not block the remaining queue.
                if item := self.queue.get(screen.screen_id):
                    self.queue.items.remove(item)
                    if self.queue.cursor == screen.screen_id:
                        self.queue.cursor = None
                if self.exhausted:
                    self.blocked_reason = None
                    self.retry_at = None
                else:
                    self._defer("invalid_item", 60)
                await self._async_save()
                _LOGGER.warning("Queue skipped %r: %s", screen.name, err)
                return False
            displayed = result.get("displayed", result.get("uploaded", True))
            if not displayed and not result.get("cloud_queued"):
                self._defer(result.get("skip_reason", "power_policy"))
                return False
            self._pending = None
            self._pending_hold_on_success = False
            self.blocked_reason = None
            self.retry_at = None
            self.queue.advance(screen.screen_id, dt_util.now())
            if displayed:
                self._displayed_item = self.queue.get(screen.screen_id)
                self.current_id = screen.screen_id
                self.displayed_hash = result.get("content_hash")
                self._last_rotation = dt_util.utcnow()
                if not self.enabled:
                    self._paused_at = self._last_rotation
                self._hold_until = (
                    dt_util.utcnow() + timedelta(seconds=self.queue.interval)
                    if hold_on_success
                    else None
                )
            await self._async_save()
            self._notify()
            return bool(displayed)
        finally:
            self._busy = False
            self._busy_started_at = None
            self._sending_slide_name = None
            self.sending_screen = None
            self._notify()
            self._schedule_prefetch()

    @callback
    def invalidate_preprocessing(self) -> None:
        """Refresh prepared snapshots after render dependencies change."""
        self._playlist_preprocess_done = None
        self._schedule_prefetch()

    def _prefetch_limit(self) -> int:
        options = getattr(self.entry, "options", {})
        try:
            return int(options.get(CONF_PLAYLIST_PREFETCH, DEFAULT_PLAYLIST_PREFETCH))
        except (TypeError, ValueError):
            return DEFAULT_PLAYLIST_PREFETCH

    def _prefetch_screens(self) -> list[ScreenConfig]:
        """Upcoming hand-queue and playlist pictures in actual play order."""
        limit = self._prefetch_limit()
        if limit <= 0:
            return []
        queued = self.queued_slides
        if not self.enabled and not queued:
            return []
        result: list[ScreenConfig] = []
        seen: set[str] = set()
        candidates = [
            *queued,
            *(self.playlist_up_next(limit=len(self.screens)) if self.enabled else []),
        ]
        for screen in candidates:
            if screen.screen_id in seen or not self._is_preparable_picture(screen):
                continue
            result.append(screen)
            seen.add(screen.screen_id)
            if len(result) >= limit:
                break
        return result

    @staticmethod
    def _is_preparable_picture(screen: ScreenConfig) -> bool:
        source = getattr(screen, "source", None) or {}
        return getattr(screen, "kind", None) == KIND_PICTURE and bool(
            source.get("library_image")
            or (source.get("provider") and source.get("provider_item"))
        )

    def _playlist_preprocess_screens(self) -> list[ScreenConfig]:
        """Every fixed picture in the assigned playlist, once per slide id."""
        signature = self._playlist_preprocess_signature()
        if signature is None or signature == self._playlist_preprocess_done:
            return []
        result: list[ScreenConfig] = []
        seen: set[str] = set()
        for screen in self.queued_slides:
            if screen.screen_id in seen or not self._is_preparable_picture(screen):
                continue
            result.append(screen)
            seen.add(screen.screen_id)
        return result

    def _playlist_preprocess_signature(self) -> str | None:
        """Version the full preparation pass by playlist and render settings."""
        if self._prefetch_limit() <= 0:
            return None
        return json.dumps(
            {
                "playlist": self.playlist_id,
                "slides": [
                    [
                        screen.screen_id,
                        prepared_thumbnail_fingerprint(self.hass, self.entry, screen),
                    ]
                    for screen in self.queued_slides
                    if self._is_preparable_picture(screen)
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )

    def _schedule_prefetch(self) -> None:
        """Start or refresh the single serial preparation worker."""
        if not self._prefetch_screens() and not self._playlist_preprocess_screens():
            return
        if self._prefetch_task is not None and not self._prefetch_task.done():
            self._prefetch_again = True
            return
        create = getattr(self.hass, "async_create_background_task", None)
        if create is None:
            return
        self._prefetch_task = create(
            self._async_prefetch(), name=f"fraimic_prefetch_{self.entry.entry_id}"
        )

    async def _async_prefetch(self) -> None:
        """Prepare fixed upcoming art serially and without touching runtime state."""
        try:
            while True:
                self._prefetch_again = False
                upcoming = self._prefetch_screens()
                full_signature = self._playlist_preprocess_signature()
                full_screens = self._playlist_preprocess_screens()
                prepared_ids = {screen.screen_id for screen in upcoming}
                screens = [
                    *upcoming,
                    *(
                        screen
                        for screen in full_screens
                        if screen.screen_id not in prepared_ids
                    ),
                ]
                for screen in screens:
                    if self._busy or self.external_upload_active:
                        return
                    try:
                        from .render.display import async_prepare_screen

                        await async_prepare_screen(self.hass, self.entry, screen)
                    except asyncio.CancelledError:
                        raise
                    except HomeAssistantError as err:
                        _LOGGER.debug(
                            "Could not prepare playlist picture %r: %s",
                            screen.name,
                            err,
                        )
                    except Exception as err:  # noqa: BLE001 - best-effort preparation
                        _LOGGER.warning(
                            "Preparing playlist picture %r failed unexpectedly: %s",
                            screen.name,
                            err,
                        )
                if full_screens:
                    self._playlist_preprocess_done = full_signature
                if not self._prefetch_again:
                    return
        finally:
            self._prefetch_task = None

    @callback
    def _coordinator_updated(self) -> None:
        if self._can_retry_pending():
            self.entry.async_create_task(
                self.hass,
                self._async_retry_pending(self._pending),
                "fraimic_queue_wake_push",
            )
        # Charging or a changed power profile can release a previously blocked send.
        if self.blocked_reason in {"daily_budget", "cooldown", "low_battery"}:
            battery = (self.entry.runtime_data.coordinator.data or {}).get(
                "battery"
            ) or {}
            if battery.get("charging") or battery.get("cable_connected"):
                self.blocked_reason = None
                self.retry_at = None
                self._notify()

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
        requires_enabled = self._pending_requires_enabled
        if requires_enabled and not eligible(screen, dt_util.now()):
            self._pending = None
            await self._async_rotate(force=True)
            return
        await self._async_show(
            screen,
            manual=not requires_enabled,
            hold_on_success=self._pending_hold_on_success,
        )

    async def _async_save(self) -> None:
        await self._store.async_save(
            {
                "enabled": self._stored_enabled,
                "playback_queue": self.queue.to_dict(),
                "displayed_item": self._displayed_item.to_dict()
                if self._displayed_item
                else None,
                "current_screen_id": self.current_id,
                "displayed_hash": self.displayed_hash,
                "last_rotation": self._last_rotation.isoformat()
                if self._last_rotation
                else None,
                "hold_until": self._hold_until.isoformat()
                if self._hold_until
                else None,
                "paused_at": self._paused_at.isoformat() if self._paused_at else None,
                "pending_queue_id": self._pending.screen_id if self._pending else None,
                "pending_requires_enabled": self._pending_requires_enabled,
            }
        )
