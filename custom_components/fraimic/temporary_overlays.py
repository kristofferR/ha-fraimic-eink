"""Recompose overlays from the retained panel image without advancing playback."""

from __future__ import annotations

import base64
import json
import logging
import time
from datetime import timedelta

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import CONF_HEIGHT, CONF_ROTATION, CONF_WIDTH, DOMAIN, frame_bin_size
from .overlays import (
    _visible,
    async_apply_frame_overlays,
    get_overlay_manager,
    normalize_overlay,
)
from .power import TRIGGER_OVERLAY

_LOGGER = logging.getLogger(__name__)
MAX_DURATION = 24 * 3600
DEFAULT_REFRESH_INTERVAL = 60


def validate_refresh_interval(value):
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or (value != 0 and not 60 <= value <= 3600)
    ):
        raise ValueError("Refresh interval must be 0 or between 60 and 3600 seconds")
    return value


class TemporaryOverlays:
    """One expiring overlay set per frame, independent of its playback queue.

    Only accepted sends replace the retained base. The packed base is persisted
    with its mount geometry so a restart never needs to refetch random artwork.
    All composition/acceptance operations run under the frame's upload lock.
    """

    def __init__(self, hass, entry):
        self.hass, self.entry = hass, entry
        self._store = Store(hass, 1, f"{DOMAIN}_current_artwork_{entry.entry_id}")
        self.base = None
        self.art = None
        self.title = "Artwork"
        self.inherit = True
        self.temporary = []
        self.expires_at = 0.0
        self.refresh_interval = DEFAULT_REFRESH_INTERVAL
        self.composed_valid_until = None
        self._saved_composed_valid_until = None
        self._next_refresh_at = 0.0
        self.last_signature = ""
        self.submitted_hash = None
        self.submitted_via_cloud = False
        self.dirty = False
        self._refreshing = False
        self._retry_at = 0.0
        self._unsub = None

    def _geometry(self):
        return [
            self.entry.data[CONF_WIDTH],
            self.entry.data[CONF_HEIGHT],
            self.entry.options.get(CONF_ROTATION, 0),
        ]

    async def async_setup(self):
        saved = await self._store.async_load() or {}
        if saved.get("geometry") != self._geometry():
            return
        try:
            packed = base64.b64decode(saved.get("base", ""), validate=True)
            if len(packed) != frame_bin_size(*self._geometry()[:2]):
                return
            from .image_convert import bin_to_png

            width, height, rotation = self._geometry()
            png = await self.hass.async_add_executor_job(
                bin_to_png, packed, width, height, (-rotation) % 360
            )
            self.base = (packed, png, saved.get("mode", "none"))
            self.temporary = [
                normalize_overlay(item) for item in saved.get("temporary", [])
            ]
            self.expires_at = float(saved.get("expires_at", 0))
            self.refresh_interval = validate_refresh_interval(
                saved.get("refresh_interval", DEFAULT_REFRESH_INTERVAL)
            )
            deadline = saved.get("composed_valid_until")
            self.composed_valid_until = (
                float(deadline) if deadline is not None else None
            )
            self._saved_composed_valid_until = self.composed_valid_until
            self._next_refresh_at = float(saved.get("next_refresh_at", 0))
        except (ValueError, TypeError, KeyError):
            _LOGGER.warning(
                "Ignoring invalid retained artwork for %s", self.entry.entry_id
            )
            self.base = None
            return
        self.art = saved.get("art")
        self.title = saved.get("title") or "Artwork"
        self.inherit = saved.get("inherit", True)
        self.last_signature = saved.get("signature", "")
        self.submitted_hash = saved.get("submitted_hash")
        self.submitted_via_cloud = saved.get("submitted_via_cloud", False)
        self.dirty = saved.get("dirty", False)

    def start(self):
        self._unsub = async_track_time_interval(
            self.hass, self._async_tick, timedelta(seconds=30)
        )

    def shutdown(self):
        if self._unsub:
            self._unsub()
            self._unsub = None

    @property
    def active(self):
        return bool(self.temporary) and time.time() < self.expires_at

    @property
    def holds_playback(self):
        return (
            self.active
            or self.dirty
            or (self.base is not None and self.signature() != self.last_signature)
        )

    def visible(self, inherit=None):
        manager = get_overlay_manager(self.hass)
        permanent = (
            manager.for_frame(self.entry.entry_id)
            if manager and (self.inherit if inherit is None else inherit)
            else []
        )
        # Earlier entries render on top of later entries in the compositor.
        overlays = [*(self.temporary if self.active else []), *permanent]
        now = dt_util.now()
        return [item for item in overlays if _visible(self.hass, item, now)]

    def signature(self, inherit=None):
        # Configuration/visibility changes are immediate. While active, the
        # refresh timer also reads live widget data; delivery deduplicates pixels.
        return json.dumps(self.visible(inherit), sort_keys=True)

    async def async_compose(self, base, art=None, inherit=True):
        self.composed_valid_until = None
        overlays = self.visible(inherit)
        signature = json.dumps(overlays, sort_keys=True)
        if not overlays:
            return base, signature, 0
        from .render.display import _NEUTRAL_OVERRIDES
        from .services import async_convert_for_entry

        from .image_convert import bin_to_png

        # Library previews can be thumbnails. Decode the exact panel pixels so
        # changing overlays cannot resize or soften the already-dithered art.
        width, height, rotation = self._geometry()
        png = await self.hass.async_add_executor_job(
            bin_to_png, base[0], width, height, (-rotation) % 360
        )
        deadlines = []
        composed, count = await async_apply_frame_overlays(
            self.hass, self.entry, png, art, overlays=overlays,
            snapshot_deadlines=deadlines,
        )
        self.composed_valid_until = min(deadlines) if deadlines else None
        rendered = await async_convert_for_entry(
            self.hass, self.entry, composed, _NEUTRAL_OVERRIDES, preprocess=False
        )
        return rendered, signature, count

    async def async_accept(
        self, base, art, title, inherit, signature, content_hash, *, via_cloud=False
    ):
        title = title or "Artwork"
        active = self.active
        dirty = self.signature(inherit) != signature
        temporary = self.temporary if active else []
        expires_at = self.expires_at if active else 0
        unchanged = (
            self.base == base
            and self.art == art
            and self.title == title
            and self.inherit == inherit
            and self.last_signature == signature
            and self.submitted_hash == content_hash
            and self.submitted_via_cloud == via_cloud
            and self.dirty == dirty
            and self.temporary == temporary
            and self.expires_at == expires_at
            and self.composed_valid_until == self._saved_composed_valid_until
        )
        self.base, self.art, self.title, self.inherit = (
            base,
            art,
            title,
            inherit,
        )
        self.last_signature = signature
        self.submitted_hash = content_hash
        self.submitted_via_cloud = via_cloud
        self.dirty = dirty
        self.temporary = temporary
        self.expires_at = expires_at
        if not unchanged:
            await self._async_save()

    async def async_mark_dirty(self):
        """Persist that the retained artwork needs fresh composition."""
        self.dirty = True
        self._next_refresh_at = 0
        await self._async_save()

    async def _async_save(self):
        encoded = (
            await self.hass.async_add_executor_job(
                lambda: base64.b64encode(self.base[0]).decode()
            )
            if self.base
            else ""
        )
        await self._store.async_save(
            {
                "geometry": self._geometry(),
                "base": encoded,
                "mode": self.base[2] if self.base else "none",
                "art": self.art,
                "title": self.title,
                "inherit": self.inherit,
                "temporary": self.temporary,
                "expires_at": self.expires_at,
                "refresh_interval": self.refresh_interval,
                "composed_valid_until": self.composed_valid_until,
                "next_refresh_at": self._next_refresh_at,
                "signature": self.last_signature,
                "submitted_hash": self.submitted_hash,
                "submitted_via_cloud": self.submitted_via_cloud,
                "dirty": self.dirty,
            }
        )
        self._saved_composed_valid_until = self.composed_valid_until

    async def async_show(
        self,
        overlays,
        duration,
        *,
        preview_only=False,
        refresh_interval=DEFAULT_REFRESH_INTERVAL,
    ):
        if not overlays or len(overlays) > 12:
            raise HomeAssistantError("Choose between one and twelve overlays")
        if isinstance(duration, bool) or not 1 <= duration <= MAX_DURATION:
            raise HomeAssistantError("Duration must be between 1 and 86400 seconds")
        normalized = [normalize_overlay(item) for item in overlays]
        refresh_interval = validate_refresh_interval(refresh_interval)
        async with self.entry.runtime_data.upload_lock:
            if self.base is None:
                raise HomeAssistantError(
                    "The clean artwork is unavailable. Show a picture through Fraimic first."
                )
            previous = (
                self.temporary,
                self.expires_at,
                self.composed_valid_until,
            )
            self.temporary, self.expires_at = normalized, time.time() + duration
            if preview_only:
                try:
                    rendered, _, count = await self.async_compose(
                        self.base, self.art, self.inherit
                    )
                    from .render.display import _set_screen_preview

                    _set_screen_preview(
                        self.entry.runtime_data, rendered[1], rendered[2]
                    )
                    return {
                        "uploaded": False,
                        "preview_only": True,
                        "overlay_count": count,
                    }
                finally:
                    (
                        self.temporary,
                        self.expires_at,
                        self.composed_valid_until,
                    ) = previous
            self.dirty = True
            self.refresh_interval = refresh_interval
            self._next_refresh_at = 0
            await self._async_save()
        return await self.async_refresh()

    async def async_update(self, overlays=None):
        """Replace supplied content or reread live widgets without renewing expiry.

        Literal text is a snapshot, so HA can replace it through this action.
        Entity-backed widgets and templates are reread automatically.
        """
        if overlays is not None and (not overlays or len(overlays) > 12):
            raise HomeAssistantError("Choose between one and twelve overlays")
        normalized = (
            [normalize_overlay(item) for item in overlays]
            if overlays is not None
            else None
        )
        async with self.entry.runtime_data.upload_lock:
            if not self.active:
                return {"uploaded": False, "active": False}
            if normalized is not None:
                self.temporary = normalized
            self.dirty = True
            await self._async_save()
        if time.time() < max(self._retry_at, self._next_refresh_at):
            return {"uploaded": False, "deferred": True, "active": True}
        return await self.async_refresh()

    async def async_clear(self):
        async with self.entry.runtime_data.upload_lock:
            self.temporary = []
            self.expires_at = 0
            self.dirty = (
                self.base is not None and self.signature() != self.last_signature
            )
            await self._async_save()
        return await self.async_refresh() if self.dirty else {"uploaded": False}

    async def async_refresh(self):
        runtime = self.entry.runtime_data
        scheduler = runtime.scheduler
        if self._refreshing or (
            scheduler and (scheduler.busy or scheduler.external_upload_active)
        ):
            await self.async_mark_dirty()
            return {"uploaded": False, "deferred": True}
        if self.base is None:
            raise HomeAssistantError(
                "The clean artwork is unavailable. Show a picture through Fraimic first."
            )
        from .services import async_render_and_upload

        self._refreshing = True
        self._next_refresh_at = time.time() + max(60, self.refresh_interval)
        if scheduler:
            scheduler.begin_external_upload()
        failed = False
        try:
            # Read the retained base under the upload lock, after any preceding
            # manual artwork change. Never queue a time-sensitive rendered image.
            result = await async_render_and_upload(
                self.hass,
                self.entry,
                b"",
                hold_playlist=False,
                trigger=TRIGGER_OVERLAY,
                overlay_refresh=True,
            )
            if (
                not result.get("displayed")
                and not result.get("cloud_queued")
                and not result.get("unchanged")
            ):
                self.dirty = True
            return {key: value for key, value in result.items() if key != "preview_png"}
        except HomeAssistantError:
            self.dirty = True
            failed = True
            raise
        finally:
            self._retry_at = time.time() + 60
            if failed:
                self._next_refresh_at = self._retry_at
            self._refreshing = False
            if scheduler:
                scheduler.finish_external_upload(uploaded=False, hold=False)

    async def _async_tick(self, _now=None):
        now = time.time()
        expired = bool(self.temporary) and now >= self.expires_at
        if (
            self.base is None
            or self._refreshing
            or (now < self._retry_at and not expired)
        ):
            return
        changed = self.signature() != self.last_signature
        briefing_due = (
            self.composed_valid_until is not None
            and now >= self.composed_valid_until
        )
        refresh_due = (
            self.active
            and (
                briefing_due
                or (self.refresh_interval and now >= self._next_refresh_at)
            )
        )
        # Content updates coalesce until the next refresh. Expiry/visibility
        # changes still remove the overlay even with periodic refresh disabled.
        if (
            self.active
            and now < self._next_refresh_at
            and not briefing_due
            and not changed
        ):
            return
        if not self.dirty and not changed and not refresh_due:
            return
        try:
            await self.async_refresh()
        except HomeAssistantError as err:
            _LOGGER.debug(
                "Overlay refresh deferred for %s: %s", self.entry.entry_id, err
            )

    async def async_recompose_pending(self, pending):
        """Refresh a queued composite at delivery time, including after expiry."""
        if self.base is None or pending.get("content_hash") != self.submitted_hash:
            return None
        rendered, signature, count = await self.async_compose(
            self.base, self.art, self.inherit
        )
        return rendered, signature, count

    async def async_invalidate(self):
        """An untracked device refresh replaced the retained artwork."""
        async with self.entry.runtime_data.upload_lock:
            queue = getattr(self.entry.runtime_data, "send_queue", None)
            if (
                queue is not None
                and queue.pending
                and queue.pending.get("content_hash") == self.submitted_hash
            ):
                await queue.async_discard()
            self.base = None
            self.submitted_hash = None
            self.submitted_via_cloud = False
            self.dirty = False
            self.temporary = []
            self.expires_at = 0
            await self._async_save()
