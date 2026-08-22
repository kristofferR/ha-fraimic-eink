"""Tests for the persistent online-artwork/render cache."""

from __future__ import annotations

import asyncio
import gc
import os
import sys
import time
import types
from pathlib import Path
from types import SimpleNamespace

from conftest import load


def _load_cache(monkeypatch):
    homeassistant = types.ModuleType("homeassistant")
    core = types.ModuleType("homeassistant.core")
    core.HomeAssistant = object
    homeassistant.core = core
    monkeypatch.setitem(sys.modules, "homeassistant", homeassistant)
    monkeypatch.setitem(sys.modules, "homeassistant.core", core)
    sys.modules.pop("fraimic.artwork_cache", None)
    return load("artwork_cache")


class _Config:
    def __init__(self, root: Path) -> None:
        self.root = root

    def path(self, name: str) -> str:
        return str(self.root / name)


class _Entries:
    def __init__(self, entries: list[object]) -> None:
        self.entries = entries

    def async_entries(self, _domain: str) -> list[object]:
        return self.entries


class _Hass:
    def __init__(self, root: Path, entries: list[object]) -> None:
        self.config = _Config(root)
        self.config_entries = _Entries(entries)
        self.data = {}

    async def async_add_executor_job(self, func, *args):
        return func(*args)

    def async_create_background_task(self, coro, *, name: str):
        return asyncio.create_task(coro, name=name)


def test_source_and_render_survive_manager_restart(tmp_path, monkeypatch) -> None:
    cache_mod = _load_cache(monkeypatch)
    entry = SimpleNamespace(
        options={cache_mod.CONF_ARTWORK_CACHE: cache_mod.ARTWORK_CACHE_FOREVER}
    )
    hass = _Hass(tmp_path, [entry])

    async def run() -> None:
        first = cache_mod.ArtworkCache(hass)
        await first.async_setup()
        # Keep this test focused on I/O; cleanup has its own policy assertions.
        first._last_cleanup = time.monotonic()
        fetches = 0

        async def fetch() -> bytes:
            nonlocal fetches
            fetches += 1
            return b"downloaded-once"

        assert (
            await first.async_get_or_fetch_source("provider:x:1", entry, fetch)
            == b"downloaded-once"
        )
        assert (
            await first.async_get_or_fetch_source("provider:x:1", entry, fetch)
            == b"downloaded-once"
        )
        assert fetches == 1

        renders = 0

        async def render():
            nonlocal renders
            renders += 1
            return b"panel", b"preview", "floyd_steinberg"

        expected = b"panel", b"preview", "floyd_steinberg"
        assert await first.async_get_or_create_render(
            "provider:x:1", "raw-hash", "variant", entry, render
        ) == expected

        second = cache_mod.ArtworkCache(hass)
        await second.async_setup()
        second._last_cleanup = time.monotonic()
        assert (
            await second.async_get_source("provider:x:1", entry)
            == b"downloaded-once"
        )
        assert await second.async_get_or_create_render(
            "provider:x:1", "raw-hash", "variant", entry, render
        ) == expected
        assert renders == 1

    asyncio.run(run())


def test_forever_policy_wins_for_shared_cache(tmp_path, monkeypatch) -> None:
    cache_mod = _load_cache(monkeypatch)
    bounded = SimpleNamespace(
        options={
            cache_mod.CONF_ARTWORK_CACHE: cache_mod.ARTWORK_CACHE_30_DAYS,
            cache_mod.CONF_ARTWORK_CACHE_MAX_MB: 512,
        }
    )
    forever = SimpleNamespace(
        options={cache_mod.CONF_ARTWORK_CACHE: cache_mod.ARTWORK_CACHE_FOREVER}
    )
    manager = cache_mod.ArtworkCache(_Hass(tmp_path, [bounded, forever]))

    policy = manager.policy_for(bounded)
    assert policy.enabled
    assert policy.retention is None
    assert policy.max_bytes is None


