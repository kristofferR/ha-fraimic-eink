"""Authenticated HTTP API backing the Fraimic panel.

All views live under ``/api/fraimic/`` and use Home Assistant's normal bearer
auth (``requires_auth`` default), so the frontend panel can call them with
``hass.fetchWithAuth`` and nothing is exposed to the LAN unauthenticated.
"""

from __future__ import annotations

import asyncio
import logging
import time
from http import HTTPStatus
from typing import Any
from urllib.parse import quote, urlencode

from aiohttp import web
from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .api import FraimicError
from .art_packs import ArtPackManager, ArtPackNotFoundError, get_pack_manager
from .const import (
    CONF_HEIGHT,
    CONF_ROTATION,
    CONF_WIDTH,
    DEFAULT_ROTATION,
    DOMAIN,
    MAX_SOURCE_BYTES,
)
from .coordinator import REDISCOVERY_FAIL_THRESHOLD
from .frame_name import frame_display_name
from .gallery_http import gallery_views
from .helpers import loaded_fraimic_entries
from .http_helpers import require_loaded_entry
from .library import FraimicLibrary, async_delete_library_image, get_library
from .overlays_http import overlay_views
from .playlists import DATA_PLAYLISTS, PlaylistManager
from .playlists_http import playlist_views
from .render.schema import ScreenConfig
from .scenes import SceneManager, SceneNotFoundError, get_scene_manager
from .screens_http import screens_views
from .services import begin_external_upload, finish_external_upload

_LOGGER = logging.getLogger(__name__)

DATA_VIEWS_REGISTERED = "views_registered"


def async_register_views(hass: HomeAssistant) -> None:
    """Register all Fraimic HTTP views (idempotent).

    aiohttp routes cannot be removed, so this happens once per HA run and the
    handlers look the library up lazily — a 503 answers any call that races an
    unloaded integration.
    """
    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get(DATA_VIEWS_REGISTERED):
        return
    domain_data[DATA_VIEWS_REGISTERED] = True
    for view in (
        LibraryListView(),
        LibraryUploadView(),
        LibraryImageView(),
        LibraryCropView(),
        LibraryPreviewView(),
        LibraryThumbView(),
        LibraryAlbumView(),
        LibrarySendView(),
        FramesView(),
        PlayerStateView(),
        PlayerArtworkView(),
        PlayerControlView(),
        PlayerQueueView(),
        ScenesView(),
        SceneView(),
        SceneSendView(),
        PacksView(),
        PackProgressView(),
        PackView(),
        PackInstallView(),
        PackUninstallView(),
        *playlist_views(),
        *gallery_views(),
        *overlay_views(),
        *screens_views(),
    ):
        hass.http.register_view(view)


class _FraimicView(HomeAssistantView):
    """Base class: resolves the library and normalizes error responses."""

    def _library(self, request: web.Request) -> FraimicLibrary:
        library = get_library(request.app[KEY_HASS])
        if library is None:
            raise web.HTTPServiceUnavailable(text="Fraimic is not set up")
        return library

    async def _json_body(self, request: web.Request) -> dict[str, Any]:
        try:
            data = await request.json()
        except ValueError:
            raise web.HTTPBadRequest(text="Body must be JSON") from None
        if not isinstance(data, dict):
            raise web.HTTPBadRequest(text="Body must be a JSON object")
        return data


class LibraryListView(_FraimicView):
    """List the library contents for the panel grid."""

    url = "/api/fraimic/library"
    name = "api:fraimic:library"

    async def get(self, request: web.Request) -> web.Response:
        library = self._library(request)
        images = sorted(
            library.images.values(), key=lambda image: image.uploaded_at, reverse=True
        )
        return self.json(
            {
                "images": [image.to_dict() for image in images],
                "albums": library.albums(),
            }
        )


