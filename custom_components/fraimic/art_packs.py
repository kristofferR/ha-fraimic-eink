"""Curated art packs: one-click installs of public-domain artwork.

Two catalog sources, merged in ``status()``:

- Bundled (``packs/catalog.json``): ships with the integration, always
  available, fails loudly on packaging bugs.
- Remote: dsackr's `frame-addons` community catalog (40+ packs, pre-sized
  images hosted on GitHub raw), fetched live with a TTL so new packs appear
  without an integration update. Failures fall back to whatever was cached —
  the tab degrades to bundled-only, never breaks.

Installing a pack downloads its images into the library under a pack-named
album, then creates/updates a scene assigning an orientation-matched image to
every loaded frame. Downloads are throttled per host and sent with a
descriptive User-Agent — Wikimedia Commons rate-limits bursty anonymous
clients hard (HTTP 429); GitHub raw needs only a light touch.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import aiohttp
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .const import (
    CONF_HEIGHT,
    CONF_ROTATION,
    CONF_WIDTH,
    DEFAULT_HEIGHT,
    DEFAULT_ROTATION,
    DEFAULT_WIDTH,
    DOMAIN,
    MAX_SOURCE_BYTES,
)
from .helpers import loaded_fraimic_entries
from .library import FraimicLibrary
from .pack_model import map_remote_catalog, match_images_to_frames, validate_catalog
from .scene_model import SCENE_SOURCE_PACK, Scene
from .scenes import SceneManager

_LOGGER = logging.getLogger(__name__)

DATA_PACKS = "packs"
STORAGE_KEY = f"{DOMAIN}.packs"
STORAGE_VERSION = 1

DOWNLOAD_TIMEOUT = 120
# Seconds between downloads from Wikimedia Commons (bursts get the whole
# install 429'd) vs. everything else (GitHub raw just needs a light touch).
DOWNLOAD_DELAY_COMMONS = 2.0
DOWNLOAD_DELAY_DEFAULT = 0.4
USER_AGENT = "ha-fraimic-eink/1.0 (https://github.com/kristofferR/ha-fraimic-eink)"

# Community catalog: dsackr/frame-addons (per-image public-domain attribution
# in its index; ``widget``-type packs are scripts for another integration and
# are skipped by the mapper).
REMOTE_PACK_RAW_BASE = "https://raw.githubusercontent.com/dsackr/frame-addons/main"
REMOTE_PACK_INDEX_URL = f"{REMOTE_PACK_RAW_BASE}/scene_packs/index.json"
REMOTE_PACK_TTL = 6 * 3600
REMOTE_PACK_FAILURE_TTL = 300


@callback
def get_pack_manager(hass: HomeAssistant) -> ArtPackManager | None:
    """Return the domain-wide pack manager, if initialized."""
    return hass.data.get(DOMAIN, {}).get(DATA_PACKS)


class ArtPackManager:
    """Loads the bundled catalog and installs/uninstalls packs."""

    def __init__(
        self, hass: HomeAssistant, library: FraimicLibrary, scenes: SceneManager
    ) -> None:
        self.hass = hass
        self.library = library
        self.scenes = scenes
        self.packs: list[dict[str, Any]] = []
        self.remote_packs: list[dict[str, Any]] = []
        self._remote_fetched_at: float = 0.0
        # pack_id -> {"installed_at": ts, "images": {url: image_id}}
        self.installed: dict[str, dict[str, Any]] = {}
        self._store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._install_lock = asyncio.Lock()

    async def async_setup(self) -> None:
        catalog_path = Path(__file__).parent / "packs" / "catalog.json"
        try:
            raw = await self.hass.async_add_executor_job(
                catalog_path.read_text, "utf-8"
            )
            self.packs = validate_catalog(json.loads(raw))
        except (OSError, TypeError, ValueError):
            _LOGGER.exception("Could not load bundled art pack catalog")
            self.packs = []
        data = await self._store.async_load()
        self.installed = (data or {}).get("installed", {})

    async def async_refresh_remote(self) -> None:
        """Fetch the community catalog if the cached copy is stale.

        Never raises: an unreachable index just leaves the previous (possibly
        empty) remote list in place.
        """
        now = time.time()
        ttl = REMOTE_PACK_TTL if self.remote_packs else REMOTE_PACK_FAILURE_TTL
        if self._remote_fetched_at and now - self._remote_fetched_at < ttl:
            return
        session = async_get_clientsession(self.hass)
        try:
            resp = await session.get(
                REMOTE_PACK_INDEX_URL,
                timeout=aiohttp.ClientTimeout(total=30),
                headers={"User-Agent": USER_AGENT},
            )
            async with resp:
                if resp.status != 200:
                    raise HomeAssistantError(f"HTTP {resp.status}")
                data = await resp.json(content_type=None)
        except (
            HomeAssistantError,
            aiohttp.ClientError,
            asyncio.TimeoutError,
            TypeError,
            ValueError,
        ) as err:
            self._remote_fetched_at = time.time()
            _LOGGER.warning("Could not fetch the community pack catalog: %s", err)
            return
        self.remote_packs = map_remote_catalog(data or {}, REMOTE_PACK_RAW_BASE)
        self._remote_fetched_at = time.time()

    async def _async_save(self) -> None:
        await self._store.async_save({"installed": self.installed})

    def _all_packs(self) -> list[dict[str, Any]]:
        return [*self.packs, *self.remote_packs]

    def _get_pack(self, pack_id: str) -> dict[str, Any]:
        for pack in self._all_packs():
            if pack["id"] == pack_id:
                return pack
        raise HomeAssistantError(f"No art pack with id {pack_id}")

    def _live_images(
        self, pack_id: str, current_urls: set[str] | None = None
    ) -> dict[str, str]:
        """The pack's installed url→image_id map, dropping deleted images."""
        record = self.installed.get(pack_id) or {}
        return {
            url: image_id
            for url, image_id in (record.get("images") or {}).items()
            if image_id in self.library.images
            and (current_urls is None or url in current_urls)
        }

    def status(self) -> list[dict[str, Any]]:
        """Merged catalog + installed state for the panel's Art Packs tab."""
        result = []
        seen_ids = set()
        for pack in self._all_packs():
            seen_ids.add(pack["id"])
            current_urls = {image["url"] for image in pack["images"]}
            live = self._live_images(pack["id"], current_urls)
            result.append(
                {
                    **pack,
                    "installed_count": len(live),
                    "installed": bool(current_urls) and set(live) == current_urls,
                }
            )
        for pack_id, record in self.installed.items():
            if pack_id in seen_ids:
                continue
            live = self._live_images(pack_id)
            if not live:
                continue
            pack = self._installed_only_pack(pack_id, record, live)
            result.append(
                {
                    **pack,
                    "installed_count": len(live),
                    "installed": True,
                }
            )
        return result

    def _installed_only_pack(
        self, pack_id: str, record: dict[str, Any], live: dict[str, str]
    ) -> dict[str, Any]:
        """Build a catalog row for an installed pack missing from live catalogs."""
        images = []
        for url, image_id in live.items():
            filename = Path(urlparse(url).path).name or f"{image_id}.jpg"
            images.append(
                {
                    "title": self.library.images[image_id].filename,
                    "url": url,
                    "preview_url": url,
                    "filename": filename,
                }
            )
        return {
            "id": pack_id,
            "name": str(record.get("name") or pack_id),
            "category": "Installed",
            "description": "Installed pack not currently available in the catalog.",
            "attribution": "See original catalog source",
            "cover_url": images[0]["url"],
            "images": images,
        }

    def _installed_record(
        self,
        pack_id: str,
        pack_name: str,
        images: dict[str, str],
        *,
        scene_id: str | None = None,
    ) -> dict[str, Any]:
        record: dict[str, Any] = {
            "installed_at": time.time(),
            "name": pack_name,
            "images": dict(images),
        }
        previous_scene_id = (self.installed.get(pack_id) or {}).get("scene_id")
        scene_id = scene_id or previous_scene_id
        if isinstance(scene_id, str) and scene_id:
            record["scene_id"] = scene_id
        return record

    # --------------------------------------------------------------- install

    async def async_install(self, pack_id: str) -> dict[str, Any]:
        """Install (or repair) a pack. Already-present images are skipped, so
        a partially failed install just resumes on the next click."""
        async with self._install_lock:
            pack = self._get_pack(pack_id)
            session = async_get_clientsession(self.hass)
            current_urls = {image["url"] for image in pack["images"]}
            all_live = self._live_images(pack_id)
            stale = {
                url: image_id
                for url, image_id in all_live.items()
                if url not in current_urls
            }
            if stale:
                await self._async_delete_pack_images(stale.values())
            live = {
                url: image_id
                for url, image_id in all_live.items()
                if url in current_urls
            }
            failed: list[dict[str, str]] = []
            downloaded = 0

            for image_def in pack["images"]:
                url = image_def["url"]
                if url in live:
                    continue
                try:
                    data = await self._async_download(session, url)
                    library_image = await self.library.async_add_image(
                        data,
                        image_def["filename"],
                        albums=[pack["name"]],
                        source_url=image_def.get("source_url"),
                        license_text=image_def.get("license"),
                        attribution=image_def.get("attribution"),
                    )
                except (HomeAssistantError, aiohttp.ClientError, asyncio.TimeoutError) as err:
                    _LOGGER.warning(
                        "Art pack %s: could not fetch %s: %s", pack_id, image_def["title"], err
                    )
                    failed.append({"title": image_def["title"], "error": str(err)})
                else:
                    live[url] = library_image.image_id
                    self.installed[pack_id] = self._installed_record(
                        pack_id, pack["name"], live
                    )
                    await self._async_save()
                    downloaded += 1
                delay = (
                    DOWNLOAD_DELAY_COMMONS
                    if "wikimedia.org" in url
                    else DOWNLOAD_DELAY_DEFAULT
                )
                await asyncio.sleep(delay)

            self.installed[pack_id] = self._installed_record(
                pack_id, pack["name"], live
            )
            await self._async_save()

            scene_id = None
            if live:
                scene_id = await self._async_sync_pack_scene(pack, list(live.values()))
                self.installed[pack_id] = self._installed_record(
                    pack_id, pack["name"], live, scene_id=scene_id
                )
                await self._async_save()
            return {
                "pack_id": pack_id,
                "downloaded": downloaded,
                "installed_count": len(live),
                "total": len(pack["images"]),
                "failed": failed,
                "scene_id": scene_id,
            }

    async def _async_download(self, session: aiohttp.ClientSession, url: str) -> bytes:
        resp = await session.get(
            url,
            timeout=aiohttp.ClientTimeout(total=DOWNLOAD_TIMEOUT),
            headers={"User-Agent": USER_AGENT},
        )
        async with resp:
            if resp.status != 200:
                raise HomeAssistantError(f"HTTP {resp.status} from {url}")
            chunks: list[bytes] = []
            size = 0
            while chunk := await resp.content.read(64 * 1024):
                size += len(chunk)
                if size > MAX_SOURCE_BYTES:
                    raise HomeAssistantError("Downloaded image is too large")
                chunks.append(chunk)
            return b"".join(chunks)

    async def _async_sync_pack_scene(
        self, pack: dict[str, Any], image_ids: list[str]
    ) -> str | None:
        """Create or update the pack's auto-scene with orientation matching."""
        frames = []
        for entry in loaded_fraimic_entries(self.hass):
            width = entry.data.get(CONF_WIDTH, DEFAULT_WIDTH)
            height = entry.data.get(CONF_HEIGHT, DEFAULT_HEIGHT)
            if entry.options.get(CONF_ROTATION, DEFAULT_ROTATION) in (90, 270):
                width, height = height, width
            frames.append((entry.entry_id, width, height))
        if not frames:
            return None

        images = [
            (image.image_id, image.width, image.height)
            for image_id in image_ids
            if (image := self.library.images.get(image_id))
        ]
        mappings = match_images_to_frames(frames, images)
        if not mappings:
            return None

        installed_image_ids = set(image_ids)
        for scene in self.scenes.scenes.values():
            if self._is_pack_scene(
                scene, pack["id"], pack["name"], installed_image_ids
            ):
                merged_mappings = {**scene.mappings, **mappings}
                updated = await self.scenes.async_update(
                    scene.scene_id, mappings=merged_mappings, source_id=pack["id"]
                )
                return updated.scene_id
        scene_name = self._available_pack_scene_name(pack["name"])
        created = await self.scenes.async_create(
            scene_name, mappings, source=SCENE_SOURCE_PACK, source_id=pack["id"]
        )
        return created.scene_id

    def _is_pack_scene(
        self,
        scene: Scene,
        pack_id: str,
        pack_name: str | None,
        installed_image_ids: set[str],
    ) -> bool:
        if scene.source != SCENE_SOURCE_PACK:
            return False
        if scene.source_id == pack_id:
            return True
        record_scene_id = (self.installed.get(pack_id) or {}).get("scene_id")
        if isinstance(record_scene_id, str) and scene.scene_id == record_scene_id:
            return True
        if scene.source_id:
            return False
        if pack_name is None:
            return False
        if not (
            scene.name == pack_name or self._is_pack_scene_name(scene.name, pack_name)
        ):
            return False
        return bool(installed_image_ids) and any(
            image_id in installed_image_ids for image_id in scene.mappings.values()
        )

    @staticmethod
    def _pack_scene_name(pack_name: str) -> str:
        return f"{pack_name} (Pack)"

    @classmethod
    def _is_pack_scene_name(cls, scene_name: str, pack_name: str) -> bool:
        prefix = f"{pack_name} (Pack "
        return scene_name == cls._pack_scene_name(pack_name) or (
            scene_name.startswith(prefix) and scene_name.endswith(")")
        )

    def _available_pack_scene_name(self, pack_name: str) -> str:
        """Return a name that will not collide with user-created scenes."""
        existing = {
            scene.name.strip().casefold() for scene in self.scenes.scenes.values()
        }
        if pack_name.strip().casefold() not in existing:
            return pack_name
        base = self._pack_scene_name(pack_name)
        if base.casefold() not in existing:
            return base
        suffix = 2
        while True:
            candidate = f"{pack_name} (Pack {suffix})"
            if candidate.casefold() not in existing:
                return candidate
            suffix += 1

    # ------------------------------------------------------------- uninstall

    async def async_uninstall(self, pack_id: str) -> dict[str, Any]:
        """Remove a pack's images from the library (scenes are pruned too)."""
        async with self._install_lock:
            record = self.installed.get(pack_id)
            try:
                pack = self._get_pack(pack_id)
            except HomeAssistantError:
                if record is None:
                    raise
                pack = None
            pack_name = (pack or record or {}).get("name")
            live = self._live_images(pack_id)
            pack_scene_ids = self._pack_scene_ids(
                pack_id, pack_name, set(live.values())
            )
            await self._async_delete_pack_images(live.values())
            for scene_id in pack_scene_ids:
                try:
                    await self.scenes.async_delete(scene_id)
                except HomeAssistantError:
                    continue
            self.installed.pop(pack_id, None)
            await self._async_save()
            return {"pack_id": pack_id, "removed": len(live)}

    def _pack_scene_ids(
        self, pack_id: str, pack_name: str | None, image_ids: set[str]
    ) -> list[str]:
        """Find auto-scenes owned by a pack before uninstall pruning mutates them."""
        scene_ids = []
        for scene in self.scenes.scenes.values():
            if self._is_pack_scene(scene, pack_id, pack_name, image_ids):
                scene_ids.append(scene.scene_id)
        return scene_ids

    async def _async_delete_pack_images(self, image_ids: Iterable[str]) -> None:
        """Delete pack-owned images and prune references from scenes."""
        for image_id in image_ids:
            try:
                await self.library.async_delete_image(image_id)
            except HomeAssistantError:
                continue
            await self.scenes.async_prune_image(image_id)
