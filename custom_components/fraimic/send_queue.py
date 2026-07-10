"""Queued delivery of rendered images to a sleeping frame.

The frame is battery-powered and unreachable in deep sleep, so a send that
misses it would otherwise just fail. Instead, the rendered ``.bin`` (plus its
preview) is persisted to disk and flushed on the next observed wake. Probes
use a power-mode-aware backoff; minimum mode is passive unless the frame has
advertised its own next scheduled wake.

Delivery semantics (hardware-informed, see #28/#33):

- **Latest wins** — a newer queued send replaces the old one. A token guards
  the flush so a stale in-flight attempt can never overwrite a newer image.
- **At-most-once** — a flush makes exactly one upload attempt. On a timeout
  the firmware may have accepted the image and be mid-redraw with the HTTP
  response blocked, so the queue is cleared (retrying could double-redraw the
  panel). Only a hard connection error (frame fell asleep again before the
  upload started) keeps the payload queued.
- Progress is broadcast over a dispatcher signal and mirrored by the
  always-available ``send_status`` sensor: the standout hint being
  *"tap the frame to wake it up"*.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .api import (
    FraimicApiError,
    FraimicConnectionError,
    FraimicError,
    FraimicTimeoutError,
)
from .const import DOMAIN
from .power import (
    DEFER_REASONS,
    SKIP_DUPLICATE,
    TRIGGER_MANUAL,
    power_mode,
    queue_probe_delay,
)

if TYPE_CHECKING:
    from .coordinator import FraimicConfigEntry

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1

# A queued image is dropped if the frame hasn't woken within this window —
# day-old automation content (weather, dashboards) shouldn't suddenly render.
QUEUE_TTL = 24 * 3600

def signal_send_status(entry_id: str) -> str:
    """Dispatcher signal carrying send-status updates for one frame."""
    return f"{DOMAIN}_send_status_{entry_id}"


class FraimicSendQueue:
    """Persisted single-slot send queue for one frame."""

    def __init__(self, hass: HomeAssistant, entry: FraimicConfigEntry) -> None:
        self._hass = hass
        self._entry = entry
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}_send_queue_{entry.entry_id}"
        )
        self._bin_path = hass.config.path(
            "fraimic_library", "queue", f"{entry.entry_id}.bin"
        )
        self._png_path = f"{self._bin_path}.png"
        # {"title", "mode", "token", "queued_at" (epoch), "has_preview"}
        self._pending: dict[str, Any] | None = None
        self._flushing = False
        self._unsub_listener: Any = None
        self._unsub_probe: Any = None
        self._unsub_expiry: Any = None
        self._probe_attempt = 0
        # Last human-readable status, mirrored by the send_status sensor.
        self.status: str = "Idle"

    # ---------------------------------------------------------------- setup

    async def async_setup(self) -> None:
        """Load persisted state and resume power-aware wake detection."""
        data = await self._store.async_load()
        if data and data.get("pending"):
            self._pending = data["pending"]
            if time.time() - self._pending.get("queued_at", 0) > QUEUE_TTL:
                await self._async_clear(
                    f"Gave up: frame never woke up for '{self._pending.get('title')}'"
                )
            else:
                self._start_waiting()

    def shutdown(self) -> None:
        """Detach from the coordinator (entry unload)."""
        self._stop_waiting()

    @property
    def pending(self) -> dict[str, Any] | None:
        """Metadata of the queued send, or None."""
        return self._pending

    # ---------------------------------------------------------------- sends

    async def async_upload_or_queue(
        self,
        bin_data: bytes,
        preview_png: bytes | None,
        mode: str,
        title: str,
        content_hash: str,
        trigger: str = TRIGGER_MANUAL,
    ) -> bool:
        """Upload now if possible, else queue for the frame's next wake.

        Returns True when the image was uploaded (or accepted-with-timeout)
        now, False when it was queued. Callers already hold the runtime
        upload lock.
        """
        runtime = self._entry.runtime_data
        self._dispatch(f"Sending {title}...")
        try:
            await runtime.client.upload_image(bin_data)
        except FraimicTimeoutError:
            # Possibly accepted with the response blocked by the redraw; do
            # not retry (double-redraw hazard) and do not queue. Latest wins:
            # drop any older queued payload so it can't overwrite this later.
            await self._async_drop_pending()
            self._dispatch(f"Sent {title} (unconfirmed — the frame's reply timed out)")
            return True
        except FraimicConnectionError:
            await self._async_queue(
                bin_data, preview_png, mode, title, content_hash, trigger
            )
            return False
        # FraimicApiError/FraimicError propagate: a real rejection (bad size
        # etc.) won't fix itself by waiting for a wake.
        await self._async_drop_pending()
        self._dispatch(f"Sent {self._now_str()}")
        return True

    async def async_queue_deferred(
        self,
        bin_data: bytes,
        preview_png: bytes | None,
        mode: str,
        title: str,
        content_hash: str,
        trigger: str,
    ) -> None:
        """Persist power-deferred automatic content in the latest-wins slot."""
        await self._async_queue(
            bin_data, preview_png, mode, title, content_hash, trigger
        )

    async def _async_queue(
        self,
        bin_data: bytes,
        preview_png: bytes | None,
        mode: str,
        title: str,
        content_hash: str,
        trigger: str,
    ) -> None:
        def _write() -> None:
            import os

            os.makedirs(os.path.dirname(self._bin_path), exist_ok=True)
            with open(self._bin_path, "wb") as file:
                file.write(bin_data)
            if preview_png:
                with open(self._png_path, "wb") as file:
                    file.write(preview_png)

        await self._hass.async_add_executor_job(_write)
        self._pending = {
            "title": title,
            "mode": mode,
            "token": time.monotonic_ns(),
            "queued_at": time.time(),
            "has_preview": bool(preview_png),
            "content_hash": content_hash,
            "trigger": trigger,
        }
        await self._store.async_save({"pending": self._pending})
        self._start_waiting()
        self._dispatch(f"Waiting to send {title} — tap the frame to wake it up")
        _LOGGER.info(
            "Frame %s is unreachable; queued '%s' for its next wake",
            self._entry.title,
            title,
        )

    async def async_try_send(self) -> None:
        """User-requested liveness check and immediate queued delivery attempt."""
        if self._pending is None:
            self._dispatch("Idle — nothing is queued")
            return
        try:
            battery = await self._entry.runtime_data.client.get_battery()
        except FraimicError:
            self._dispatch("Frame is still asleep — tap it, then try again")
            return
        self._apply_battery(battery)
        await self._async_flush()

    async def _async_probe(self, _now: Any = None) -> None:
        self._unsub_probe = None
        if self._pending is None:
            return
        self._probe_attempt += 1
        try:
            battery = await self._entry.runtime_data.client.get_battery()
        except FraimicError:
            self._schedule_probe()
            return
        self._apply_battery(battery)
        await self._async_flush()

    async def _async_expire(self, _now: Any = None) -> None:
        """Drop an expired item locally without making a frame request."""
        self._unsub_expiry = None
        if self._pending is None:
            return
        age = time.time() - self._pending.get("queued_at", 0)
        if age < QUEUE_TTL:
            self._schedule_expiry()
            return
        await self._async_clear(
            f"Gave up: frame never woke up for '{self._pending.get('title')}'"
        )

    def _apply_battery(self, payload: dict[str, Any]) -> None:
        """Merge a cheap liveness response into the policy's current snapshot."""
        runtime = self._entry.runtime_data
        current = dict(runtime.coordinator.data or {})
        existing = current.get("battery")
        existing = dict(existing) if isinstance(existing, dict) else {}
        update = payload.get("battery") if isinstance(payload.get("battery"), dict) else payload
        for key in ("percent", "voltage_mv", "charging", "cable_connected", "source"):
            if key in update:
                existing[key] = update[key]
        current["battery"] = existing
        runtime.coordinator.data = current

    # ---------------------------------------------------------------- flush

    @callback
    def _on_coordinator_update(self) -> None:
        coordinator = self._entry.runtime_data.coordinator
        if self._pending is None or not coordinator.last_update_success:
            return
        if self._flushing:
            return
        self._entry.async_create_background_task(
            self._hass, self._async_flush(), name=f"fraimic-flush-{self._entry.entry_id}"
        )

    async def _async_flush(self) -> None:
        """One delivery attempt for the queued payload (frame just woke)."""
        if self._flushing or self._pending is None:
            return
        self._flushing = True
        try:
            pending = self._pending
            token = pending["token"]
            title = pending.get("title") or "image"
            if time.time() - pending.get("queued_at", 0) > QUEUE_TTL:
                await self._async_clear(f"Gave up: frame never woke up for '{title}'")
                return

            runtime = self._entry.runtime_data

            def _read() -> tuple[bytes | None, bytes | None]:
                try:
                    with open(self._bin_path, "rb") as file:
                        bin_data = file.read()
                except OSError:
                    return None, None
                preview = None
                if pending.get("has_preview"):
                    try:
                        with open(self._png_path, "rb") as file:
                            preview = file.read()
                    except OSError:
                        preview = None
                return bin_data, preview

            bin_data, preview_png = await self._hass.async_add_executor_job(_read)
            if bin_data is None:
                await self._async_clear("Idle")
                return

            async with runtime.upload_lock:
                # A newer send may have replaced (or cleared) the queue while
                # we waited for the lock.
                if self._pending is None or self._pending["token"] != token:
                    return
                content_hash = pending.get("content_hash") or ""
                trigger = pending.get("trigger") or TRIGGER_MANUAL
                power_token = runtime.power.begin(trigger)
                reason = runtime.power.skip_reason(
                    content_hash,
                    trigger,
                    power_token,
                    runtime.coordinator.data,
                )
                runtime.power.finish(power_token)
                if reason == SKIP_DUPLICATE:
                    if preview_png:
                        runtime.last_preview = preview_png
                        if runtime.preview_image is not None:
                            runtime.preview_image.set_preview(
                                preview_png, pending.get("mode") or ""
                            )
                    runtime.media_title = title
                    await self._async_clear(f"Already displaying {title}")
                    return
                if reason in DEFER_REASONS:
                    self._dispatch(f"Deferred {title} to save battery ({reason})")
                    self._schedule_probe()
                    return
                self._dispatch(f"Sending {title}...")
                try:
                    await runtime.client.upload_image(bin_data)
                except FraimicTimeoutError:
                    await runtime.power.async_record_upload(content_hash, trigger)
                    await self._async_clear(
                        f"Sent {title} (unconfirmed — the frame's reply timed out)"
                    )
                    runtime.power.schedule_sleep()
                    return
                except FraimicConnectionError:
                    # Fell asleep again before the upload; keep it queued.
                    self._dispatch(
                        f"Waiting to send {title} — tap the frame to wake it up"
                    )
                    self._schedule_probe()
                    return
                except (FraimicApiError, FraimicError) as err:
                    await self._async_clear(f"Failed to send {title}: {err}")
                    return

                await runtime.power.async_record_upload(content_hash, trigger)
                await self._async_clear(f"Sent {self._now_str()}")
                if preview_png:
                    runtime.last_preview = preview_png
                    if runtime.preview_image is not None:
                        runtime.preview_image.set_preview(
                            preview_png, pending.get("mode") or ""
                        )
                runtime.media_title = title
                _LOGGER.info(
                    "Delivered queued image '%s' to %s", title, self._entry.title
                )
                runtime.power.schedule_sleep()
        finally:
            self._flushing = False

    # ------------------------------------------------------------- plumbing

    async def _async_clear(self, status: str) -> None:
        await self._async_drop_pending()
        self._dispatch(status)

    async def _async_drop_pending(self) -> None:
        """Forget any queued payload (no status change)."""
        if self._pending is None:
            return
        self._pending = None
        await self._store.async_save({"pending": None})
        self._stop_waiting()

    def _start_waiting(self) -> None:
        coordinator = self._entry.runtime_data.coordinator
        if self._unsub_listener is None:
            self._unsub_listener = coordinator.async_add_listener(
                self._on_coordinator_update
            )
        self._probe_attempt = 0
        if self._unsub_expiry is not None:
            self._unsub_expiry()
            self._unsub_expiry = None
        self._schedule_expiry()
        self._schedule_probe()

    def _schedule_expiry(self) -> None:
        if self._pending is None or self._unsub_expiry is not None:
            return
        remaining = QUEUE_TTL - (time.time() - self._pending.get("queued_at", 0))
        self._unsub_expiry = async_call_later(
            self._hass, max(0, remaining), self._async_expire
        )

    def _schedule_probe(self) -> None:
        if self._pending is None or self._unsub_probe is not None:
            return
        coordinator = self._entry.runtime_data.coordinator
        display = (coordinator.data or {}).get("display") or {}
        delay = queue_probe_delay(
            power_mode(dict(self._entry.options)),
            self._probe_attempt,
            next_refresh=display.get("next_refresh"),
        )
        if delay is None:
            return
        remaining = QUEUE_TTL - (time.time() - self._pending.get("queued_at", 0))
        if remaining <= 0 or delay >= remaining:
            return
        self._unsub_probe = async_call_later(
            self._hass, min(delay, remaining), self._async_probe
        )

    def _stop_waiting(self) -> None:
        if self._unsub_probe is not None:
            self._unsub_probe()
            self._unsub_probe = None
        if self._unsub_expiry is not None:
            self._unsub_expiry()
            self._unsub_expiry = None
        if self._unsub_listener is not None:
            self._unsub_listener()
            self._unsub_listener = None

    def _dispatch(self, status: str) -> None:
        self.status = status
        async_dispatcher_send(
            self._hass, signal_send_status(self._entry.entry_id), status
        )

    @staticmethod
    def _now_str() -> str:
        return dt_util.now().strftime("%Y-%m-%d %H:%M")
