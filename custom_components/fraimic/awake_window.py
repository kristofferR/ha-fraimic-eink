"""Planned awake windows for a Hybrid frame that otherwise sleeps.

Firmware 0.2.29 never starts keep-awake from a timer wake, but a restart sent
during one does (docs/fraimic-cloud-api/albums-scheduling.md). So the album
wakes the frame shortly before ``start``, keep-awake goes on, and the wake is
caught on the LAN and turned into a normal boot. At ``end`` keep-awake goes off
once the album carries a later slot, so the frame never sleeps without a wake.

From ``standby_from`` the frame also checks in every few minutes. A window
started early (``start`` now) then reaches it at the next check.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Coroutine
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .api import FraimicApiError, FraimicError
from .cloud import FraimicCloudError
from .const import CLOUD_SLOT_LEAD_MINUTES, DOMAIN

if TYPE_CHECKING:
    from .coordinator import FraimicConfigEntry

_LOGGER = logging.getLogger(__name__)

# The wake precedes ``start`` by the restart (~40 s) and some slack.
WAKE_LEAD = 6 * 60
# Keep-awake goes on and probing starts this long before the planned wake.
# Timer wakes ignore keep-awake, so turning it on early cannot keep the frame up.
PREPARE = 5 * 60
# Each check slot is re-anchored this long before it, so the frame's wake for
# it finds nothing due and only learns the next slot.
STEER_LEAD = 150
STANDBY_INTERVAL = 5 * 60
# A slot closer than this cannot be steered (see ``cloud.steered_minutes``).
STEER_MIN = CLOUD_SLOT_LEAD_MINUTES * 60
# Fast probing around an expected wake, slow otherwise.
CATCH_WINDOW = 6 * 60
FAST_PROBE = 2
SLOW_PROBE = 15
# Timer wakes last at most ~3 min, so a shorter uptime is one to restart.
FRESH_BOOT = 240
# Without a window the frame still wakes this often, so a plan made while it
# sleeps reaches it.
HEARTBEAT = 24 * 3600
# A failed cloud call is retried this much later.
RETRY = 60


def following_wake(
    after: float, *, wake: float | None, standby_from: float | None
) -> float:
    """The frame's next planned wake after one at ``after``.

    ``wake`` is the window's wake, None without a window. Before standby the
    frame sleeps until it starts (at most a day); during standby, and once
    the window is due but not yet caught, it checks every STANDBY_INTERVAL.
    """
    if wake is None:
        return after + HEARTBEAT
    step = after + STANDBY_INTERVAL
    if after >= wake:
        return step
    if standby_from is None or step < standby_from:
        first = wake if standby_from is None else min(standby_from, wake)
        return min(first, after + HEARTBEAT)
    return min(step, wake)


def _days_later(ts: float, days: int) -> datetime:
    """The same local wall-clock time ``days`` later, across DST changes."""
    return dt_util.as_local(dt_util.utc_from_timestamp(ts)) + timedelta(days=days)


def _store(hass: HomeAssistant, entry: FraimicConfigEntry) -> Store[dict[str, Any]]:
    return Store(hass, 1, f"{DOMAIN}_awake_window_{entry.entry_id}")


async def async_retire_awake_window(
    hass: HomeAssistant, entry: FraimicConfigEntry, cloud: Any
) -> bool:
    """Delivery left Hybrid: drop any window and the keep-awake it may hold.

    Returns False when the account could not be updated; the state is kept
    so setup can retry.
    """
    store = _store(hass, entry)
    data = await store.async_load()
    if not data:
        return True
    if cloud is not None and data.get("managed"):
        try:
            # Cloud delivery keeps the frame asleep between album slots.
            await cloud.async_set_keep_awake(False)
            await cloud.async_plan_wake(None)
        except FraimicCloudError as err:
            _LOGGER.warning("Could not release the awake window of %s: %s", entry.title, err)
            return False
    await store.async_remove()
    return True


class AwakeWindow:
    """At most one planned window per frame; Home Assistant owns keep-awake."""

    def __init__(self, hass: HomeAssistant, entry: FraimicConfigEntry) -> None:
        self.hass, self.entry = hass, entry
        self._store = _store(hass, entry)
        self.start: float | None = None
        self.end: float | None = None
        self.standby_from: float | None = None
        self.repeat_daily = False
        self.awake = False
        self.restarted_at: float | None = None
        # Set once a window was used, so heartbeats never surprise frames
        # that do not use awake windows.
        self.managed = False
        self.last_result: str | None = None
        self._keep_awake_on = False
        # The frame may not sleep yet: its next wake is not on the album.
        self._rest_pending = False
        self._unsubs: list[Callable[[], None]] = []
        self._catcher: asyncio.Task[None] | None = None
        # Transitions run one at a time; a replaced window's jobs are dropped.
        self._lock = asyncio.Lock()
        self._generation = 0

    @property
    def active(self) -> bool:
        """Within a window, including its wake: the frame must not be slept."""
        if self.start is None or self.end is None:
            return False
        return self.start - WAKE_LEAD - PREPARE <= time.time() < self.end

    @property
    def holds_awake(self) -> bool:
        """Inside a window, or its next wake is not armed yet: no sleeping."""
        return self.active or self._rest_pending

    @property
    def resting(self) -> bool:
        """Between windows the frame should sleep; LAN polls would keep it up."""
        return self.managed and not self.holds_awake

    @property
    def _wake(self) -> float | None:
        return None if self.start is None else self.start - WAKE_LEAD

    async def async_setup(self) -> None:
        data = await self._store.async_load() or {}
        self.start, self.end = data.get("start"), data.get("end")
        self.standby_from = data.get("standby_from")
        self.repeat_daily = data.get("repeat_daily", False)
        self.awake = data.get("awake", False)
        self.restarted_at = data.get("restarted_at")
        self.managed = data.get("managed", False)
        self.last_result = data.get("last_result")
        self._rest_pending = data.get("rest_pending", False)
        device = data.get("device_id")
        cloud = self._cloud
        if device and cloud is not None and device != cloud.device_id:
            # Another canvas was chosen. The window was the old canvas's;
            # cloud delivery hands that one back to local use on its own.
            self.start = self.end = self.standby_from = None
            self.repeat_daily = self.awake = self.managed = self._rest_pending = False
            await self._async_save()
            try:
                await cloud.async_plan_wake(None)
            except FraimicCloudError as err:
                _LOGGER.debug("Could not drop the previous canvas's wake plan: %s", err)
        self._schedule()

    def shutdown(self) -> None:
        self._cancel_timers()
        self._stop_catcher()

    async def async_set(
        self,
        start: datetime,
        end: datetime,
        *,
        standby_from: datetime | None = None,
        repeat_daily: bool = False,
    ) -> None:
        """Replace any window; the frame stays awake from ``start`` to ``end``.

        A daily window plans the next day's while the frame is still awake, so
        a sleeping frame always carries the next wake.
        """
        async with self._lock:
            await self._async_set_locked(
                start, end, standby_from=standby_from, repeat_daily=repeat_daily
            )

    async def _async_set_locked(
        self,
        start: datetime,
        end: datetime,
        *,
        standby_from: datetime | None,
        repeat_daily: bool,
    ) -> None:
        self._generation += 1
        was_awake = self.awake and self.active
        self._cancel_timers()
        self._stop_catcher()
        self.start = dt_util.as_utc(start).timestamp()
        self.end = dt_util.as_utc(end).timestamp()
        self.standby_from = (
            None if standby_from is None else dt_util.as_utc(standby_from).timestamp()
        )
        self.repeat_daily = repeat_daily
        self.managed = True
        # A window that covers now keeps a frame already caught awake, and
        # ends any rest still waiting for its wake.
        self.awake = was_awake and self.active
        if self.active:
            self._rest_pending = False
        await self._async_save()
        wake = self.start - WAKE_LEAD
        if not self.active:
            await self._async_rest()
            return
        if not self.awake and wake - time.time() >= STEER_MIN:
            # Due soon but still ahead: the sleeping frame needs its slot.
            await self._async_plan(wake)
        self._schedule()

    async def async_clear(self) -> None:
        """End any window now and let the frame sleep until its heartbeat."""
        async with self._lock:
            self._generation += 1
            self._cancel_timers()
            await self._async_finish()

    def diagnostics(self) -> dict[str, Any]:
        return {
            "start": self.start,
            "end": self.end,
            "standby_from": self.standby_from,
            "repeat_daily": self.repeat_daily,
            "awake": self.awake,
            "managed": self.managed,
            "rest_pending": self._rest_pending,
            "last_result": self.last_result,
        }

    # ------------------------------------------------------------ timeline

    def _schedule(self) -> None:
        """Timers for the current state; replaces any scheduled before."""
        self._cancel_timers()
        if self._rest_pending:
            self._at(time.time() + RETRY, self._async_rest)
        upcoming = getattr(self._cloud, "wake_at", None)
        start, end, wake = self.start, self.end, self._wake
        if start is None or end is None or wake is None:
            if self.managed and upcoming is not None and not self._rest_pending:
                self._at(upcoming - STEER_LEAD, self._async_steer)
            return
        if time.time() >= end:
            self._at(time.time(), self._async_end)
            return
        if not self.awake:
            self._at(wake - PREPARE, self._async_prepare)
            # The window's own wake stays due; checks before it are steered.
            if upcoming is not None and abs(upcoming - wake) > 60:
                self._at(upcoming - STEER_LEAD, self._async_steer)
            else:
                # Missed it: keep checking until the frame is caught.
                self._at(wake + CATCH_WINDOW, self._async_steer)
        self._at(end, self._async_end)

    def _at(self, when: float, job: Callable[[], Coroutine[Any, Any, None]]) -> None:
        generation = self._generation

        async def guarded() -> None:
            async with self._lock:
                if generation == self._generation:
                    await job()

        @callback
        def fire(_now: datetime) -> None:
            self._run(guarded())

        if when <= time.time():
            self._run(guarded())
            return
        self._unsubs.append(
            async_track_point_in_utc_time(self.hass, fire, dt_util.utc_from_timestamp(when))
        )

    def _run(self, coro: Coroutine[Any, Any, None]) -> None:
        self.entry.async_create_background_task(self.hass, coro, f"fraimic-awake-{self.entry.entry_id}")

    def _cancel_timers(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()

    def _stop_catcher(self) -> None:
        if self._catcher is not None:
            self._catcher.cancel()
            self._catcher = None

    async def _async_rest(self) -> None:
        """Arm the next wake, and only then let the frame sleep."""
        if self.active:
            return
        target = following_wake(time.time(), wake=self._wake, standby_from=self.standby_from)
        rested = await self._async_plan(target) and await self._async_keep_awake(False)
        if not rested and not self._rest_pending:
            _LOGGER.warning(
                "%s stays awake until its next wake is planned and keep-awake is off",
                self.entry.title,
            )
        if self._rest_pending == rested:
            self._rest_pending = not rested
            await self._async_save()
        self._schedule()

    async def _async_steer(self) -> None:
        """Re-anchor before a check so it only teaches the frame the next one."""
        upcoming = getattr(self._cloud, "wake_at", None)
        restarting = self.restarted_at is not None and time.time() < self.restarted_at + CATCH_WINDOW
        if upcoming is None or self.awake or restarting:
            return
        # A wake missed while Home Assistant was down is spent; plan from now.
        if await self._async_plan(
            following_wake(
                max(upcoming, time.time()), wake=self._wake, standby_from=self.standby_from
            )
        ):
            self._schedule()
        else:
            self._at(time.time() + RETRY, self._async_steer)

    async def _async_prepare(self) -> None:
        self._keep_awake_on = await self._async_keep_awake(True)
        if not self.awake and self._catcher is None:
            self._catcher = self.entry.async_create_background_task(
                self.hass, self._async_catch(), f"fraimic-awake-catch-{self.entry.entry_id}"
            )

    async def _async_end(self) -> None:
        """A window ran out; a daily one moves on to its next day."""
        start, end = self.start, self.end
        if not self.repeat_daily or start is None or end is None:
            await self._async_finish()
            return
        # Count local days, so time lost to downtime across DST skips no window.
        now = _days_later(time.time(), 0)
        days = max(1, (now.date() - _days_later(end, 0).date()).days)
        if _days_later(end, days) <= now:
            days += 1
        standby = self.standby_from
        await self._async_set_locked(
            _days_later(start, days),
            _days_later(end, days),
            standby_from=None if standby is None else _days_later(standby, days),
            repeat_daily=True,
        )

    async def _async_finish(self) -> None:
        """Window over: the frame sleeps once its heartbeat is armed."""
        self._stop_catcher()
        self.start = self.end = self.standby_from = None
        self.repeat_daily = False
        self.awake = False
        await self._async_save()
        if self.managed:
            await self._async_rest()
        else:
            self._schedule()

    # ------------------------------------------------------------ the wake

    async def _async_catch(self) -> None:
        """Probe the LAN; restart a fresh timer wake into a normal boot."""
        from .coordinator import normalize_info

        runtime = self.entry.runtime_data
        while self.end is not None and time.time() < self.end:
            now = time.time()
            recent = self.restarted_at is not None and now < self.restarted_at + CATCH_WINDOW
            try:
                async with asyncio.timeout(FAST_PROBE):
                    info = normalize_info(await runtime.client.get_info())
            except (FraimicError, TimeoutError):
                expected = [w for w in (self._wake, getattr(self._cloud, "wake_at", None)) if w]
                fast = recent or any(w - 90 <= now < w + CATCH_WINDOW for w in expected)
                await asyncio.sleep(FAST_PROBE if fast else SLOW_PROBE)
                continue
            if not await self._async_hold():
                # The account is failing; do not call it every probe.
                await asyncio.sleep(SLOW_PROBE)
                continue
            uptime = info["device"]["uptime_s"]
            # Without an uptime the boot is unknown; a restart is the safe answer.
            fresh = not isinstance(uptime, int | float) or uptime < FRESH_BOOT
            if not recent and fresh:
                async with runtime.upload_lock:
                    try:
                        await runtime.client.restart()
                    except FraimicApiError as err:
                        _LOGGER.warning("%s refused to restart: %s", self.entry.title, err)
                        await asyncio.sleep(FAST_PROBE)
                        continue
                    except FraimicError as err:
                        # The reboot can drop the connection before replying.
                        _LOGGER.debug("Restart reply for %s: %s", self.entry.title, err)
                self.restarted_at = time.time()
                await self._async_save()
                await asyncio.sleep(20)
                continue
            self.awake = True
            self.last_result = "restarted" if recent else "already_awake"
            await self._async_save()
            self._schedule()
            runtime.coordinator.async_set_frame_online(True)
            _LOGGER.info("%s is awake for its window (%s)", self.entry.title, self.last_result)
            break
        else:
            self.last_result = "missed"
            await self._async_save()
            _LOGGER.warning("%s did not wake for its awake window", self.entry.title)
        self._catcher = None

    async def _async_hold(self) -> bool:
        """Keep-awake on and nothing left to serve, before the frame is restarted.

        Without keep-awake the restarted frame would sleep again; with the album
        still active, every slot in the window would redraw it.
        """
        if not self._keep_awake_on:
            self._keep_awake_on = await self._async_keep_awake(True)
        return self._keep_awake_on and await self._async_retire_album()

    # ------------------------------------------------------------ cloud

    @property
    def _cloud(self) -> Any:
        return getattr(self.entry.runtime_data, "cloud", None)

    async def _async_keep_awake(self, on: bool) -> bool:
        cloud = self._cloud
        if cloud is None:
            return False
        try:
            await cloud.async_set_keep_awake(on)
        except FraimicCloudError as err:
            _LOGGER.warning("Could not turn keep-awake %s: %s", "on" if on else "off", err)
            return False
        if not on:
            self._keep_awake_on = False
        return True

    async def _async_retire_album(self) -> bool:
        cloud = self._cloud
        if cloud is None:
            return True
        try:
            async with self.entry.runtime_data.upload_lock:
                await cloud.async_cancel_delivery()
        except FraimicCloudError as err:
            _LOGGER.warning("Could not retire the wake slot of %s: %s", self.entry.title, err)
            return False
        return True

    async def _async_plan(self, wake_at: float) -> bool:
        """Make the album carry a slot at ``wake_at`` for the sleeping frame."""
        cloud = self._cloud
        if cloud is None:
            return False
        runtime = self.entry.runtime_data
        overlays = runtime.temporary_overlays
        base = getattr(overlays, "base", None)
        scheduler = runtime.scheduler
        # Same rule as the player: external uploads clear the displayed hash.
        shown = scheduler.current_screen if scheduler.displayed_hash is not None else None
        # Without a pending image, the art on the glass carries the slot.
        carrier = None if base is None else (
            base[0], base[1], overlays.title, shown.source if shown else None
        )
        try:
            async with runtime.upload_lock:
                return bool(await cloud.async_plan_wake(wake_at, carrier))
        except FraimicCloudError as err:
            _LOGGER.warning("Could not plan the next wake of %s: %s", self.entry.title, err)
            return False

    async def _async_save(self) -> None:
        await self._store.async_save(
            {
                "start": self.start,
                "end": self.end,
                "standby_from": self.standby_from,
                "repeat_daily": self.repeat_daily,
                "awake": self.awake,
                "restarted_at": self.restarted_at,
                "managed": self.managed,
                "rest_pending": self._rest_pending,
                "last_result": self.last_result,
                "device_id": getattr(self._cloud, "device_id", None),
            }
        )