class LibraryUploadView(_FraimicView):
    """Accept a multipart image upload into the library."""

    url = "/api/fraimic/library/upload"
    name = "api:fraimic:library:upload"

    async def post(self, request: web.Request) -> web.Response:
        library = self._library(request)
        try:
            reader = await request.multipart()
        except (AssertionError, ValueError):
            return self.json_message(
                "Expected a multipart upload", HTTPStatus.BAD_REQUEST
            )

        data: bytes | None = None
        filename = "image"
        albums: list[str] = []
        async for part in reader:
            if part.name == "file":
                filename = part.filename or filename
                chunks: list[bytes] = []
                size = 0
                while chunk := await part.read_chunk(64 * 1024):
                    size += len(chunk)
                    if size > MAX_SOURCE_BYTES:
                        return self.json_message(
                            "Image is too large", HTTPStatus.REQUEST_ENTITY_TOO_LARGE
                        )
                    chunks.append(chunk)
                data = b"".join(chunks)
            elif part.name == "album":
                albums.append((await part.text()).strip())

        if not data:
            return self.json_message("No file field in upload", HTTPStatus.BAD_REQUEST)
        try:
            image = await library.async_add_image(data, filename, albums=albums)
        except HomeAssistantError as err:
            return self.json_message(str(err), HTTPStatus.BAD_REQUEST)
        return self.json(image.to_dict())


class LibraryImageView(_FraimicView):
    """Serve, update, or delete one library image."""

    url = "/api/fraimic/library/image/{image_id}"
    name = "api:fraimic:library:image"

    async def get(self, request: web.Request, image_id: str) -> web.Response:
        library = self._library(request)
        try:
            data, content_type = await library.async_get_original(image_id)
        except HomeAssistantError as err:
            return self.json_message(str(err), HTTPStatus.NOT_FOUND)
        return web.Response(body=data, content_type=content_type)

    async def post(self, request: web.Request, image_id: str) -> web.Response:
        library = self._library(request)
        body = await self._json_body(request)
        albums = body.get("albums")
        if albums is not None and not (
            isinstance(albums, list) and all(isinstance(a, str) for a in albums)
        ):
            return self.json_message(
                "albums must be a list of strings", HTTPStatus.BAD_REQUEST
            )
        try:
            image = await library.async_update_image(image_id, albums=albums)
        except HomeAssistantError as err:
            return self.json_message(str(err), HTTPStatus.NOT_FOUND)
        return self.json(image.to_dict())

    async def delete(self, request: web.Request, image_id: str) -> web.Response:
        hass = request.app[KEY_HASS]
        try:
            await async_delete_library_image(hass, image_id)
        except HomeAssistantError as err:
            return self.json_message(str(err), HTTPStatus.NOT_FOUND)
        return self.json({"deleted": image_id})


class LibraryCropView(_FraimicView):
    """Save or clear the per-resolution manual crop for an image."""

    url = "/api/fraimic/library/image/{image_id}/crop"
    name = "api:fraimic:library:crop"

    async def post(self, request: web.Request, image_id: str) -> web.Response:
        library = self._library(request)
        body = await self._json_body(request)
        try:
            width = int(body["width"])
            height = int(body["height"])
        except (KeyError, TypeError, ValueError):
            return self.json_message(
                "width and height are required", HTTPStatus.BAD_REQUEST
            )
        box = body.get("box")
        rotate = body.get("rotate")
        if rotate is not None and rotate not in (0, 90, 180, 270):
            return self.json_message(
                "rotate must be 0, 90, 180 or 270", HTTPStatus.BAD_REQUEST
            )
        try:
            image = await library.async_set_crop(
                image_id, width, height, box, rotate=rotate
            )
        except ValueError as err:
            return self.json_message(str(err), HTTPStatus.BAD_REQUEST)
        except HomeAssistantError as err:
            return self.json_message(str(err), HTTPStatus.NOT_FOUND)
        return self.json(image.to_dict())


class LibraryPreviewView(_FraimicView):
    """Dithered e-ink preview of an image for a frame, with an ad-hoc crop.

    Powers the crop editor's "Preview on e-ink" button. Nothing is saved or
    uploaded; the response is the palette-exact PNG the renderer would show.
    """

    url = "/api/fraimic/library/image/{image_id}/preview"
    name = "api:fraimic:library:preview"

    async def post(self, request: web.Request, image_id: str) -> web.Response:
        hass = request.app[KEY_HASS]
        library = self._library(request)
        body = await self._json_body(request)
        entry_id = body.get("entry_id")
        entry = next(
            (e for e in loaded_fraimic_entries(hass) if e.entry_id == entry_id), None
        )
        if entry is None:
            return self.json_message(
                "Unknown or unloaded entry_id", HTTPStatus.BAD_REQUEST
            )
        rotate = body.get("rotate")
        if rotate is not None and rotate not in (0, 90, 180, 270):
            return self.json_message(
                "rotate must be 0, 90, 180 or 270", HTTPStatus.BAD_REQUEST
            )
        try:
            png = await library.async_render_adhoc_preview(
                image_id, entry, body.get("box"), rotate=rotate
            )
        except ValueError as err:
            return self.json_message(str(err), HTTPStatus.BAD_REQUEST)
        except HomeAssistantError as err:
            return self.json_message(str(err), HTTPStatus.BAD_REQUEST)
        return web.Response(body=png, content_type="image/png")


