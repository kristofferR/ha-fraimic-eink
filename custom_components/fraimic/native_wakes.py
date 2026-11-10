"""Native wake scheduling for local frames that sleep between art changes.

Firmware 0.2.31 wakes the frame on its own schedule and keeps it reachable
for ``MAX_IDLE`` seconds. Home Assistant picks when art changes, writes that
schedule to the frame whenever it answers, and catches each wake: it probes
from ``CATCH_LEAD`` before the frame's next wake, polls the frame as soon as
it answers (the scheduler and send queue deliver on that poll), then puts it
back to sleep.

Only for local delivery: cloud and the local backend wake the frame through
albums. A schedule set outside Home Assistant is left alone until one is
picked here.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime, timedelta, timezone
from functools import partial
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .api import FraimicApiError, FraimicConnectionError, FraimicError
from .const import DOMAIN
from .wake_schedule import WakeSchedule, art_slots, frame_offset, frame_wakes, matches

if TYPE_CHECKING:
    from collections.abc import Callable

    from .coordinator import FraimicConfigEntry

_LOGGER = logging.getLogger(__name__)
STORE_VERSION = 1
# Probing starts this long before a wake, and art may change from then on.
CATCH_LEAD = timedelta(seconds=30)
# The window closes on time even mid-upload (30-35 s), so stop looking for
# the frame once an upload could no longer finish inside it.
CATCH_END = timedelta(seconds=80)
PROBE_EVERY = 2
PROBE_TIMEOUT = 3
# Consecutive idle seconds, after the wake's poll, before the frame may sleep.
IDLE_SECONDS = 3
SETTLE_LIMIT = 180
MISSES_FOR_ISSUE = 2


class NativeWakes:
    """The frame's wake schedule, as picked in Home Assistant, and its wakes."""

    def __init__(self, hass: HomeAssistant, entry: FraimicConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        # None until the frame answers; False on firmware without the endpoint.
        self.supported: bool | None = None
        self._firmware: str | None = None
        # When art changes, on Home Assistant's clock; None = not managed here.
        self.schedule: WakeSchedule | None = None
        # The frame's last reported schedule (GET/POST reply).
        self.frame: dict[str, Any] | None = None
        # The frame may not have what ``schedule`` asks for yet.
        self.dirty = False
        self.misses = 0
        # {"wake": iso, "at": iso, "outcome": "answered" | "missed"}
        self.last_wake: dict[str, Any] | None = None
        self._store: Store[dict[str, Any]] = Store(
            hass, STORE_VERSION, f"{DOMAIN}_wakes_{entry.entry_id}"
        )
        self._sync_lock = asyncio.Lock()
        self._catching = False
        self._unsub_catch: Callable[[], None] | None = None
        self._unsub_coordinator: Callable[[], None] | None = None

    @property
    def active(self) -> bool:
        """Whether art changes follow the frame's wakes."""
        return self.supported is True and self.schedule is not None

    @property
    def _issue_id(self) -> str:
        return f"wake_missed_{self.entry.entry_id}"

    async def async_setup(self) -> None:
        data = await self._store.async_load() or {}
        self.supported = data.get("supported")
        self._firmware = data.get("firmware")
        if data.get("schedule") is not None:
            try:
                self.schedule = WakeSchedule.from_dict(data["schedule"])
            except ValueError as err:
                _LOGGER.warning("Ignoring an invalid stored wake schedule: %s", err)
        self.frame = data.get("frame")
        self.dirty = bool(data.get("dirty"))
        self.misses = int(data.get("misses") or 0)
        self.last_wake = data.get("last_wake")
        self._unsub_coordinator = self.entry.runtime_data.coordinator.async_add_listener(
            self._coordinator_updated
        )
        self._schedule_catch()
        # The startup poll ran before this listener existed.
        self._coordinator_updated()

    @callback
    def shutdown(self) -> None:
        if self._unsub_catch is not None:
            self._unsub_catch()
            self._unsub_catch = None
        if self._unsub_coordinator is not None:
            self._unsub_coordinator()
            self._unsub_coordinator = None

    async def _async_save(self) -> None:
        await self._store.async_save(
            {
                "supported": self.supported,
                "firmware": self._firmware,
                "schedule": self.schedule.to_dict() if self.schedule else None,
                "frame": self.frame,
                "dirty": self.dirty,
                "misses": self.misses,
                "last_wake": self.last_wake,
            }
        )

    # ------------------------------------------------------------ schedule

    async def async_set_schedule(self, schedule: WakeSchedule | None) -> None:
        """Pick when art changes, or hand timing back to the queue interval."""
        if self.supported is not True:
            raise HomeAssistantError("This frame's firmware has no wake schedule")
        self.schedule = schedule
        self.dirty = True
        await self._async_save()
        if self.entry.runtime_data.coordinator.frame_online:
            await self.async_sync()
        self._schedule_catch()

    def _frame_offset(self) -> int | None:
        offset = frame_offset(self.frame)
        if offset is not None:
            return offset
        data = self.entry.runtime_data.coordinator.data or {}
        value = (data.get("device") or {}).get("utc_offset_minutes")
        return value if isinstance(value, int) else None

    def slots(self, after: datetime, count: int) -> list[datetime]:
        """The next ``count`` times art changes after ``after`` (UTC)."""
        if self.schedule is None or not self.active:
            return []
        offset = self._frame_offset()
        if offset is None:
            # Unknown frame clock: assume Home Assistant's.
            offset = int((dt_util.now().utcoffset() or timedelta()).total_seconds() // 60)
        return art_slots(
            self.schedule,
            after,
            count,
            zone=dt_util.get_default_time_zone(),
            frame_offset=offset,
        )

    def next_change(self, after: datetime) -> datetime | None:
        """When art shown at ``after`` may change: its catch at the next slot.

        A slot whose catch had already begun at ``after`` belongs to that art.
        """
        slots = self.slots(after + CATCH_LEAD, 1)
        return slots[0] - CATCH_LEAD if slots else None

    def _upcoming_wakes(self, after: datetime) -> list[datetime]:
        """The frame's wakes after ``after``: its own list, then its schedule."""
        wakes = [wake for wake in frame_wakes(self.frame) if wake > after]
        if wakes:
            return wakes
        programmed = WakeSchedule.from_frame(self.frame)
        offset = self._frame_offset()
        if programmed is None or offset is None:
            return []
        zone = timezone(timedelta(minutes=offset))
        return [wake.astimezone(UTC) for wake in programmed.wakes(after.astimezone(zone), 1)]

    @property
    def next_wake(self) -> datetime | None:
        wakes = self._upcoming_wakes(self._catch_after())
        return wakes[0] if wakes else None

    def as_dict(self, *, after: datetime | None = None, count: int = 0) -> dict[str, Any]:
        wake = self.next_wake
        return {
            "supported": self.supported,
            "active": self.active,
            "schedule": self.schedule.to_dict() if self.schedule else None,
            "synced": not self.dirty,
            "time_valid": (self.frame or {}).get("time_valid"),
            "next_wake": wake.isoformat() if wake else None,
            "slots": [
                slot.isoformat() for slot in self.slots(after or dt_util.utcnow(), count)
            ],
            "last_wake": self.last_wake,
            "missed": self.misses,
        }

    # ---------------------------------------------------------------- sync

    @callback
    def _coordinator_updated(self) -> None:
        coordinator = self.entry.runtime_data.coordinator
        if not coordinator.frame_online or self._catching or self._sync_lock.locked():
            return
        firmware = (coordinator.data or {}).get("firmware_version")
        if firmware and firmware != self._firmware:
            # A firmware update can add (or drop) the endpoint.
            self._firmware = firmware
            self.supported = None
        if self.supported is None or (self.supported and self.dirty):
            self.entry.async_create_background_task(
                self.hass, self.async_sync(), f"fraimic-wake-sync-{self.entry.entry_id}"
            )

    def _payload(self, state: dict[str, Any]) -> dict[str, Any] | None:
        """What the frame should hold; None to leave it as it is."""
        if self.schedule is None:
            return {"enabled": False} if self.dirty else None
        offset = frame_offset(state)
        if offset is None:
            offset = self._frame_offset()
        if offset is None:
            return None  # the frame's clock is unknown; try at its next wake
        local = int((dt_util.now().utcoffset() or timedelta()).total_seconds() // 60)
        return self.schedule.shifted(offset - local).frame_payload()

    async def async_sync(self) -> bool:
        """Read the frame's schedule and write ours over it when they differ.

        Returns whether the frame now holds what Home Assistant wants.
        """
        runtime = self.entry.runtime_data
        async with self._sync_lock:
            # The frame serves one request at a time; let uploads finish first.
            async with runtime.upload_lock:
                try:
                    state = await runtime.client.get_wake_schedule()
                except FraimicApiError as err:
                    if err.status == 404:
                        self.supported = False
                        await self._async_save()
                    return False
                except FraimicError:
                    return False
                self.supported = True
                payload = self._payload(state)
                if payload is not None and not matches(state, payload):
                    try:
                        state = await runtime.client.set_wake_schedule(payload)
                    except FraimicError as err:
                        _LOGGER.warning(
                            "Could not set the wake schedule of %s: %s",
                            self.entry.title,
                            err,
                        )
                        payload = None
                self.frame = state
                self.dirty = payload is None and (self.dirty or self.schedule is not None)
            await self._async_save()
        self._schedule_catch()
        return not self.dirty

    # --------------------------------------------------------------- catch

    def _catch_after(self) -> datetime:
        """Wakes up to this time are over, or already caught."""
        after = dt_util.utcnow() - CATCH_END
        caught = (self.last_wake or {}).get("wake")
        if caught:
            after = max(after, datetime.fromisoformat(caught))
        return after

    @callback
    def _schedule_catch(self) -> None:
        if self._unsub_catch is not None:
            self._unsub_catch()
            self._unsub_catch = None
        if self.supported is not True or self._catching:
            return
        # A schedule turned off here is still caught once, to clear it.
        if self.schedule is None and not self.dirty:
            return
        wakes = self._upcoming_wakes(self._catch_after())
        if not wakes:
            return
        start = max(dt_util.utcnow(), wakes[0] - CATCH_LEAD)
        self._unsub_catch = async_track_point_in_utc_time(
            self.hass, partial(self._start_catch, wakes[0]), start
        )

    @callback
    def _start_catch(self, wake: datetime, _now: datetime) -> None:
        self._unsub_catch = None
        self._catching = True
        self.entry.async_create_background_task(
            self.hass, self._async_catch(wake), f"fraimic-wake-{self.entry.entry_id}"
        )

    async def _async_catch(self, wake: datetime) -> None:
        runtime = self.entry.runtime_data
        try:
            answered = False
            while dt_util.utcnow() < wake + CATCH_END:
                if not runtime.coordinator.frame_busy:
                    try:
                        await runtime.client.get_battery(timeout=PROBE_TIMEOUT)
                    except FraimicError:
                        pass
                    else:
                        answered = True
                        break
                await asyncio.sleep(PROBE_EVERY)
            if answered:
                await self._async_answered()
            else:
                self._missed()
            self.last_wake = {
                "wake": wake.isoformat(),
                "at": dt_util.utcnow().isoformat(),
                "outcome": "answered" if answered else "missed",
            }
            await self._async_save()
        finally:
            self._catching = False
            self._schedule_catch()

    async def _async_answered(self) -> None:
        runtime = self.entry.runtime_data
        coordinator = runtime.coordinator
        self.misses = 0
        ir.async_delete_issue(self.hass, DOMAIN, self._issue_id)
        coordinator.async_set_frame_online(True)
        # This poll's listeners deliver: the scheduler's due art and any queued send.
        await coordinator.async_refresh()
        await self.async_sync()
        await self._async_wait_idle()
        battery = (coordinator.data or {}).get("battery") or {}
        if battery.get("charging") is not False:
            return  # charging keeps it awake anyway; unknown is not safe
        try:
            # Waits for any render to end; the frame would finish it regardless.
            await runtime.client.sleep()
        except FraimicConnectionError:
            pass  # the window closed during that wait: it is asleep already
        except FraimicError as err:
            _LOGGER.debug("Could not put %s back to sleep: %s", self.entry.title, err)
            return
        coordinator.async_set_frame_online(False, expected_sleep=True)

    async def _async_wait_idle(self) -> None:
        """Until no upload has run for a few seconds, or the limit."""
        runtime = self.entry.runtime_data
        deadline = time.monotonic() + SETTLE_LIMIT
        idle = 0
        while idle < IDLE_SECONDS and time.monotonic() < deadline:
            await asyncio.sleep(1)
            scheduler = runtime.scheduler
            busy = runtime.upload_lock.locked() or bool(scheduler and scheduler.busy)
            idle = 0 if busy else idle + 1

    def _missed(self) -> None:
        self.misses += 1
        _LOGGER.info("%s did not wake for its scheduled wake", self.entry.title)
        if self.misses < MISSES_FOR_ISSUE:
            return
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            self._issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="wake_missed",
            translation_placeholders={
                "frame": self.entry.title,
                "count": str(self.misses),
            },
        )
