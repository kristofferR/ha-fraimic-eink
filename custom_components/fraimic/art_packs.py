"""Curated art packs: one-click installs of public-domain artwork.

The catalog ships with the integration (``packs/catalog.json``); installing a
pack downloads its images from Wikimedia Commons into the library under an
album named after the pack, then creates/updates a scene assigning an
orientation-matched image to every loaded frame.

Downloads are throttled and sent with a descriptive User-Agent — Commons
rate-limits bursty anonymous clients hard (HTTP 429).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

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
from .pack_model import match_images_to_frames, validate_catalog
from .scene_model import SCENE_SOURCE_PACK
from .scenes import SceneManager

_LOGGER = logging.getLogger(__name__)

DATA_PACKS = "packs"
STORAGE_KEY = f"{DOMAIN}.packs"
STORAGE_VERSION = 1

DOWNLOAD_TIMEOUT = 120
# Seconds between Commons downloads; bursts get the whole install 429'd.
DOWNLOAD_DELAY = 2.0
USER_AGENT = "ha-fraimic-eink/1.0 (https://github.com/kristofferR/ha-fraimic-eink)"


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
        # pack_id -> {"installed_at": ts, "images": {url: image_id}}
        self.installed: dict[str, dict[str, Any]] = {}
        self._store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._install_lock = asyncio.Lock()

    async def async_setup(self) -> None:
        catalog_path = Path(__file__).parent / "packs" / "catalog.json"
        raw = await self.hass.async_add_executor_job(
            catalog_path.read_text, "utf-8"
        )
        self.packs = validate_catalog(json.loads(raw))
        data = await self._store.async_load()
        self.installed = (data or {}).get("installed", {})

    async def _async_save(self) -> None:
        await self._store.async_save({"installed": self.installed})

    def _get_pack(self, pack_id: str) -> dict[str, Any]:
        for pack in self.packs:
            if pack["id"] == pack_id:
                return pack
        raise HomeAssistantError(f"No art pack with id {pack_id}")

    def _live_images(self, pack_id: str) -> dict[str, str]:
        """The pack's installed url→image_id map, dropping deleted images."""
        record = self.installed.get(pack_id) or {}
        return {
            url: image_id
            for url, image_id in (record.get("images") or {}).items()
            if image_id in self.library.images
        }

    def status(self) -> list[dict[str, Any]]:
        """Catalog + installed state for the panel's Add-ons tab."""
        result = []
        for pack in self.packs:
            live = self._live_images(pack["id"])
            result.append(
                {
                    **pack,
                    "installed_count": len(live),
                    "installed": len(live) == len(pack["images"]),
                }
            )
        return result

    # --------------------------------------------------------------- install

    async def async_install(self, pack_id: str) -> dict[str, Any]:
        """Install (or repair) a pack. Already-present images are skipped, so
        a partially failed install just resumes on the next click."""
        async with self._install_lock:
            pack = self._get_pack(pack_id)
            session = async_get_clientsession(self.hass)
            live = self._live_images(pack_id)
            failed: list[dict[str, str]] = []
            downloaded = 0

            for image_def in pack["images"]:
                url = image_def["url"]
                if url in live:
                    continue
                try:
                    data = await self._async_download(session, url)
                    library_image = await self.library.async_add_image(
                        data, image_def["filename"], albums=[pack["name"]]
                    )
                except (HomeAssistantError, aiohttp.ClientError, asyncio.TimeoutError) as err:
                    _LOGGER.warning(
                        "Art pack %s: could not fetch %s: %s", pack_id, image_def["title"], err
                    )
                    failed.append({"title": image_def["title"], "error": str(err)})
                else:
                    live[url] = library_image.image_id
                    downloaded += 1
                await asyncio.sleep(DOWNLOAD_DELAY)

            self.installed[pack_id] = {"installed_at": time.time(), "images": live}
            await self._async_save()

            scene_id = None
            if live:
                scene_id = await self._async_sync_pack_scene(pack, list(live.values()))
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
            data = await resp.content.read(MAX_SOURCE_BYTES + 1)
            if len(data) > MAX_SOURCE_BYTES:
                raise HomeAssistantError("Downloaded image is too large")
            return data

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

        for scene in self.scenes.scenes.values():
            if scene.source == SCENE_SOURCE_PACK and scene.name == pack["name"]:
                updated = await self.scenes.async_update(scene.scene_id, mappings=mappings)
                return updated.scene_id
        created = await self.scenes.async_create(
            pack["name"], mappings, source=SCENE_SOURCE_PACK
        )
        return created.scene_id

    # ------------------------------------------------------------- uninstall

    async def async_uninstall(self, pack_id: str) -> dict[str, Any]:
        """Remove a pack's images from the library (scenes are pruned too)."""
        self._get_pack(pack_id)
        live = self._live_images(pack_id)
        for image_id in live.values():
            try:
                await self.library.async_delete_image(image_id)
            except HomeAssistantError:
                continue
            await self.scenes.async_prune_image(image_id)
        self.installed.pop(pack_id, None)
        await self._async_save()
        return {"pack_id": pack_id, "removed": len(live)}