class LibraryThumbView(_FraimicView):
    """Serve the cached JPEG thumbnail for the panel grid."""

    url = "/api/fraimic/library/thumb/{image_id}"
    name = "api:fraimic:library:thumb"

    async def get(self, request: web.Request, image_id: str) -> web.Response:
        library = self._library(request)
        try:
            data = await library.async_get_thumbnail(image_id)
        except HomeAssistantError as err:
            return self.json_message(str(err), HTTPStatus.NOT_FOUND)
        return web.Response(
            body=data,
            content_type="image/jpeg",
            headers={"Cache-Control": "private, max-age=86400"},
        )


class LibraryAlbumView(_FraimicView):
    """Album operations (rename/delete) applied across the whole library."""

    url = "/api/fraimic/library/album"
    name = "api:fraimic:library:album"

    async def post(self, request: web.Request) -> web.Response:
        library = self._library(request)
        body = await self._json_body(request)
        action = body.get("action")
        name = body.get("name", "")
        try:
            if action == "rename":
                await library.async_rename_album(name, body.get("new_name", ""))
            elif action == "delete":
                await library.async_delete_album(name)
            else:
                return self.json_message(
                    "action must be rename or delete", HTTPStatus.BAD_REQUEST
                )
        except HomeAssistantError as err:
            return self.json_message(str(err), HTTPStatus.BAD_REQUEST)
        return self.json({"albums": library.albums()})


class LibrarySendView(_FraimicView):
    """Send one library image to one or more frames."""

    url = "/api/fraimic/library/send"
    name = "api:fraimic:library:send"

    async def post(self, request: web.Request) -> web.Response:
        hass = request.app[KEY_HASS]
        library = self._library(request)
        body = await self._json_body(request)
        image_id = body.get("image_id")
        if not isinstance(image_id, str):
            return self.json_message("image_id is required", HTTPStatus.BAD_REQUEST)

        entries = loaded_fraimic_entries(hass)
        if "entry_ids" in body:
            entry_ids = body["entry_ids"]
            if not isinstance(entry_ids, list) or not all(
                isinstance(entry_id, str) for entry_id in entry_ids
            ):
                return self.json_message(
                    "entry_ids must be a list", HTTPStatus.BAD_REQUEST
                )
            selected = set(entry_ids)
            entries = [entry for entry in entries if entry.entry_id in selected]
        if not entries:
            return self.json_message(
                "No matching loaded frames", HTTPStatus.BAD_REQUEST
            )

        async def _send(entry: ConfigEntry) -> str | None:
            scheduler = None
            uploaded = False
            try:
                scheduler = begin_external_upload(entry)
                await library.async_send_to_entry(image_id, entry)
                uploaded = True
            except Exception as err:
                _LOGGER.exception("Failed to send library image to %s", entry.entry_id)
                return str(err)
            finally:
                finish_external_upload(scheduler, uploaded=uploaded)
            return None

        errors = await asyncio.gather(*(_send(entry) for entry in entries))
        results = {
            entry.entry_id: {"ok": error is None, "error": error}
            for entry, error in zip(entries, errors, strict=True)
        }
        status = (
            HTTPStatus.OK
            if any(result["ok"] for result in results.values())
            else HTTPStatus.BAD_GATEWAY
        )
        return self.json({"results": results}, status_code=status)


class _SceneViewMixin(_FraimicView):
    """Adds scene-manager resolution to a view."""

    def _scenes(self, request: web.Request) -> SceneManager:
        manager = get_scene_manager(request.app[KEY_HASS])
        if manager is None:
            raise web.HTTPServiceUnavailable(text="Fraimic is not set up")
        return manager

    @staticmethod
    def _mappings_from(body: dict[str, Any]) -> dict[str, str] | None:
        mappings = body.get("mappings")
        if mappings is None:
            return None
        if not isinstance(mappings, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in mappings.items()
        ):
            raise web.HTTPBadRequest(text="mappings must map entry_id to image_id")
        return mappings


