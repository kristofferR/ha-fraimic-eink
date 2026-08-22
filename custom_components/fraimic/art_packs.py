"""Curated art packs: one-click installs of artwork.

Four catalog sources, merged in ``status()``:

- Bundled (``packs/catalog.json``): ships with the integration, always
  available, fails loudly on packaging bugs.
- Remote: dsackr's `frame-addons` community catalog (40+ packs, pre-sized
  images hosted on GitHub raw), fetched live with a TTL so new packs appear
  without an integration update. Failures fall back to whatever was cached —
  the tab degrades to bundled-only, never breaks.
- Reframed Gallery: its live Collections, Colors, Tags, Artists, Vertical, and
  Recently Added taxonomy. Rows are cheap lazy descriptors; installing one
  resolves a bounded set of current artwork into the normal library + scene.
- Wallhaven: static lazy rows for its SFW feeds, top ranges, categories, and
  colors. Installing resolves the current wallpapers for the frame's viewed
  orientation into the same library + scene flow.

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
    FIT_COVER,
    MAX_SOURCE_BYTES,
)
from .helpers import loaded_fraimic_entries
from .library import FraimicLibrary
from .pack_model import (
    REFRAMED_FALLBACK_COVER,
    REFRAMED_PACK_LIMIT,
    WALLHAVEN_FALLBACK_COVER,
    WALLHAVEN_PACK_LIMIT,
    make_reframed_pack,
    make_wallhaven_pack,
    map_remote_catalog,
    match_images_to_frames,
    materialize_reframed_pack,
    materialize_wallhaven_pack,
    reframed_filename,
    validate_catalog,
)
from .playlists import DATA_PLAYLISTS, PlaylistManager
from .providers.base import BrowseFolder
from .providers.curation import acceptable_for_fit
from .providers.ha import ArtFetchError, async_browse_provider
from .providers.wallhaven import (
    CATEGORY_FOLDERS,
    COLOR_FOLDERS,
    FEED_FOLDERS,
    TOP_FOLDERS,
)
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
REFRAMED_PACK_TTL = 6 * 3600
REFRAMED_PACK_FAILURE_TTL = 300
LAZY_PACK_MAX_EXTRA_PAGES = 4
WALLHAVEN_RANDOM_PACK_TTL = 300

REFRAMED_GROUPS = (
    ("collections", "Reframed Collections"),
    ("colors", "Reframed Colors"),
    ("tags", "Reframed Tags"),
)

WALLHAVEN_GROUPS = (
    ("Wallhaven Feeds", FEED_FOLDERS),
    ("Wallhaven Top", TOP_FOLDERS),
    ("Wallhaven Categories", CATEGORY_FOLDERS),
    ("Wallhaven Colors", COLOR_FOLDERS),
)


class ArtPackNotFoundError(HomeAssistantError):
    """Raised when an art-pack id is not in any catalog."""


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
        self.reframed_packs: list[dict[str, Any]] = []
        self.wallhaven_packs = [
            make_wallhaven_pack(folder.item_id, folder.title, category)
            for category, folders in WALLHAVEN_GROUPS
            for folder in folders
        ]
        self._remote_fetched_at: float = 0.0
        self._reframed_fetched_at: float = 0.0
        self._reframed_last_refresh_succeeded = False
        self._reframed_refresh_task: asyncio.Task[None] | None = None
        self._materialized_random_packs: dict[
            str, tuple[float, dict[str, Any]]
        ] = {}
        self._active_install_progress: dict[str, tuple[int, int]] = {}
        # pack_id -> installed image ids plus catalog metadata used after restart.
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
        await self._async_migrate_reframed_filenames()

    async def _async_migrate_reframed_filenames(self) -> None:
        """Give already-installed Reframed artwork human-readable filenames."""
        for image_id, library_image in self.library.images.items():
            if not (
                library_image.source_url
                and library_image.source_url.startswith(
                    "https://www.reframed.gallery/"
                )
                and library_image.attribution
            ):
                continue
            title, separator, _credit = library_image.attribution.partition(" — ")
            if not separator:
                continue
            filename = reframed_filename(
                title, library_image.filename, library_image.attribution
            )
            try:
                await self.library.async_rename_image(image_id, filename)
            except HomeAssistantError as err:
                _LOGGER.warning(
                    "Could not migrate Reframed image %s filename: %s",
                    image_id,
                    err,
                )

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

    async def async_refresh_reframed(self) -> None:
        """Refresh lazy art-pack rows from Reframed's live taxonomy."""
        if not self._reframed_refresh_due():
            return
        entries = loaded_fraimic_entries(self.hass)
        if not entries:
            self._reframed_fetched_at = time.time()
            self._reframed_last_refresh_succeeded = False
            return
        entry = entries[0]
        packs: dict[str, dict[str, Any]] = {}
        try:
            for browse_id, category in REFRAMED_GROUPS:
                page = await async_browse_provider(
                    self.hass, entry, "reframed", browse_id
                )
                for folder in page.folders:
                    pack = self._reframed_folder_pack(folder, category)
                    packs[pack["id"]] = pack

            artist_ranges = await async_browse_provider(
                self.hass, entry, "reframed", "artists"
            )
            for artist_range in artist_ranges.folders:
                page = await async_browse_provider(
                    self.hass, entry, "reframed", artist_range.item_id
                )
                for folder in page.folders:
                    pack = self._reframed_folder_pack(folder, "Reframed Artists")
                    packs[pack["id"]] = pack

            for folder in (
                BrowseFolder("verticals", "Vertical artworks"),
                BrowseFolder("recent", "Recently added"),
            ):
                pack = self._reframed_folder_pack(folder, "Reframed Gallery")
                packs[pack["id"]] = pack
        except ArtFetchError as err:
            self._reframed_fetched_at = time.time()
            self._reframed_last_refresh_succeeded = False
            _LOGGER.warning("Could not fetch the Reframed pack catalog: %s", err)
            return
        except Exception:
            self._reframed_fetched_at = time.time()
            self._reframed_last_refresh_succeeded = False
            _LOGGER.exception("Reframed pack catalog refresh failed")
            return

        self.reframed_packs = sorted(
            packs.values(), key=lambda pack: (pack["category"], pack["name"].casefold())
        )
        self._reframed_fetched_at = time.time()
        self._reframed_last_refresh_succeeded = True

    def _reframed_refresh_due(self) -> bool:
        ttl = (
            REFRAMED_PACK_TTL
            if self._reframed_last_refresh_succeeded
            else REFRAMED_PACK_FAILURE_TTL
        )
        return not self._reframed_fetched_at or (
            time.time() - self._reframed_fetched_at >= ttl
        )

    @property
    def reframed_refreshing(self) -> bool:
        """Whether the taxonomy is refreshing or still waiting to refresh."""
        task_running = bool(
            self._reframed_refresh_task
            and not self._reframed_refresh_task.done()
        )
        return task_running or self._reframed_refresh_due()

    @callback
    def schedule_reframed_refresh(self) -> None:
        """Start one background refresh when the cached taxonomy is stale."""
        if not self._reframed_refresh_due() or (
            self._reframed_refresh_task
            and not self._reframed_refresh_task.done()
        ):
            return
        task = self.hass.async_create_background_task(
            self.async_refresh_reframed(), name="fraimic_reframed_pack_catalog"
        )
        self._reframed_refresh_task = task
        task.add_done_callback(self._reframed_refresh_done)

    @callback
    def _reframed_refresh_done(self, task: asyncio.Task[None]) -> None:
        if self._reframed_refresh_task is task:
            self._reframed_refresh_task = None

    @staticmethod
    def _reframed_folder_pack(
        folder: BrowseFolder, category: str
    ) -> dict[str, Any]:
        return make_reframed_pack(
            folder.item_id,
            folder.title,
            category,
            cover_url=folder.thumb_url,
            source_count=folder.count,
        )

    async def _async_save(self) -> None:
        await self._store.async_save({"installed": self.installed})

    def _all_packs(self) -> list[dict[str, Any]]:
        return [
            *self.packs,
            *self.remote_packs,
            *self.reframed_packs,
            *self.wallhaven_packs,
        ]

    def _get_pack(self, pack_id: str) -> dict[str, Any]:
        for pack in self._all_packs():
            if pack["id"] == pack_id:
                return pack
        raise ArtPackNotFoundError(f"No art pack with id {pack_id}")

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
            catalog_images = pack["images"]
            current_urls = {image["url"] for image in catalog_images}
            live = self._live_images(
                pack["id"], current_urls if current_urls else None
            )
            record = self.installed.get(pack["id"]) or {}
            total = (
                len(current_urls)
                or int(record.get("total") or 0)
                or int(pack.get("image_count") or 0)
            )
            display_pack = pack
            if not catalog_images and live:
                installed_pack = self._installed_only_pack(pack["id"], record, live)
                cover_url = pack.get("cover_url")
                if cover_url in (
                    REFRAMED_FALLBACK_COVER,
                    WALLHAVEN_FALLBACK_COVER,
                ):
                    cover_url = installed_pack["cover_url"]
                display_pack = {
                    **pack,
                    "images": installed_pack["images"],
                    "cover_url": cover_url or installed_pack["cover_url"],
                }
            result.append(
                {
                    **display_pack,
                    "image_count": total,
                    "installed_count": len(live),
                    "installed": bool(total) and len(live) == total,
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

    def install_progress(self) -> dict[str, dict[str, int]]:
        """Return lightweight installed counts without refreshing catalogs."""
        progress = {}
        for pack_id, record in self.installed.items():
            live = self._live_images(pack_id)
            progress[pack_id] = {
                "installed_count": len(live),
                "total": int(record.get("total") or len(live)),
            }
        for pack_id, (installed_count, total) in self._active_install_progress.items():
            progress[pack_id] = {
                "installed_count": installed_count,
                "total": total,
            }
        return progress

    def _installed_only_pack(
        self, pack_id: str, record: dict[str, Any], live: dict[str, str]
    ) -> dict[str, Any]:
        """Build a catalog row for an installed pack missing from live catalogs."""
        images = []
        metadata = record.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        for url, image_id in live.items():
            library_image = self.library.images[image_id]
            image_metadata = metadata.get(url) or {}
            if not isinstance(image_metadata, dict):
                image_metadata = {}
            filename = Path(urlparse(url).path).name or f"{image_id}.jpg"
            images.append(
                {
                    "title": image_metadata.get("title") or library_image.filename,
                    "url": url,
                    "preview_url": image_metadata.get("preview_url") or url,
                    "filename": filename,
                    "source_url": image_metadata.get("source_url")
                    or library_image.source_url,
                    "license": image_metadata.get("license") or library_image.license,
                    "attribution": image_metadata.get("attribution")
                    or library_image.attribution,
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
        total: int | None = None,
        metadata: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        previous = self.installed.get(pack_id) or {}
        record: dict[str, Any] = {
            "installed_at": time.time(),
            "name": pack_name,
            "images": dict(images),
            "total": total or previous.get("total") or len(images),
            "metadata": metadata or previous.get("metadata") or {},
        }
        previous_scene_id = previous.get("scene_id")
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
            pack = await self._async_materialize_pack(pack)
            session = async_get_clientsession(self.hass)
            current_urls = {image["url"] for image in pack["images"]}
            metadata = {
                image["url"]: {
                    key: image.get(key)
                    for key in (
                        "title",
                        "preview_url",
                        "source_url",
                        "license",
                        "attribution",
                    )
                    if image.get(key)
                }
                for image in pack["images"]
            }
            all_live = self._live_images(pack_id)
            stale = {
                url: image_id
                for url, image_id in all_live.items()
                if url not in current_urls
            }
            live = {
                url: image_id
                for url, image_id in all_live.items()
                if url in current_urls
            }
            previous_metadata = (self.installed.get(pack_id) or {}).get("metadata")
            if not isinstance(previous_metadata, dict):
                previous_metadata = {}
            owned_metadata = {**previous_metadata, **metadata}
            failed: list[dict[str, str]] = []
            downloaded = 0
            total = len(pack["images"])
            self._active_install_progress[pack_id] = (len(live), total)

            try:
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
                    except (
                        HomeAssistantError,
                        aiohttp.ClientError,
                        asyncio.TimeoutError,
                    ) as err:
                        _LOGGER.warning(
                            "Art pack %s: could not fetch %s: %s",
                            pack_id,
                            image_def["title"],
                            err,
                        )
                        failed.append(
                            {"title": image_def["title"], "error": str(err)}
                        )
                    else:
                        live[url] = library_image.image_id
                        self._active_install_progress[pack_id] = (len(live), total)
                        self.installed[pack_id] = self._installed_record(
                            pack_id,
                            pack["name"],
                            {**stale, **live},
                            total=total,
                            metadata=owned_metadata,
                        )
                        await self._async_save()
                        downloaded += 1
                    delay = (
                        DOWNLOAD_DELAY_COMMONS
                        if "wikimedia.org" in url
                        else DOWNLOAD_DELAY_DEFAULT
                    )
                    await asyncio.sleep(delay)

                keep_stale = bool(stale and failed)
                committed = {**stale, **live} if stale else live
                committed_metadata = owned_metadata if stale else metadata
                self.installed[pack_id] = self._installed_record(
                    pack_id,
                    pack["name"],
                    committed,
                    total=total,
                    metadata=committed_metadata,
                )
                await self._async_save()

                scene_id = self.installed[pack_id].get("scene_id")
                if live and not keep_stale:
                    scene_id = await self._async_sync_pack_scene(
                        pack, list(live.values())
                    )
                    if stale:
                        await self._async_delete_pack_images(stale.values())
                    remaining_stale = {
                        url: image_id
                        for url, image_id in stale.items()
                        if image_id in self.library.images
                    }
                    self.installed[pack_id] = self._installed_record(
                        pack_id,
                        pack["name"],
                        {**remaining_stale, **live},
                        scene_id=scene_id,
                        total=total,
                        metadata=owned_metadata if remaining_stale else metadata,
                    )
                    await self._async_save()
                return {
                    "pack_id": pack_id,
                    "downloaded": downloaded,
                    "installed_count": len(live),
                    "total": total,
                    "failed": failed,
                    "scene_id": scene_id,
                }
            finally:
                self._active_install_progress.pop(pack_id, None)

    async def async_gallery(self, pack_id: str) -> dict[str, Any]:
        """Return a pack with its lazy provider artwork resolved."""
        return await self._async_materialize_pack(self._get_pack(pack_id))

    async def _async_materialize_pack(
        self, pack: dict[str, Any]
    ) -> dict[str, Any]:
        """Resolve a lazy provider row into a bounded current image list."""
        provider_path = pack.get("provider_path")
        if not isinstance(provider_path, str) or not provider_path:
            return pack
        if pack["images"]:
            return pack
        provider_key = pack.get("provider_key", "reframed")
        random_cache_key = (
            pack["id"]
            if provider_key == "wallhaven" and provider_path == "random"
            else None
        )
        if random_cache_key:
            cached = self._materialized_random_packs.get(random_cache_key)
            if cached and time.time() - cached[0] < WALLHAVEN_RANDOM_PACK_TTL:
                return cached[1]
        if provider_key == "reframed":
            pack_limit = REFRAMED_PACK_LIMIT
            materialize = materialize_reframed_pack
            provider_name = "Reframed"
        elif provider_key == "wallhaven":
            pack_limit = WALLHAVEN_PACK_LIMIT
            materialize = materialize_wallhaven_pack
            provider_name = "Wallhaven"
        else:
            raise HomeAssistantError(f"Unknown art-pack provider {provider_key}")
        entries = loaded_fraimic_entries(self.hass)
        if not entries:
            raise HomeAssistantError("No Fraimic frame is loaded")

        if provider_key == "wallhaven":
            entries_by_size = {
                self._viewed_size(entry): entry for entry in entries
            }
            candidate_groups = [
                await self._async_browse_pack_candidates(
                    entry,
                    provider_key,
                    provider_path,
                    pack_limit,
                    curate_for_entry=True,
                )
                for entry in entries_by_size.values()
            ]
            candidates = self._round_robin_candidates(
                candidate_groups, pack_limit
            )
        else:
            candidates = await self._async_browse_pack_candidates(
                entries[0], provider_key, provider_path, pack_limit
            )

        materialized = materialize(pack, candidates)
        if not materialized["images"]:
            raise HomeAssistantError(
                f"{provider_name} pack {pack['name']} currently has no downloadable artwork"
            )
        if random_cache_key:
            self._materialized_random_packs[random_cache_key] = (
                time.time(),
                materialized,
            )
        return materialized

    async def _async_browse_pack_candidates(
        self,
        entry: Any,
        provider_key: str,
        provider_path: str,
        pack_limit: int,
        *,
        curate_for_entry: bool = False,
    ) -> list[Any]:
        """Collect one bounded, deduplicated candidate group for a frame."""
        first_page = await async_browse_provider(
            self.hass, entry, provider_key, provider_path
        )
        candidates: list[Any] = []
        seen: set[str] = set()
        target_width, target_height = self._viewed_size(entry)

        def add(page_candidates: Iterable[Any]) -> None:
            for candidate in page_candidates:
                item_id = str(getattr(candidate, "item_id", ""))
                if not item_id or item_id in seen:
                    continue
                seen.add(item_id)
                candidate_width = getattr(candidate, "width", None)
                candidate_height = getattr(candidate, "height", None)
                if curate_for_entry and not (
                    candidate_width
                    and candidate_height
                    and acceptable_for_fit(
                        candidate_width,
                        candidate_height,
                        target_width,
                        target_height,
                        FIT_COVER,
                    )
                ):
                    continue
                candidates.append(candidate)
                if len(candidates) >= pack_limit:
                    break

        add(first_page.candidates)
        extra_pages = 0
        for folder in first_page.folders:
            if (
                len(candidates) >= pack_limit
                or extra_pages >= LAZY_PACK_MAX_EXTRA_PAGES
            ):
                break
            if not folder.item_id.startswith(f"{provider_path}/page/"):
                continue
            extra_pages += 1
            page = await async_browse_provider(
                self.hass, entry, provider_key, folder.item_id
            )
            add(page.candidates)
        return candidates

    @staticmethod
    def _round_robin_candidates(
        groups: list[list[Any]], limit: int
    ) -> list[Any]:
        """Interleave frame-specific pools so every orientation is represented."""
        candidates: list[Any] = []
        seen: set[str] = set()
        for index in range(max((len(group) for group in groups), default=0)):
            for group in groups:
                if index >= len(group):
                    continue
                candidate = group[index]
                item_id = str(getattr(candidate, "item_id", ""))
                if not item_id or item_id in seen:
                    continue
                seen.add(item_id)
                candidates.append(candidate)
                if len(candidates) >= limit:
                    return candidates
        return candidates

    @staticmethod
    def _viewed_size(entry: Any) -> tuple[int, int]:
        width = entry.data.get(CONF_WIDTH, DEFAULT_WIDTH)
        height = entry.data.get(CONF_HEIGHT, DEFAULT_HEIGHT)
        if entry.options.get(CONF_ROTATION, DEFAULT_ROTATION) in (90, 270):
            return height, width
        return width, height

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
            width, height = self._viewed_size(entry)
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
        """Delete pack-owned images and prune every stored reference."""
        for image_id in image_ids:
            try:
                await self.library.async_delete_image(image_id)
            except HomeAssistantError:
                continue
            await self.scenes.async_prune_image(image_id)
            domain_data = getattr(self.hass, "data", {}).get(DOMAIN, {})
            playlists = domain_data.get(DATA_PLAYLISTS)
            if isinstance(playlists, PlaylistManager):
                affected = await playlists.async_prune_image(image_id)
                for entry in loaded_fraimic_entries(self.hass):
                    if playlists.assignments.get(entry.entry_id) in affected:
                        await entry.runtime_data.scheduler.async_refresh_playlist()
