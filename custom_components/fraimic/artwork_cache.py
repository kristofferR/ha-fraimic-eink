"""Persistent cache for downloaded artwork and converted frame buffers.

The media library already owns permanent originals. This cache covers the
other half of the dashboard: provider thumbnails/originals and fixed online
playlist pictures. Entries are content-addressed on disk, shared by all
Fraimic frames, and safe to discard at any time.

``30_days`` is an access-based TTL plus a global LRU size bound. ``forever``
deliberately disables both expiry and size eviction. If multiple frames use
different policies, the most retentive enabled policy wins because the files
are shared and deleting one frame's cache would also delete another's.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import shutil
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from weakref import WeakValueDictionary

from homeassistant.core import HomeAssistant

from .const import (
    ARTWORK_CACHE_30_DAYS,
    ARTWORK_CACHE_DIR,
    ARTWORK_CACHE_FOREVER,
    CONF_ARTWORK_CACHE,
    CONF_ARTWORK_CACHE_MAX_MB,
    DEFAULT_ARTWORK_CACHE,
    DEFAULT_ARTWORK_CACHE_MAX_MB,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

DATA_ARTWORK_CACHE = "artwork_disk_cache"
THIRTY_DAYS = 30 * 24 * 60 * 60
METADATA_MAX_AGE = 7 * 24 * 60 * 60
MIN_CLEANUP_INTERVAL = 60 * 60


@dataclass(frozen=True)
class CachePolicy:
    """Effective domain-wide disk policy."""

    enabled: bool
    retention: float | None
    max_bytes: int | None


def get_artwork_cache(hass: HomeAssistant) -> ArtworkCache | None:
    """Return the domain-wide cache manager, if the integration is loaded."""
    return getattr(hass, "data", {}).get(DOMAIN, {}).get(DATA_ARTWORK_CACHE)


class ArtworkCache:
    """Disk-backed source/render cache with per-key request coalescing."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.root = Path(hass.config.path(ARTWORK_CACHE_DIR))
        self.items_dir = self.root / "items"
        self.metadata_dir = self.root / "metadata"
        # Callers keep a strong reference while using or waiting on a lock;
        # idle per-artwork locks disappear instead of growing for HA's lifetime.
        self._locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()
        self._cleanup_task: asyncio.Task | None = None
        self._last_cleanup = 0.0

    async def async_setup(self) -> None:
        """Create cache directories without blocking the event loop."""
        await self.hass.async_add_executor_job(self._setup_sync)

    def _setup_sync(self) -> None:
        self.items_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)

    def shutdown(self) -> None:
        """Cancel only the best-effort cleanup task."""
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            self._cleanup_task = None

    def schedule_cleanup(self, entry) -> None:
        """Apply expiry/size policy in the background, at most hourly."""
        self._schedule_cleanup(entry)

    # --------------------------------------------------------------- policy

    def policy_for(self, entry) -> CachePolicy:
        """Return the shared policy, respecting an explicit per-frame opt-out."""
        requested = entry.options.get(CONF_ARTWORK_CACHE, DEFAULT_ARTWORK_CACHE)
        if requested not in {ARTWORK_CACHE_30_DAYS, ARTWORK_CACHE_FOREVER}:
            return CachePolicy(False, 0, 0)

        entries = []
        try:
            entries = self.hass.config_entries.async_entries(DOMAIN)
        except (AttributeError, TypeError):
            pass
        if entry not in entries:
            entries = [*entries, entry]

        enabled = [
            candidate
            for candidate in entries
            if candidate.options.get(CONF_ARTWORK_CACHE, DEFAULT_ARTWORK_CACHE)
            in {ARTWORK_CACHE_30_DAYS, ARTWORK_CACHE_FOREVER}
        ]
        if any(
            candidate.options.get(CONF_ARTWORK_CACHE, DEFAULT_ARTWORK_CACHE)
            == ARTWORK_CACHE_FOREVER
            for candidate in enabled
        ):
            return CachePolicy(True, None, None)
        max_mb = max(
            int(
                candidate.options.get(
                    CONF_ARTWORK_CACHE_MAX_MB, DEFAULT_ARTWORK_CACHE_MAX_MB
                )
            )
            for candidate in enabled
        )
        return CachePolicy(True, THIRTY_DAYS, max_mb * 1024 * 1024)

    # --------------------------------------------------------------- sources

    async def async_get_source(self, cache_id: str, entry) -> bytes | None:
        """Read one downloaded source, touching its access timestamp."""
        policy = self.policy_for(entry)
        if not policy.enabled:
            return None
        return await self.hass.async_add_executor_job(
            self._read_source_sync, cache_id, policy.retention
        )

    async def async_store_source(
        self, cache_id: str, entry, value: bytes
    ) -> None:
        """Atomically persist downloaded bytes when caching is enabled."""
        if not self.policy_for(entry).enabled:
            return
        try:
            await self.hass.async_add_executor_job(
                self._write_source_sync, cache_id, value
            )
        except OSError as err:
            _LOGGER.warning("Could not write artwork cache entry %s: %s", cache_id, err)
            return
        self._schedule_cleanup(entry)

    async def async_get_or_fetch_source(
        self,
        cache_id: str,
        entry,
        loader: Callable[[], Awaitable[bytes]],
    ) -> bytes:
        """Return cached bytes or run one coalesced fetch for this key."""
        lock = self._locks.setdefault(f"source:{cache_id}", asyncio.Lock())
        async with lock:
            cached = await self.async_get_source(cache_id, entry)
            if cached is not None:
                return cached
            value = await loader()
            await self.async_store_source(cache_id, entry, value)
            return value

    def _read_source_sync(
        self, cache_id: str, retention: float | None
    ) -> bytes | None:
        item_dir = self._item_dir(cache_id)
        source = item_dir / "source.bin"
        try:
            stat = source.stat()
        except OSError:
            return None
        if retention is not None and time.time() - stat.st_mtime > retention:
            shutil.rmtree(item_dir, ignore_errors=True)
            return None
        try:
            value = source.read_bytes()
            if time.time() - stat.st_mtime > MIN_CLEANUP_INTERVAL:
                source.touch(exist_ok=True)
            return value
        except OSError:
            return None

    def _write_source_sync(self, cache_id: str, value: bytes) -> None:
        item_dir = self._item_dir(cache_id)
        item_dir.mkdir(parents=True, exist_ok=True)
        self._atomic_write(item_dir / "source.bin", value)

    # --------------------------------------------------------------- renders

    async def async_get_or_create_render(
        self,
        cache_id: str,
        raw_digest: str,
        variant: str,
        entry,
        creator: Callable[[], Awaitable[tuple[bytes, bytes | None, str]]],
    ) -> tuple[bytes, bytes | None, str]:
        """Return a cached conversion or create it exactly once concurrently."""
        policy = self.policy_for(entry)
        if not policy.enabled:
            return await creator()
        key = f"{raw_digest}_{variant}"
        lock = self._locks.setdefault(f"render:{cache_id}:{key}", asyncio.Lock())
        async with lock:
            cached = await self.hass.async_add_executor_job(
                self._read_render_sync, cache_id, key, policy.retention
            )
            if cached is not None:
                return cached
            rendered = await creator()
            try:
                await self.hass.async_add_executor_job(
                    self._write_render_sync, cache_id, key, rendered
                )
            except OSError as err:
                _LOGGER.warning(
                    "Could not cache rendered artwork %s (%s): %s",
                    cache_id,
                    variant,
                    err,
                )
            else:
                self._schedule_cleanup(entry)
            return rendered

    def _read_render_sync(
        self, cache_id: str, key: str, retention: float | None
    ) -> tuple[bytes, bytes | None, str] | None:
        render_dir = self._item_dir(cache_id) / "renders"
        bin_path = render_dir / f"{key}.bin"
        png_path = render_dir / f"{key}.png"
        meta_path = render_dir / f"{key}.json"
        try:
            stat = meta_path.stat()
            if retention is not None and time.time() - stat.st_mtime > retention:
                for path in (bin_path, png_path, meta_path):
                    path.unlink(missing_ok=True)
                return None
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            preview = png_path.read_bytes() if meta.get("preview", True) else None
            result = bin_path.read_bytes(), preview, str(meta.get("mode", "auto"))
            if time.time() - stat.st_mtime > MIN_CLEANUP_INTERVAL:
                meta_path.touch(exist_ok=True)
            return result
        except (OSError, ValueError):
            return None

    def _write_render_sync(
        self,
        cache_id: str,
        key: str,
        rendered: tuple[bytes, bytes | None, str],
    ) -> None:
        bin_data, preview_png, mode = rendered
        render_dir = self._item_dir(cache_id) / "renders"
        render_dir.mkdir(parents=True, exist_ok=True)
        self._atomic_write(render_dir / f"{key}.bin", bin_data)
        if preview_png is not None:
            self._atomic_write(render_dir / f"{key}.png", preview_png)
        self._atomic_write(
            render_dir / f"{key}.json",
            json.dumps(
                {"mode": mode, "preview": preview_png is not None},
                separators=(",", ":"),
            ).encode(),
        )

    # ---------------------------------------------------------- small JSON

    async def async_get_metadata(
        self,
        cache_id: str,
        entry,
        *,
        max_age: float | None = METADATA_MAX_AGE,
    ) -> Any | None:
        """Read small provider-list metadata persisted across HA restarts."""
        if not self.policy_for(entry).enabled:
            return None
        return await self.hass.async_add_executor_job(
            self._read_metadata_sync, cache_id, max_age
        )

    async def async_store_metadata(self, cache_id: str, value: Any, entry) -> None:
        """Persist JSON-compatible provider-list metadata."""
        if not self.policy_for(entry).enabled:
            return
        try:
            payload = json.dumps(
                {"stored_at": time.time(), "value": value},
                separators=(",", ":"),
            ).encode()
            await self.hass.async_add_executor_job(
                self._atomic_write, self._metadata_path(cache_id), payload
            )
        except (OSError, TypeError, ValueError) as err:
            _LOGGER.debug("Could not persist gallery metadata %s: %s", cache_id, err)
            return
        self._schedule_cleanup(entry)

    def _read_metadata_sync(
        self, cache_id: str, max_age: float | None
    ) -> Any | None:
        path = self._metadata_path(cache_id)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            stored_at = float(payload["stored_at"])
            if max_age is not None and time.time() - stored_at > max_age:
                path.unlink(missing_ok=True)
                return None
            return payload["value"]
        except (OSError, KeyError, TypeError, ValueError):
            return None

    # --------------------------------------------------------------- cleanup

    def _schedule_cleanup(self, entry) -> None:
        if time.monotonic() - self._last_cleanup < MIN_CLEANUP_INTERVAL:
            return
        if self._cleanup_task is not None and not self._cleanup_task.done():
            return
        policy = self.policy_for(entry)
        if not policy.enabled:
            return
        self._last_cleanup = time.monotonic()
        self._cleanup_task = self.hass.async_create_background_task(
            self._async_cleanup(policy), name="fraimic_artwork_cache_cleanup"
        )

    async def _async_cleanup(self, policy: CachePolicy) -> None:
        try:
            await self.hass.async_add_executor_job(self._cleanup_sync, policy)
        except asyncio.CancelledError:
            raise
        except Exception as err:  # noqa: BLE001 - cleanup is best-effort
            _LOGGER.warning("Artwork cache cleanup failed: %s", err)

    def _cleanup_sync(self, policy: CachePolicy) -> None:
        if not policy.enabled:
            return
        now = time.time()
        rows: list[tuple[float, int, Path, bool]] = []
        item_dirs = (
            item_dir
            for shard in self.items_dir.iterdir()
            if shard.is_dir()
            for item_dir in shard.iterdir()
            if item_dir.is_dir()
        )
        for item_dir in item_dirs:
            files = [path for path in item_dir.rglob("*") if path.is_file()]
            stats = []
            for path in files:
                try:
                    stats.append(path.stat())
                except OSError:
                    pass
            if not stats:
                shutil.rmtree(item_dir, ignore_errors=True)
                continue
            accessed = max(stat.st_mtime for stat in stats)
            if policy.retention is not None and now - accessed > policy.retention:
                shutil.rmtree(item_dir, ignore_errors=True)
                continue
            rows.append(
                (accessed, sum(stat.st_size for stat in stats), item_dir, True)
            )
        for path in self.metadata_dir.glob("*.json"):
            try:
                stat = path.stat()
            except OSError:
                continue
            if now - stat.st_mtime > METADATA_MAX_AGE:
                path.unlink(missing_ok=True)
                continue
            rows.append((stat.st_mtime, stat.st_size, path, False))
        if policy.max_bytes is None:
            return
        total = sum(size for _accessed, size, _path, _is_dir in rows)
        for _accessed, size, path, is_dir in sorted(rows):
            if total <= policy.max_bytes:
                break
            if is_dir:
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)
            total -= size

    # ---------------------------------------------------------------- paths

    def _item_dir(self, cache_id: str) -> Path:
        digest = hashlib.sha256(cache_id.encode()).hexdigest()
        return self.items_dir / digest[:2] / digest

    def _metadata_path(self, cache_id: str) -> Path:
        digest = hashlib.sha256(cache_id.encode()).hexdigest()
        return self.metadata_dir / f"{digest}.json"

    @staticmethod
    def _atomic_write(path: Path, value: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
        tmp.write_bytes(value)
        tmp.replace(path)


def raw_digest(value: bytes) -> str:
    """Short content digest used to invalidate changed remote originals."""
    return hashlib.sha256(value).hexdigest()[:24]
