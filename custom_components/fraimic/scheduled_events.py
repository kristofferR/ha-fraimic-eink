"""Scheduled sends: deliver an image (or activate a scene) at a future time.

One-shot or recurring (daily/weekly/monthly) events, persisted in an HA
``Store`` so they survive restarts. A 60 s tick (the same pattern as the
playlist scheduler) fires whatever is due.

Delivery guarantees, matched to a slow, visibly-redrawing e-ink panel:

- **At-most-once**: the fire is recorded (and persisted) *before* the send,
  so a crash mid-send can never double-redraw on restart.
- One-shot events missed while HA was down fire once on the next tick.
  Missed *recurring* events also fire once, then fast-forward to the next
  occurrence in the future — never N catch-up redraws.
- A fire that targets a sleeping frame flows into the per-frame send queue
  (``send_queue.py``) rather than failing.
- If the target frame/scene/source has been deleted, the event degrades to
  ``target_missing`` instead of erroring forever.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .helpers import loaded_fraimic_entries

_LOGGER = logging.getLogger(__name__)

DATA_SCHEDULED_EVENTS = "scheduled_events"
STORAGE_KEY = f"{DOMAIN}_scheduled_events"
STORAGE_VERSION = 1
TICK_SECONDS = 60

RECURRENCE_NONE = "none"
RECURRENCES = (RECURRENCE_NONE, "daily", "weekly", "monthly")

STATE_PENDING = "pending"
STATE_DONE = "done"
STATE_TARGET_MISSING = "target_missing"


def _next_occurrence(when: datetime, recurrence: str) -> datetime:
    """The occurrence after ``when`` for a recurring event."""
    if recurrence == "daily":
        return when + timedelta(days=1)
    if recurrence == "weekly":
        return when + timedelta(weeks=1)
    # monthly: same day next month, clamped to the month's length.
    month = when.month % 12 + 1
    year = when.year + (when.month == 12)
    for day in range(when.day, when.day - 4, -1):
        try:
            return when.replace(year=year, month=month, day=day)
        except ValueError:
            continue
    raise ValueError(f"Cannot advance {when} monthly")


def get_scheduled_events(hass: HomeAssistant) -> ScheduledEventManager | None:
    """Return the domain's scheduled-event manager, if set up."""
    return hass.data.get(DOMAIN, {}).get(DATA_SCHEDULED_EVENTS)


