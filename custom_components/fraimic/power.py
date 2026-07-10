"""Per-frame battery policy and redraw accounting.

This module deliberately has no Home Assistant imports at module load time so
the decision logic remains cheap to unit-test. Persistence is loaded lazily in
``async_setup``.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import time
from typing import Any

from .const import (
    CONF_AUTO_SLEEP,
    CONF_POWER_MODE,
    CONF_SCAN_INTERVAL,
    DEFAULT_AUTO_SLEEP,
    DEFAULT_POWER_MODE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    POWER_MODE_BALANCED,
    POWER_MODE_MINIMUM,
    POWER_MODE_RESPONSIVE,
)

_LOGGER = logging.getLogger(__name__)

TRIGGER_MANUAL = "manual"
TRIGGER_SCHEDULED = "scheduled"
TRIGGER_PLAYLIST = "playlist"
TRIGGER_CAMERA = "camera"
AUTOMATIC_TRIGGERS = frozenset(
    {TRIGGER_SCHEDULED, TRIGGER_PLAYLIST, TRIGGER_CAMERA}
)
TRIGGER_PRIORITY = {
    TRIGGER_CAMERA: 1,
    TRIGGER_PLAYLIST: 2,
    TRIGGER_SCHEDULED: 3,
    TRIGGER_MANUAL: 4,
}

SKIP_DUPLICATE = "duplicate"
SKIP_COALESCED = "coalesced"
SKIP_LOW_BATTERY = "low_battery"
SKIP_COOLDOWN = "cooldown"
SKIP_DAILY_BUDGET = "daily_budget"
DEFER_REASONS = frozenset({SKIP_LOW_BATTERY, SKIP_COOLDOWN, SKIP_DAILY_BUDGET})

AUTO_SLEEP_DELAY = 45
STATE_VERSION = 1


@dataclass(frozen=True)
class PowerProfile:
    """Runtime limits for one user-facing power mode."""

    poll_floor: int | None
    startup_poll: bool
    automatic_interval: int
    daily_automatic_budget: int
    queue_backoff: tuple[int, ...]
    require_known_battery: bool


PROFILES = {
    POWER_MODE_MINIMUM: PowerProfile(
        poll_floor=None,
        startup_poll=False,
        automatic_interval=6 * 3600,
        daily_automatic_budget=1,
        queue_backoff=(),
        require_known_battery=True,
    ),
    POWER_MODE_BALANCED: PowerProfile(
        poll_floor=3600,
        startup_poll=True,
        automatic_interval=30 * 60,
        daily_automatic_budget=8,
        queue_backoff=(30, 30, 120, 300, 900, 3600),
        require_known_battery=False,
    ),
    POWER_MODE_RESPONSIVE: PowerProfile(
        poll_floor=30,
        startup_poll=True,
        automatic_interval=5 * 60,
        daily_automatic_budget=48,
        queue_backoff=(30, 30, 30, 60, 120, 300),
        require_known_battery=False,
    ),
}


def power_mode(options: dict[str, Any]) -> str:
    """Return a valid configured power mode."""
    value = options.get(CONF_POWER_MODE, DEFAULT_POWER_MODE)
    return value if value in PROFILES else DEFAULT_POWER_MODE


def effective_scan_interval(options: dict[str, Any]) -> int | None:
    """Return the coordinator interval after applying the power profile."""
    profile = PROFILES[power_mode(options)]
    if profile.poll_floor is None:
        return None
    configured = int(options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
    return max(configured, profile.poll_floor)


def _timestamp(value: Any) -> float | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def queue_probe_delay(
    mode: str,
    attempt: int,
    *,
    now: float | None = None,
    next_refresh: Any = None,
) -> float | None:
    """Return the next queued-send liveness delay.

    Minimum mode is passive unless the frame advertised its own next wake.
    Other modes exponentially back off, but use an earlier known wake time.
    """
    now = time.time() if now is None else now
    profile = PROFILES.get(mode, PROFILES[DEFAULT_POWER_MODE])
    predicted = _timestamp(next_refresh)
    wake_delay = None
    if predicted is not None and predicted > now:
        wake_delay = max(1.0, predicted - now + 30)
    if not profile.queue_backoff:
        return wake_delay
    delay = float(profile.queue_backoff[min(attempt, len(profile.queue_backoff) - 1)])
    return min(delay, wake_delay) if wake_delay is not None else delay


class FraimicPowerManager:
    """Persist duplicate, budget, coalescing, and optional sleep state."""

    def __init__(self, hass: Any, entry: Any) -> None:
        self.hass = hass
        self.entry = entry
        self.mode = power_mode(dict(entry.options))
        self.profile = PROFILES[self.mode]
        self.last_hash: str | None = None
        self.last_display_marker: str | None = None
        self.last_automatic_at = 0.0
        self.last_upload_at = 0.0
        self.budget_day = ""
        self.automatic_count = 0
        self.upload_count = 0
        self.skip_counts: dict[str, int] = {}
        self._store: Any = None
        self._token = 0
        self._latest_automatic_token: int | None = None
        self._latest_automatic_priority = 0
        self._sleep_task: asyncio.Task | None = None

    @property
    def startup_poll(self) -> bool:
        return self.profile.startup_poll

    async def async_setup(self) -> None:
        from homeassistant.helpers.storage import Store

        self._store = Store(
            self.hass, STATE_VERSION, f"{DOMAIN}_power_{self.entry.entry_id}"
        )
        data = await self._store.async_load() or {}
        self.last_hash = data.get("last_hash")
        self.last_display_marker = data.get("last_display_marker")
        self.last_automatic_at = float(data.get("last_automatic_at", 0.0))
        self.last_upload_at = float(data.get("last_upload_at", 0.0))
        self.budget_day = str(data.get("budget_day", ""))
        self.automatic_count = int(data.get("automatic_count", 0))
        self.upload_count = int(data.get("upload_count", 0))
        self.skip_counts = dict(data.get("skip_counts") or {})

    def shutdown(self) -> None:
        if self._sleep_task is not None:
            self._sleep_task.cancel()
            self._sleep_task = None

    async def _async_save(self) -> None:
        if self._store is None:
            return
        await self._store.async_save(
            {
                "last_hash": self.last_hash,
                "last_display_marker": self.last_display_marker,
                "last_automatic_at": self.last_automatic_at,
                "last_upload_at": self.last_upload_at,
                "budget_day": self.budget_day,
                "automatic_count": self.automatic_count,
                "upload_count": self.upload_count,
                "skip_counts": self.skip_counts,
            }
        )

    def begin(self, trigger: str) -> int:
        """Register a send and return its coalescing token."""
        if self._sleep_task is not None:
            self._sleep_task.cancel()
            self._sleep_task = None
        self._token += 1
        token = self._token
        if trigger in AUTOMATIC_TRIGGERS:
            priority = TRIGGER_PRIORITY.get(trigger, 0)
            if priority >= self._latest_automatic_priority:
                self._latest_automatic_token = token
                self._latest_automatic_priority = priority
        return token

    def finish(self, token: int) -> None:
        if token == self._latest_automatic_token:
            self._latest_automatic_token = None
            self._latest_automatic_priority = 0

    def _count_skip(self, reason: str) -> str:
        self.skip_counts[reason] = self.skip_counts.get(reason, 0) + 1
        return reason

    def skip_reason(
        self,
        content_hash: str,
        trigger: str,
        token: int,
        data: dict[str, Any] | None,
        *,
        now: float | None = None,
    ) -> str | None:
        """Return why a rendered send should not touch the frame."""
        now = time.time() if now is None else now
        data = data or {}
        display = data.get("display") if isinstance(data, dict) else {}
        next_native_refresh = _timestamp(
            display.get("next_refresh") if isinstance(display, dict) else None
        )
        native_refresh_may_have_run = (
            next_native_refresh is not None and next_native_refresh <= now
        )
        if content_hash == self.last_hash and not native_refresh_may_have_run:
            return self._count_skip(SKIP_DUPLICATE)
        automatic = trigger in AUTOMATIC_TRIGGERS
        if not automatic:
            return None
        if token != self._latest_automatic_token:
            return self._count_skip(SKIP_COALESCED)

        battery = data.get("battery") if isinstance(data, dict) else {}
        battery = battery if isinstance(battery, dict) else {}
        charging = battery.get("charging") is True or battery.get("cable_connected") is True
        percent = battery.get("percent")
        if not charging and self.profile.require_known_battery and not isinstance(
            percent, (int, float)
        ):
            return self._count_skip(SKIP_LOW_BATTERY)
        if not charging and isinstance(percent, (int, float)) and percent < 25:
            return self._count_skip(SKIP_LOW_BATTERY)

        if not charging and now - self.last_upload_at < self.profile.automatic_interval:
            return self._count_skip(SKIP_COOLDOWN)
        today = datetime.fromtimestamp(now, timezone.utc).date().isoformat()
        count = self.automatic_count if self.budget_day == today else 0
        if not charging and count >= self.profile.daily_automatic_budget:
            return self._count_skip(SKIP_DAILY_BUDGET)
        return None

    async def async_record_upload(
        self, content_hash: str, trigger: str, *, now: float | None = None
    ) -> None:
        now = time.time() if now is None else now
        self.last_hash = content_hash
        self.last_upload_at = now
        self.upload_count += 1
        if trigger in AUTOMATIC_TRIGGERS:
            today = datetime.fromtimestamp(now, timezone.utc).date().isoformat()
            if self.budget_day != today:
                self.budget_day = today
                self.automatic_count = 0
            self.automatic_count += 1
            self.last_automatic_at = now
        await self._async_save()

    async def async_observe_frame(self, data: dict[str, Any]) -> None:
        """Invalidate the hash when a native/cloud refresh changed the glass."""
        display = data.get("display") if isinstance(data, dict) else None
        marker = display.get("last_refresh") if isinstance(display, dict) else None
        if not marker:
            return
        marker = str(marker)
        if marker == self.last_display_marker:
            return
        if self.last_display_marker:
            self.last_hash = None
        self.last_display_marker = marker
        await self._async_save()

    def schedule_sleep(self) -> None:
        """Optionally sleep the frame after its redraw has safely completed."""
        if not self.entry.options.get(CONF_AUTO_SLEEP, DEFAULT_AUTO_SLEEP):
            return
        self._sleep_task = self.entry.async_create_background_task(
            self.hass,
            self._async_sleep_after_redraw(),
            name=f"fraimic-auto-sleep-{self.entry.entry_id}",
        )

    async def _async_sleep_after_redraw(self) -> None:
        try:
            await asyncio.sleep(AUTO_SLEEP_DELAY)
            runtime = self.entry.runtime_data
            data = runtime.coordinator.data or {}
            battery = data.get("battery") if isinstance(data, dict) else {}
            settings = data.get("settings") if isinstance(data, dict) else {}
            # Unknown power state is intentionally not safe enough for an
            # automatic sleep command.
            if not isinstance(battery, dict) or battery.get("charging") is not False:
                return
            if battery.get("cable_connected") is True:
                return
            if isinstance(settings, dict) and settings.get("keep_awake") is True:
                return
            queue = getattr(runtime, "send_queue", None)
            if runtime.upload_lock.locked() or (queue is not None and queue.pending):
                return
            await runtime.client.sleep()
        except asyncio.CancelledError:
            raise
        except Exception as err:  # best-effort experimental feature
            _LOGGER.debug("Automatic post-upload sleep failed: %s", err)
        finally:
            self._sleep_task = None

    def diagnostics(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "effective_scan_interval": effective_scan_interval(dict(self.entry.options)),
            "last_hash_known": self.last_hash is not None,
            "automatic_count_today": self.automatic_count,
            "last_upload_at": self.last_upload_at or None,
            "upload_count": self.upload_count,
            "skip_counts": dict(self.skip_counts),
        }