def test_disabled_entry_does_not_use_shared_files(tmp_path, monkeypatch) -> None:
    cache_mod = _load_cache(monkeypatch)
    disabled = SimpleNamespace(options={cache_mod.CONF_ARTWORK_CACHE: "off"})
    enabled = SimpleNamespace(
        options={cache_mod.CONF_ARTWORK_CACHE: cache_mod.ARTWORK_CACHE_FOREVER}
    )
    hass = _Hass(tmp_path, [disabled, enabled])

    async def run() -> None:
        manager = cache_mod.ArtworkCache(hass)
        await manager.async_setup()
        await manager.async_store_source("same", enabled, b"cached")
        await manager.async_store_metadata("disabled", {"cached": False}, disabled)
        assert await manager.async_get_source("same", disabled) is None
        assert await manager.async_get_metadata("disabled", disabled) is None
        assert not manager._metadata_path("disabled").exists()

    asyncio.run(run())


def test_per_artwork_locks_are_released_when_idle(tmp_path, monkeypatch) -> None:
    cache_mod = _load_cache(monkeypatch)
    entry = SimpleNamespace(
        options={cache_mod.CONF_ARTWORK_CACHE: cache_mod.ARTWORK_CACHE_FOREVER}
    )
    hass = _Hass(tmp_path, [entry])

    async def run() -> None:
        manager = cache_mod.ArtworkCache(hass)
        await manager.async_setup()
        manager._last_cleanup = time.monotonic()

        async def fetch() -> bytes:
            return b"source"

        async def render():
            return b"panel", None, "auto"

        await manager.async_get_or_fetch_source("provider:one", entry, fetch)
        await manager.async_get_or_create_render(
            "provider:one", "digest", "variant", entry, render
        )
        gc.collect()
        assert not manager._locks

    asyncio.run(run())


def test_cleanup_expires_metadata_with_bounded_policy(tmp_path, monkeypatch) -> None:
    cache_mod = _load_cache(monkeypatch)
    manager = cache_mod.ArtworkCache(_Hass(tmp_path, []))
    manager._setup_sync()
    metadata = manager._metadata_path("old-search")
    manager._atomic_write(metadata, b'{}')
    old = time.time() - cache_mod.METADATA_MAX_AGE - 1
    os.utime(metadata, (old, old))

    manager._cleanup_sync(cache_mod.CachePolicy(True, None, None))

    assert not metadata.exists()


def test_cleanup_counts_metadata_toward_size_limit(tmp_path, monkeypatch) -> None:
    cache_mod = _load_cache(monkeypatch)
    manager = cache_mod.ArtworkCache(_Hass(tmp_path, []))
    manager._setup_sync()
    metadata = manager._metadata_path("older-search")
    manager._atomic_write(metadata, b"metadata-is-larger")
    manager._write_source_sync("newer-picture", b"image")
    old = time.time() - 120
    os.utime(metadata, (old, old))

    manager._cleanup_sync(cache_mod.CachePolicy(True, None, 5))

    assert not metadata.exists()
    assert manager._read_source_sync("newer-picture", None) == b"image"


def test_cleanup_removes_expired_items_and_evicts_lru(tmp_path, monkeypatch) -> None:
    cache_mod = _load_cache(monkeypatch)
    manager = cache_mod.ArtworkCache(_Hass(tmp_path, []))
    manager._setup_sync()
    manager._write_source_sync("stale", b"stale")
    manager._write_source_sync("fresh", b"fresh")
    stale_source = manager._item_dir("stale") / "source.bin"
    old = time.time() - 120
    os.utime(stale_source, (old, old))

    manager._cleanup_sync(cache_mod.CachePolicy(True, 60, None))

    assert not manager._item_dir("stale").exists()
    assert manager._item_dir("fresh").exists()

    manager._write_source_sync("older", b"older")
    older_source = manager._item_dir("older") / "source.bin"
    old = time.time() - 30
    os.utime(older_source, (old, old))
    manager._cleanup_sync(cache_mod.CachePolicy(True, None, len(b"fresh")))

    assert not manager._item_dir("older").exists()
    assert manager._item_dir("fresh").exists()
