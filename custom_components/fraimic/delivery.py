"""Choose a transport before uploading any image bytes."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from .api import FraimicConnectionError
from .const import CONF_DELIVERY_MODE, DELIVERY_HYBRID


if TYPE_CHECKING:
    from .coordinator import FraimicConfigEntry


async def async_use_cloud(entry: FraimicConfigEntry) -> bool:
    """Probe Hybrid frames at send time; never retry an upload on another transport.

    Cached coordinator state may describe a previous wake, or come from the
    cloud account. A read-only liveness request is safe to fall back from.
    Call while holding the frame's upload lock, after rendering finishes.
    """
    runtime = entry.runtime_data
    if getattr(runtime, "cloud", None) is None:
        return False
    if entry.options.get(CONF_DELIVERY_MODE) != DELIVERY_HYBRID:
        return True
    # An answering LAN endpoint does not mean a cloud download/redraw is idle.
    # Keep using the account until the scheduler retires that delivery after
    # its complete wake window, including for manual sends during the slot.
    if runtime.cloud.has_image:
        return True
    try:
        async with asyncio.timeout(3):
            battery = await runtime.client.get_battery()
    except (FraimicConnectionError, TimeoutError):
        runtime.coordinator.async_set_frame_online(False)
        return True
    current = dict(runtime.coordinator.data or {})
    existing = current.get("battery")
    existing = dict(existing) if isinstance(existing, dict) else {}
    update = battery.get("battery") if isinstance(battery.get("battery"), dict) else battery
    for key in ("percent", "voltage_mv", "charging", "cable_connected", "source"):
        if key in update:
            existing[key] = update[key]
    current["battery"] = existing
    runtime.coordinator.data = current
    runtime.coordinator.async_set_frame_online(True)
    return False
