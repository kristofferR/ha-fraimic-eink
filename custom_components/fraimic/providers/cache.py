"""Bounded TTL/LRU cache + per-provider request throttling. HA-free.

One instance lives in ``hass.data`` and is shared across config entries, so
two frames share the same Met id pool and rate-limit budget. The clock is
injectable for headless tests.
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from collections.abc import Callable, Hashable
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


class ByteCache:
    """Byte-size-bounded TTL/LRU cache for downloaded media."""

    def __init__(
        self,
        max_bytes: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_bytes < 1:
            raise ValueError("max_bytes must be positive")
        self._clock = clock
        self._max_bytes = max_bytes
        self._size = 0
        self._values: OrderedDict[
            Hashable, tuple[float, bytes, str]
        ] = OrderedDict()

    def get(self, key: Hashable, ttl: float) -> tuple[bytes, str] | None:
        """Cached bytes and content type if younger than ``ttl`` seconds."""
        entry = self._values.get(key)
        if entry is None:
            return None
        stored_at, value, content_type = entry
        if self._clock() - stored_at > ttl:
            self._remove(key)
            return None
        self._values.move_to_end(key)
        return value, content_type

    def set(self, key: Hashable, value: bytes, content_type: str) -> None:
        """Store an item and evict least-recently-used data to stay bounded."""
        if key in self._values:
            self._remove(key)
        if len(value) > self._max_bytes:
            return
        self._values[key] = (self._clock(), value, content_type)
        self._size += len(value)
        while self._size > self._max_bytes:
            oldest = next(iter(self._values))
            self._remove(oldest)

    def discard_where(self, predicate: Callable[[Hashable], bool]) -> None:
        """Remove every cached item whose key matches ``predicate``."""
        for key in tuple(self._values):
            if predicate(key):
                self._remove(key)

    def _remove(self, key: Hashable) -> None:
        _stored_at, value, _content_type = self._values.pop(key)
        self._size -= len(value)