class ScenesView(_SceneViewMixin):
    """List and create scenes."""

    url = "/api/fraimic/scenes"
    name = "api:fraimic:scenes"

    async def get(self, request: web.Request) -> web.Response:
        manager = self._scenes(request)
        scenes = sorted(
            manager.scenes.values(), key=lambda scene: scene.name.casefold()
        )
        return self.json({"scenes": [scene.to_dict() for scene in scenes]})

    async def post(self, request: web.Request) -> web.Response:
        manager = self._scenes(request)
        body = await self._json_body(request)
        name = body.get("name", "")
        if not isinstance(name, str):
            return self.json_message("name must be a string", HTTPStatus.BAD_REQUEST)
        try:
            scene = await manager.async_create(name, self._mappings_from(body) or {})
        except HomeAssistantError as err:
            return self.json_message(str(err), HTTPStatus.BAD_REQUEST)
        return self.json(scene.to_dict())


class SceneView(_SceneViewMixin):
    """Update or delete one scene."""

    url = "/api/fraimic/scenes/{scene_id}"
    name = "api:fraimic:scene"

    async def post(self, request: web.Request, scene_id: str) -> web.Response:
        manager = self._scenes(request)
        body = await self._json_body(request)
        name = body.get("name")
        if name is not None and not isinstance(name, str):
            return self.json_message("name must be a string", HTTPStatus.BAD_REQUEST)
        try:
            scene = await manager.async_update(
                scene_id, name=name, mappings=self._mappings_from(body)
            )
        except SceneNotFoundError as err:
            return self.json_message(str(err), HTTPStatus.NOT_FOUND)
        except HomeAssistantError as err:
            return self.json_message(str(err), HTTPStatus.BAD_REQUEST)
        return self.json(scene.to_dict())

    async def delete(self, request: web.Request, scene_id: str) -> web.Response:
        manager = self._scenes(request)
        try:
            await manager.async_delete(scene_id)
        except HomeAssistantError as err:
            return self.json_message(str(err), HTTPStatus.NOT_FOUND)
        return self.json({"deleted": scene_id})


class SceneSendView(_SceneViewMixin):
    """Activate a scene from the panel."""

    url = "/api/fraimic/scenes/{scene_id}/send"
    name = "api:fraimic:scene:send"

    async def post(self, request: web.Request, scene_id: str) -> web.Response:
        manager = self._scenes(request)
        try:
            results = await manager.async_send(scene_id)
        except SceneNotFoundError as err:
            return self.json_message(str(err), HTTPStatus.NOT_FOUND)
        except HomeAssistantError as err:
            return self.json_message(str(err), HTTPStatus.BAD_GATEWAY)
        status = (
            HTTPStatus.OK
            if any(result["ok"] for result in results.values())
            else HTTPStatus.BAD_GATEWAY
        )
        return self.json({"results": results}, status_code=status)


class _PackViewMixin(_FraimicView):
    """Adds pack-manager resolution to a view."""

    def _packs(self, request: web.Request) -> ArtPackManager:
        manager = get_pack_manager(request.app[KEY_HASS])
        if manager is None:
            raise web.HTTPServiceUnavailable(text="Fraimic is not set up")
        return manager


class PacksView(_PackViewMixin):
    """Catalog + installed state for the panel's Add-ons tab."""

    url = "/api/fraimic/packs"
    name = "api:fraimic:packs"

    async def get(self, request: web.Request) -> web.Response:
        manager = self._packs(request)
        # Reframed's taxonomy takes several throttled requests. Never hold the
        # request open for it; the panel polls while the single-flight task runs.
        manager.schedule_reframed_refresh()
        await manager.async_refresh_remote()
        reframed_refreshing = manager.reframed_refreshing
        return self.json(
            {
                "packs": manager.status(),
                "reframed_refreshing": reframed_refreshing,
            }
        )


class PackProgressView(_PackViewMixin):
    """Return pack install counts without touching remote catalogs."""

    url = "/api/fraimic/packs/progress"
    name = "api:fraimic:packs:progress"

    async def get(self, request: web.Request) -> web.Response:
        return self.json({"packs": self._packs(request).install_progress()})