class ScheduledEventManager:
    """Domain-wide store + ticker for scheduled sends."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._events: dict[str, dict[str, Any]] = {}
        self._unsub_tick: Any = None
        self._firing = False

    async def async_setup(self) -> None:
        data = await self._store.async_load()
        self._events = {e["id"]: e for e in (data or {}).get("events", [])}
        self._unsub_tick = async_track_time_interval(
            self._hass, self._async_tick, timedelta(seconds=TICK_SECONDS)
        )
        # Fire anything missed while HA was down soon after startup.
        self._hass.async_create_task(self._async_fire_due())

    @callback
    def shutdown(self) -> None:
        if self._unsub_tick is not None:
            self._unsub_tick()
            self._unsub_tick = None

    # ----------------------------------------------------------------- CRUD

    async def async_add(
        self,
        *,
        name: str | None,
        when: datetime,
        recurrence: str,
        entry_id: str | None,
        scene: str | None,
        source: dict[str, Any],
        overrides: dict[str, Any],
    ) -> str:
        event_id = uuid.uuid4().hex[:12]
        self._events[event_id] = {
            "id": event_id,
            "name": name or f"Scheduled send {event_id}",
            "at": dt_util.as_utc(when).isoformat(),
            "recurrence": recurrence,
            "entry_id": entry_id,
            "scene": scene,
            "source": source,
            "overrides": overrides,
            "state": STATE_PENDING,
            "last_fired": None,
        }
        await self._async_save()
        return event_id

    async def async_cancel(self, event_id: str | None) -> int:
        """Cancel one event (or all when ``event_id`` is None). Returns count."""
        if event_id is None:
            count = len(self._events)
            self._events = {}
        else:
            if event_id not in self._events:
                raise ServiceValidationError(f"No scheduled send {event_id}")
            del self._events[event_id]
            count = 1
        await self._async_save()
        return count

    def as_list(self) -> list[dict[str, Any]]:
        return sorted(self._events.values(), key=lambda e: e["at"])

    async def _async_save(self) -> None:
        await self._store.async_save({"events": list(self._events.values())})

    # ----------------------------------------------------------------- tick

    async def _async_tick(self, _now: datetime) -> None:
        await self._async_fire_due()

    async def _async_fire_due(self) -> None:
        if self._firing:
            return
        self._firing = True
        try:
            now = dt_util.utcnow()
            for event_id in list(self._events):
                # Re-fetch each round: async_cancel() may run while an earlier
                # event awaits storage or the send itself.
                event = self._events.get(event_id)
                if event is None or event.get("state") != STATE_PENDING:
                    continue
                when = dt_util.parse_datetime(event["at"])
                if when is None or when > now:
                    continue
                await self._async_fire(event, now)
        finally:
            self._firing = False

    async def _async_fire(self, event: dict[str, Any], now: datetime) -> None:
        """Record the fire, then send. Order matters: at-most-once."""
        recurrence = event.get("recurrence") or RECURRENCE_NONE
        event["last_fired"] = now.isoformat()
        if recurrence == RECURRENCE_NONE:
            event["state"] = STATE_DONE
        else:
            # Fast-forward past any occurrences missed while HA was down.
            when = dt_util.parse_datetime(event["at"]) or now
            while when <= now:
                when = _next_occurrence(when, recurrence)
            event["at"] = when.isoformat()
        await self._async_save()
        if self._events.get(event["id"]) is not event:
            # Cancelled while the fire record was being persisted — a
            # cancellation that already reported success must not redraw.
            return

        try:
            await self._async_send(event)
        except HomeAssistantError as err:
            _LOGGER.warning(
                "Scheduled send %s (%s) failed: %s", event["id"], event["name"], err
            )
        except Exception:  # noqa: BLE001 - a bad event must not kill the ticker
            _LOGGER.exception(
                "Scheduled send %s (%s) failed unexpectedly", event["id"], event["name"]
            )

    async def _async_send(self, event: dict[str, Any]) -> None:
        from .scenes import get_scene_manager  # local import: avoid cycles
        from .services import async_render_and_upload

        if scene_name := event.get("scene"):
            scenes = get_scene_manager(self._hass)
            scene = None
            if scenes is not None:
                try:
                    scene = scenes.get(scene_name)
                except HomeAssistantError:
                    try:
                        scene = scenes.find_by_name(scene_name)
                    except HomeAssistantError:
                        scene = None
            if scene is None:
                await self._async_mark_missing(event, f"scene {scene_name!r} not found")
                return
            await scenes.async_send(scene.scene_id)
            return

        entry = next(
            (
                e
                for e in loaded_fraimic_entries(self._hass)
                if e.entry_id == event.get("entry_id")
            ),
            None,
        )
        if entry is None:
            await self._async_mark_missing(
                event, f"frame {event.get('entry_id')} is not loaded"
            )
            return

        source = event.get("source") or {}
        if image_id := source.get("library_image"):
            from .library import get_library

            library = get_library(self._hass)
            if library is None:
                raise HomeAssistantError("The Fraimic library is not set up")
            try:
                library.get(image_id)
            except HomeAssistantError:
                await self._async_mark_missing(
                    event, f"library image {image_id} no longer exists"
                )
                return
            await library.async_send_to_entry(image_id, entry, dict(event.get("overrides") or {}))
            return

        from .source import async_get_source_bytes

        try:
            raw = await async_get_source_bytes(
                self._hass,
                path=source.get("path"),
                url=source.get("url"),
                entity_id=source.get("image_entity"),
            )
        except ServiceValidationError as err:
            await self._async_mark_missing(event, str(err))
            return
        await async_render_and_upload(
            self._hass,
            entry,
            raw,
            dict(event.get("overrides") or {}),
            hold_playlist=False,
            queue_if_asleep=True,
            title=event["name"],
        )

    async def _async_mark_missing(self, event: dict[str, Any], reason: str) -> None:
        _LOGGER.warning(
            "Scheduled send %s (%s): target missing (%s)",
            event["id"],
            event["name"],
            reason,
        )
        event["state"] = STATE_TARGET_MISSING
        event["error"] = reason
        await self._async_save()
