"""Planned awake windows for a Hybrid frame that otherwise sleeps.

Firmware 0.2.29 never starts keep-awake from a timer wake, but a restart sent
during one does (docs/fraimic-cloud-api/albums-scheduling.md). So the album
wakes the frame shortly before ``start``, keep-awake goes on, and the wake is
caught on the LAN and turned into a normal boot. At ``end`` keep-awake goes off
and the album keeps a later slot, so the frame never sleeps without a wake.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Coroutine
from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .api import FraimicError
from .cloud import FraimicCloudError
from .const import DOMAIN

if TYPE_CHECKING:
    from .coordinator import FraimicConfigEntry

_LOGGER = logging.getLogger(__name__)

# The wake precedes ``start`` by the restart (~40 s) plus the album image the
# slot still renders (~2.5 min) and the retirement of that slot (~4 min).
WAKE_LEAD = 6 * 60
# Keep-awake goes on and probing starts this long before the wake. Timer
# wakes ignore keep-awake, so turning it on early cannot keep the frame up.
PREPARE = 5 * 60
# Fast probing lasts until this long after the wake, then slows down.
CATCH_WINDOW = 6 * 60
FAST_PROBE = 2
SLOW_PROBE = 15
# Timer wakes last at most ~3 min, so a shorter uptime is one to restart.
FRESH_BOOT = 240
# Without a window the frame still wakes this often (a short check wake), so
# a plan made while it sleeps reaches it.
HEARTBEAT = 24 * 3600
DAY = 24 * 3600


class AwakeWindow:
    """At most one planned window per frame; Home Assistant owns keep-awake."""

    def __init__(self, hass: HomeAssistant, entry: FraimicConfigEntry) -> None:
        self.hass, self.entry = hass, entry
        self._store: Store[dict[str, Any]] = Store(
            hass, 1, f"{DOMAIN}_awake_window_{entry.entry_id}"
        )
        self.start: float | None = None
        self.end: float | None = None
        self.repeat_daily = False
        self.awake = False
        self.restarted_at: float | None = None
        # Set once a window was used, so heartbeats never surprise frames
        # that do not use awake windows.
        self.managed = False
        self.last_result: str | None = None
        self._unsubs: list[Callable[[], None]] = []
        self._catcher: asyncio.Task[None] | None = None

    @property
    def active(self) -> bool:
        """Within a window, including its wake: the frame must not be slept."""
        if self.start is None or self.end is None:
            return False
        return self.start - WAKE_LEAD - PREPARE <= time.time() < self.end

    async def async_setup(self) -> None:
        data = await self._store.async_load() or {}
        self.start, self.end = data.get("start"), data.get("end")
        self.repeat_daily = data.get("repeat_daily", False)
        self.awake = data.get("awake", False)
        self.restarted_at = data.get("restarted_at")
        self.managed = data.get("managed", False)
        self.last_result = data.get("last_result")
        self._schedule()

    def shutdown(self) -> None:
        self._cancel()

    async def async_set(
        self, start: datetime, end: datetime, *, repeat_daily: bool = False
    ) -> None:
        """Replace any window; the frame stays awake from ``start`` to ``end``.

        A daily window plans the next day's while the frame is still awake, so
        a sleeping frame always carries the next wake.
        """
        was_awake = self.awake and self.active
        self._cancel()
        wake_at = dt_util.as_utc(start).timestamp() - WAKE_LEAD
        self.start = wake_at + WAKE_LEAD
        self.end = dt_util.as_utc(end).timestamp()
        self.repeat_daily = repeat_daily
        self.managed = True
        # A window that covers now keeps a frame already caught awake.
        self.awake = was_awake and self.active
        if time.time() < wake_at - PREPARE:
            # Sleep until the wake, which the album now carries.
            await self._async_keep_awake(False)
            await self._async_plan(wake_at)
        await self._async_save()
        self._schedule()

    async def async_clear(self) -> None:
        """End any window now and let the frame sleep until its heartbeat."""
        self._cancel()
        await self._async_finish()

    def diagnostics(self) -> dict[str, Any]:
        return {
            "start": self.start,
            "end": self.end,
            "repeat_daily": self.repeat_daily,
            "awake": self.awake,
            "managed": self.managed,
            "last_result": self.last_result,
        }

    # ------------------------------------------------------------ timeline

    def _schedule(self) -> None:
        start, end = self.start, self.end
        if start is None or end is None:
            cloud = self._cloud
            if self.managed and cloud is not None and cloud.wake_at is not None:
                self._at(cloud.wake_at - PREPARE, self._async_heartbeat)
            return
        if time.time() >= end:
            self._run(self._async_end())
            return
        self._at(start - WAKE_LEAD - PREPARE, self._async_prepare)
        self._at(end, self._async_end)

    def _at(self, when: float, job: Callable[[], Coroutine[Any, Any, None]]) -> None:
        @callback
        def fire(_now: datetime) -> None:
            self._run(job())

        if when <= time.time():
            self._run(job())
            return
        self._unsubs.append(
            async_track_point_in_utc_time(self.hass, fire, dt_util.utc_from_timestamp(when))
        )

    def _run(self, coro: Coroutine[Any, Any, None]) -> None:
        self.entry.async_create_background_task(self.hass, coro, f"fraimic-awake-{self.entry.entry_id}")

    def _cancel(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        if self._catcher is not None:
            self._catcher.cancel()
            self._catcher = None

    async def _async_prepare(self) -> None:
        await self._async_keep_awake(True)
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
        days = max(1, int((time.time() - end) // DAY) + 1)
        await self.async_set(
            dt_util.utc_from_timestamp(start + days * DAY),
            dt_util.utc_from_timestamp(end + days * DAY),
            repeat_daily=True,
        )

    async def _async_finish(self) -> None:
        """Window over: keep-awake off and a slot for the next wake."""
        if self._catcher is not None:
            self._catcher.cancel()
            self._catcher = None
        self.start = self.end = None
        self.repeat_daily = False
        self.awake = False
        if self.managed:
            await self._async_keep_awake(False)
            await self._async_plan(time.time() + HEARTBEAT)
        await self._async_save()
        self._schedule()

    async def _async_heartbeat(self) -> None:
        """Move the heartbeat on before the frame wakes for it.

        The re-anchored album no longer serves the slot the frame learned, so
        that wake is a short check that only picks up the next slot.
        """
        cloud = self._cloud
        if cloud is None or cloud.wake_at is None:
            return
        next_wake = cloud.wake_at + HEARTBEAT
        if next_wake <= time.time() + PREPARE:
            next_wake = time.time() + HEARTBEAT
        await self._async_plan(next_wake)
        self._schedule()

    # ------------------------------------------------------------ the wake

    async def _async_catch(self) -> None:
        """Probe the LAN; restart a fresh timer wake into a normal boot."""
        from .coordinator import normalize_info

        if self.start is None:
            return
        wake_at = self.start - WAKE_LEAD
        runtime = self.entry.runtime_data
        while self.end is not None and time.time() < self.end:
            now = time.time()
            recent = self.restarted_at is not None and now < self.restarted_at + CATCH_WINDOW
            try:
                async with asyncio.timeout(FAST_PROBE):
                    info = normalize_info(await runtime.client.get_info())
            except (FraimicError, TimeoutError):
                fast = recent or now < wake_at + CATCH_WINDOW
                await asyncio.sleep(FAST_PROBE if fast else SLOW_PROBE)
                continue
            uptime = info["device"]["uptime_s"]
            if not recent and isinstance(uptime, int | float) and uptime < FRESH_BOOT:
                async with runtime.upload_lock:
                    try:
                        await runtime.client.restart()
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
            runtime.coordinator.async_set_frame_online(True)
            _LOGGER.info("%s is awake for its window (%s)", self.entry.title, self.last_result)
            break
        else:
            self.last_result = "missed"
            await self._async_save()
            _LOGGER.warning("%s did not wake for its awake window", self.entry.title)
        self._catcher = None

    # ------------------------------------------------------------ cloud

    @property
    def _cloud(self) -> Any:
        return getattr(self.entry.runtime_data, "cloud", None)

    async def _async_keep_awake(self, on: bool) -> None:
        cloud = self._cloud
        if cloud is None:
            return
        try:
            await cloud.async_set_keep_awake(on)
        except FraimicCloudError as err:
            _LOGGER.warning("Could not turn keep-awake %s: %s", "on" if on else "off", err)

    async def _async_plan(self, wake_at: float) -> None:
        """Make the album carry a slot at ``wake_at`` for the sleeping frame."""
        cloud = self._cloud
        if cloud is None:
            return
        runtime = self.entry.runtime_data
        try:
            async with runtime.upload_lock:
                if await cloud.async_plan_wake(wake_at):
                    return
                # No pending image: re-send the one on the glass to carry the slot.
                base = getattr(runtime.temporary_overlays, "base", None)
                if base is None:
                    _LOGGER.warning("No artwork to carry the wake of %s", self.entry.title)
                    return
                await cloud.async_deliver(
                    base[0], title=runtime.temporary_overlays.title, preview_png=base[1]
                )
        except FraimicCloudError as err:
            _LOGGER.warning("Could not plan the next wake of %s: %s", self.entry.title, err)

    async def _async_save(self) -> None:
        await self._store.async_save(
            {
                "start": self.start,
                "end": self.end,
                "repeat_daily": self.repeat_daily,
                "awake": self.awake,
                "restarted_at": self.restarted_at,
                "managed": self.managed,
                "last_result": self.last_result,
            }
        )