class PackView(_PackViewMixin):
    """Resolve one lazy pack for gallery browsing."""

    url = "/api/fraimic/packs/{pack_id}"
    name = "api:fraimic:packs:item"

    async def get(self, request: web.Request, pack_id: str) -> web.Response:
        try:
            pack = await self._packs(request).async_gallery(pack_id)
        except ArtPackNotFoundError as err:
            return self.json_message(str(err), HTTPStatus.NOT_FOUND)
        except HomeAssistantError as err:
            return self.json_message(str(err), HTTPStatus.SERVICE_UNAVAILABLE)
        return self.json({"pack": pack})


class PackInstallView(_PackViewMixin):
    """Install (or resume a partial install of) one pack."""

    url = "/api/fraimic/packs/{pack_id}/install"
    name = "api:fraimic:packs:install"

    async def post(self, request: web.Request, pack_id: str) -> web.Response:
        try:
            result = await self._packs(request).async_install(pack_id)
        except ArtPackNotFoundError as err:
            return self.json_message(str(err), HTTPStatus.NOT_FOUND)
        except HomeAssistantError as err:
            return self.json_message(str(err), HTTPStatus.BAD_GATEWAY)
        return self.json(result)


class PackUninstallView(_PackViewMixin):
    """Remove a pack's images from the library."""

    url = "/api/fraimic/packs/{pack_id}/uninstall"
    name = "api:fraimic:packs:uninstall"

    async def post(self, request: web.Request, pack_id: str) -> web.Response:
        try:
            result = await self._packs(request).async_uninstall(pack_id)
        except HomeAssistantError as err:
            return self.json_message(str(err), HTTPStatus.NOT_FOUND)
        return self.json(result)


class FramesView(_FraimicView):
    """Describe the configured frames for the panel's Frames tab."""

    url = "/api/fraimic/frames"
    name = "api:fraimic:frames"

    async def get(self, request: web.Request) -> web.Response:
        hass = request.app[KEY_HASS]
        frames = [
            _frame_payload(hass, entry) for entry in loaded_fraimic_entries(hass)
        ]
        return self.json({"frames": frames})


def _entry_by_id(hass: HomeAssistant, entry_id: object) -> ConfigEntry:
    """Resolve one loaded frame entry or reject the request."""
    entry = next(
        (candidate for candidate in loaded_fraimic_entries(hass) if candidate.entry_id == entry_id),
        None,
    )
    if entry is None:
        raise web.HTTPBadRequest(text="Unknown or unloaded entry_id")
    return entry


