"""Bounded TTL/LRU cache + per-provider request throttling. HA-free.

One instance lives in ``hass.data`` and is shared across config entries, so
two frames share the same Met id pool and rate-limit budget. The clock is
injectable for headless tests.
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

DEFAULT_MAX_ENTRIES = 128


class ProviderCache:
    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        max_entries: int = DEFAULT_MAX_ENTRIES,
    ) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        self._clock = clock
        self._max_entries = max_entries
        self._values: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._last_call: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def get(self, key: str, ttl: float) -> Any | None:
        """Cached value if it is younger than ``ttl`` seconds, else None."""
        entry = self._values.get(key)
        if entry is None:
            return None
        stored_at, value = entry
        if self._clock() - stored_at > ttl:
            del self._values[key]
            return None
        self._values.move_to_end(key)
        return value

    def set(self, key: str, value: Any) -> None:
        self._values[key] = (self._clock(), value)
        self._values.move_to_end(key)
        while len(self._values) > self._max_entries:
            self._values.popitem(last=False)

    async def async_throttle(self, key: str, min_interval: float) -> None:
        """Wait until at least ``min_interval`` s since the last call for key."""
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            elapsed = self._clock() - self._last_call.get(key, -min_interval)
            if elapsed < min_interval:
                await asyncio.sleep(min_interval - elapsed)
            self._last_call[key] = self._clock()
