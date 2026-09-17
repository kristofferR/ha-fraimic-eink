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
    try:
        async with asyncio.timeout(3):
            await runtime.client.get_battery()
    except (FraimicConnectionError, TimeoutError):
        return True
    return False