def _frame_payload(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    """Return the selected-frame fields used by the redesigned shell."""
    runtime = entry.runtime_data
    coordinator = runtime.coordinator
    info = coordinator.data or {}
    failures = coordinator.consecutive_failures
    online = coordinator.frame_online
    unreachable = (
        not online
        and not getattr(coordinator, "expected_asleep", False)
        and failures >= REDISCOVERY_FAIL_THRESHOLD
    )
    battery = info.get("battery") or {}
    name = frame_display_name(hass, entry)
    return {
        # New vocabulary-first shape plus the legacy aliases used underneath.
        "id": entry.entry_id,
        "name": name,
        "entry_id": entry.entry_id,
        "title": name,
        "host": runtime.client.host,
        "width": entry.data.get(CONF_WIDTH),
        "height": entry.data.get(CONF_HEIGHT),
        "rotation": entry.options.get(CONF_ROTATION, DEFAULT_ROTATION),
        "online": online,
        "asleep": not online and not unreachable,
        "unreachable": unreachable,
        "last_seen": coordinator.last_seen,
        "battery": battery.get("percent"),
        "charging": bool(battery.get("charging")),
        "firmware": info.get("firmware_version"),
    }


def _slide_meta(slide: ScreenConfig) -> str:
    """Concise queue metadata for one legacy scheduler slide."""
    source = slide.source or {}
    metadata = source.get("metadata") or {}
    if source.get("provider") and not source.get("provider_item"):
        return "Fresh artwork each rotation, nothing stored"
    if source.get("provider_item"):
        return (
            " · ".join(
                filter(None, (metadata.get("artist"), metadata.get("source_name")))
            )
            or "Picture"
        )
    if entity_id := source.get("entity"):
        return str(entity_id)
    if source.get("url") or source.get("library_image"):
        return "Picture"
    return "Home Assistant"


def _slide_payload(
    slide: ScreenConfig,
    *,
    thumbnail_url: str | None = None,
) -> dict[str, Any]:
    """Serialize one scheduler slide for a frame-shaped queue row."""
    source = slide.source or {}
    provider = source.get("provider")
    metadata = source.get("metadata") or {}
    return {
        "id": slide.screen_id,
        "title": slide.name,
        "meta": _slide_meta(slide),
        "thumbnail_url": (
            thumbnail_url
            or (
                f"/api/fraimic/library/thumb/{source['library_image']}"
                if source.get("library_image")
                else source.get("url") or metadata.get("thumbnail_url")
            )
        ),
        "library_image": source.get("library_image"),
        "live": bool(provider and not source.get("provider_item")),
        "shuffle_album": provider == "shuffle",
        "blank": False,
    }


def _player_payload(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    """Build the complete Phase 1 player and queue state for one frame."""
    runtime = entry.runtime_data
    scheduler = runtime.scheduler
    playlist_id = scheduler.playlist_id
    playlist_name = scheduler.playlist_name
    frame = _frame_payload(hass, entry)
    current = (
        scheduler.current_screen if scheduler.displayed_hash is not None else None
    )
    art = runtime.last_art or {}
    title = (
        art.get("title") or runtime.media_title or (current.name if current else None)
    )
    artist = art.get("artist")
    interval = scheduler.playlist_interval
    if interval is None and current is not None:
        interval = current.interval
    elapsed: int | None = None
    remaining: int | None = None
    if interval is not None and scheduler.last_rotation is not None:
        elapsed = max(
            0,
            int((dt_util.utcnow() - scheduler.last_rotation).total_seconds()),
        )
        remaining = max(0, interval - elapsed)
    if interval is not None and scheduler.hold_until is not None:
        held_remaining = max(
            0,
            int((scheduler.hold_until - dt_util.utcnow()).total_seconds()),
        )
        if held_remaining:
            remaining = min(interval, held_remaining)
            elapsed = max(0, interval - remaining)

    sending = scheduler.busy or scheduler.external_upload_active
    sending_progress: int | None = None
    if sending and scheduler.sending_started_at is not None:
        # The firmware blocks the accepted upload response during its roughly
        # 30-second redraw. This is an estimate, updated only when state is read.
        sending_progress = min(
            95,
            max(0, round((time.time() - scheduler.sending_started_at) / 30 * 100)),
        )

    if sending:
        state = "sending"
    elif frame["unreachable"]:
        state = "unreachable"
    elif frame["asleep"]:
        state = "asleep"
    elif title is None:
        state = "idle"
    else:
        state = "playing"

    artwork_url = (
        f"/api/fraimic/player/artwork/{entry.entry_id}"
        f"?v={runtime.displayed_preview_version}"
        if runtime.displayed_preview is not None
        else None
    )
    queued = scheduler.queued_slides
    full_upcoming = scheduler.playlist_up_next(limit=len(scheduler.screens))
    upcoming = full_upcoming[: 3 if scheduler.shuffle else 10]
    playlist_queue_count = len(full_upcoming)
    current_thumbnail = artwork_url if current is not None else None
    playlists = hass.data.get(DOMAIN, {}).get(DATA_PLAYLISTS)
    active_playlist = (
        playlists.get(playlist_id)
        if isinstance(playlists, PlaylistManager) and playlist_id is not None
        else None
    )
    active_slide_ids = (
        {slide.slide_id for slide in active_playlist.slides}
        if active_playlist is not None
        else set()
    )

    def queue_thumbnail(slide: ScreenConfig) -> str | None:
        if current is not None and slide.screen_id == current.screen_id:
            return current_thumbnail
        source = slide.source or {}
        fixed_picture = source.get("library_image") or (
            source.get("provider") and source.get("provider_item")
        )
        if (
            not fixed_picture
            or playlist_id is None
            or slide.screen_id not in active_slide_ids
        ):
            return None
        query = urlencode(
            {
                "entry_id": entry.entry_id,
                "v": f"{active_playlist.modified_at if active_playlist else 0:.6f}",
            }
        )
        return (
            f"/api/fraimic/playlists/{quote(playlist_id, safe='')}"
            f"/slides/{quote(slide.screen_id, safe='')}/thumbnail?{query}"
        )

    send_queue = runtime.send_queue
    waiting = int(send_queue is not None and send_queue.pending is not None)
    overlay_count = runtime.last_overlay_count
    return {
        "frame": frame,
        "state": state,
        "current": {
            "id": current.screen_id if current is not None else None,
            "title": scheduler.sending_slide_name or title,
            "artist": artist,
            "thumbnail_url": artwork_url,
        },
        "playlist_id": playlist_id if current is not None else None,
        "playlist_name": playlist_name if current is not None else None,
        "interval": interval,
        "seconds_elapsed": elapsed,
        "seconds_remaining": remaining,
        "paused": bool(current is not None and not scheduler.enabled),
        "transport_available": current is not None,
        "sending": sending,
        "sending_progress": sending_progress,
        "overlay_count": overlay_count,
        "queue_count": len(queued) + playlist_queue_count,
        "waiting_count": waiting,
        "hand_queue": [
            _slide_payload(slide, thumbnail_url=queue_thumbnail(slide))
            for slide in queued
        ],
        "playlist": {
            "id": playlist_id,
            "name": playlist_name,
            "interval": interval,
            "shuffle": scheduler.shuffle,
            "items": [
                _slide_payload(slide, thumbnail_url=queue_thumbnail(slide))
                for slide in upcoming
            ],
        },
    }


class PlayerStateView(_FraimicView):
    """Player bar and queue state for the selected frame."""

    url = "/api/fraimic/player"
    name = "api:fraimic:player"

    async def get(self, request: web.Request) -> web.Response:
        entry = require_loaded_entry(
            request.app[KEY_HASS], request.query.get("entry_id")
        )
        return self.json(_player_payload(request.app[KEY_HASS], entry))


class PlayerArtworkView(_FraimicView):
    """Serve the latest frame-shaped preview used by the player bar."""

    url = "/api/fraimic/player/artwork/{entry_id}"
    name = "api:fraimic:player:artwork"

    async def get(self, request: web.Request, entry_id: str) -> web.Response:
        entry = require_loaded_entry(request.app[KEY_HASS], entry_id)
        preview = entry.runtime_data.displayed_preview
        if preview is None:
            raise web.HTTPNotFound(text="No artwork preview is available")
        return web.Response(
            body=preview,
            content_type="image/png",
            headers={"Cache-Control": "private, no-store"},
        )


class PlayerControlView(_FraimicView):
    """Transport, retry, and basic frame controls for the player bar."""

    url = "/api/fraimic/player/control"
    name = "api:fraimic:player:control"

    async def post(self, request: web.Request) -> web.Response:
        body = await self._json_body(request)
        entry = require_loaded_entry(request.app[KEY_HASS], body.get("entry_id"))
        runtime = entry.runtime_data
        scheduler = runtime.scheduler
        action = body.get("action")
        try:
            if action == "previous":
                stopper = runtime.stop_camera_loop
                if stopper is not None:
                    stopper()
                if await scheduler.async_previous():
                    runtime.coordinator.async_set_frame_online(True)
            elif action == "next":
                stopper = runtime.stop_camera_loop
                if stopper is not None:
                    stopper()
                if await scheduler.async_next():
                    runtime.coordinator.async_set_frame_online(True)
            elif action == "pause":
                await scheduler.async_set_enabled(False)
            elif action == "play":
                stopper = runtime.stop_camera_loop
                if stopper is not None:
                    stopper()
                await scheduler.async_set_enabled(True)
            elif action == "toggle":
                enabled = not scheduler.enabled
                if enabled:
                    stopper = runtime.stop_camera_loop
                    if stopper is not None:
                        stopper()
                await scheduler.async_set_enabled(enabled)
            elif action == "retry":
                await runtime.coordinator.async_request_refresh()
            elif action == "refresh":
                scheduler.raise_if_upload_active()
                async with runtime.upload_lock:
                    scheduler.raise_if_upload_active()
                    await runtime.client.refresh()
                runtime.coordinator.async_set_frame_online(True)
            elif action == "sleep":
                await runtime.client.sleep()
                runtime.coordinator.async_set_frame_online(
                    False, expected_sleep=True
                )
            else:
                return self.json_message(
                    "Unknown player action", HTTPStatus.BAD_REQUEST
                )
        except (HomeAssistantError, FraimicError) as err:
            return self.json_message(str(err), HTTPStatus.BAD_GATEWAY)
        return self.json(_player_payload(request.app[KEY_HASS], entry))


class PlayerQueueView(_FraimicView):
    """Mutate the scheduler's hand queue or visible playlist order."""

    url = "/api/fraimic/player/queue"
    name = "api:fraimic:player:queue"

    async def post(self, request: web.Request) -> web.Response:
        body = await self._json_body(request)
        entry = require_loaded_entry(request.app[KEY_HASS], body.get("entry_id"))
        scheduler = entry.runtime_data.scheduler
        action = body.get("action")
        try:
            if action == "add":
                slide_id = body.get("slide_id")
                slide = next(
                    (
                        candidate
                        for candidate in scheduler.screens
                        if candidate.screen_id == slide_id
                    ),
                    None,
                )
                if slide is None:
                    return self.json_message(
                        "That slide is no longer available", HTTPStatus.NOT_FOUND
                    )
                await scheduler.async_add_to_queue(
                    slide, play_next=bool(body.get("play_next"))
                )
            elif action == "remove":
                index = body.get("index")
                slide_id = body.get("slide_id")
                if not isinstance(index, int) or isinstance(index, bool):
                    return self.json_message(
                        "index is required", HTTPStatus.BAD_REQUEST
                    )
                if not isinstance(slide_id, str):
                    return self.json_message(
                        "slide_id is required", HTTPStatus.BAD_REQUEST
                    )
                await scheduler.async_remove_from_queue(index, slide_id)
            elif action == "clear":
                await scheduler.async_clear_queue()
            elif action == "play":
                section = body.get("section")
                index = body.get("index")
                slide_id = body.get("slide_id")
                if section not in {"queue", "playlist"}:
                    return self.json_message(
                        "section must be queue or playlist", HTTPStatus.BAD_REQUEST
                    )
                if not isinstance(index, int) or isinstance(index, bool):
                    return self.json_message(
                        "index is required", HTTPStatus.BAD_REQUEST
                    )
                if not isinstance(slide_id, str):
                    return self.json_message(
                        "slide_id is required", HTTPStatus.BAD_REQUEST
                    )
                stopper = entry.runtime_data.stop_camera_loop
                if stopper is not None:
                    stopper()
                await scheduler.async_play_queue_item(section, index, slide_id)
            elif action == "reorder":
                section = body.get("section")
                ordered_ids = body.get("ordered_ids")
                if not isinstance(ordered_ids, list) or not all(
                    isinstance(slide_id, str) for slide_id in ordered_ids
                ):
                    return self.json_message(
                        "ordered_ids must be a list of slide ids",
                        HTTPStatus.BAD_REQUEST,
                    )
                if section == "queue":
                    await scheduler.async_reorder_queue(ordered_ids)
                elif section == "playlist":
                    if not getattr(request.get("hass_user"), "is_admin", False):
                        raise web.HTTPForbidden(text="Admin required")
                    playlist_id = scheduler.playlist_id
                    await scheduler.async_reorder_upcoming(ordered_ids)
                    if playlist_id is not None:
                        hass = request.app[KEY_HASS]
                        playlists = hass.data.get(DOMAIN, {}).get(DATA_PLAYLISTS)
                        if isinstance(playlists, PlaylistManager):
                            for candidate in loaded_fraimic_entries(hass):
                                if (
                                    candidate.entry_id != entry.entry_id
                                    and playlists.assignments.get(candidate.entry_id)
                                    == playlist_id
                                ):
                                    other_scheduler = candidate.runtime_data.scheduler
                                    await other_scheduler.async_refresh_playlist()
                else:
                    return self.json_message(
                        "section must be queue or playlist",
                        HTTPStatus.BAD_REQUEST,
                    )
            else:
                return self.json_message("Unknown queue action", HTTPStatus.BAD_REQUEST)
        except HomeAssistantError as err:
            return self.json_message(str(err), HTTPStatus.CONFLICT)
        return self.json(_player_payload(request.app[KEY_HASS], entry))
