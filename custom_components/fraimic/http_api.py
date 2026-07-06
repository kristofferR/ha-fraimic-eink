"""Authenticated HTTP API backing the Fraimic panel.

All views live under ``/api/fraimic/`` and use Home Assistant's normal bearer
auth (``requires_auth`` default), so the frontend panel can call them with
``hass.fetchWithAuth`` and nothing is exposed to the LAN unauthenticated.
"""

from __future__ import annotations

import asyncio
import logging
from http import HTTPStatus
from typing import Any

from aiohttp import web
from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .art_packs import ArtPackManager, get_pack_manager
from .const import CONF_HEIGHT, CONF_ROTATION, CONF_WIDTH, DEFAULT_ROTATION, DOMAIN, MAX_SOURCE_BYTES
from .helpers import loaded_fraimic_entries
from .library import FraimicLibrary, get_library
from .scenes import SceneManager, get_scene_manager
from .screens_http import screens_views

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
        ScenesView(),
        SceneView(),
        SceneSendView(),
        PacksView(),
        PackInstallView(),
        PackUninstallView(),
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
            return self.json_message("albums must be a list of strings", HTTPStatus.BAD_REQUEST)
        try:
            image = await library.async_update_image(image_id, albums=albums)
        except HomeAssistantError as err:
            return self.json_message(str(err), HTTPStatus.NOT_FOUND)
        return self.json(image.to_dict())

    async def delete(self, request: web.Request, image_id: str) -> web.Response:
        library = self._library(request)
        try:
            await library.async_delete_image(image_id)
        except HomeAssistantError as err:
            return self.json_message(str(err), HTTPStatus.NOT_FOUND)
        # Scenes must not keep dangling references to a deleted image.
        if scenes := get_scene_manager(request.app[KEY_HASS]):
            await scenes.async_prune_image(image_id)
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
        try:
            image = await library.async_set_crop(image_id, width, height, box)
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
            return self.json_message("Unknown or unloaded entry_id", HTTPStatus.BAD_REQUEST)
        try:
            png = await library.async_render_adhoc_preview(
                image_id, entry, body.get("box")
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
        if entry_ids := body.get("entry_ids"):
            entries = [entry for entry in entries if entry.entry_id in entry_ids]
        if not entries:
            return self.json_message("No matching loaded frames", HTTPStatus.BAD_REQUEST)

        async def _send(entry: ConfigEntry) -> str | None:
            try:
                await library.async_send_to_entry(image_id, entry)
            except HomeAssistantError as err:
                return str(err)
            return None

        errors = await asyncio.gather(*(_send(entry) for entry in entries))
        results = {
            entry.entry_id: {"ok": error is None, "error": error}
            for entry, error in zip(entries, errors)
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
        scenes = sorted(manager.scenes.values(), key=lambda scene: scene.name.casefold())
        return self.json({"scenes": [scene.to_dict() for scene in scenes]})

    async def post(self, request: web.Request) -> web.Response:
        manager = self._scenes(request)
        body = await self._json_body(request)
        try:
            scene = await manager.async_create(
                str(body.get("name", "")), self._mappings_from(body) or {}
            )
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
        # TTL-cached; a failed fetch degrades to bundled-only, never errors.
        await manager.async_refresh_remote()
        return self.json({"packs": manager.status()})


class PackInstallView(_PackViewMixin):
    """Install (or resume a partial install of) one pack."""

    url = "/api/fraimic/packs/{pack_id}/install"
    name = "api:fraimic:packs:install"

    async def post(self, request: web.Request, pack_id: str) -> web.Response:
        try:
            result = await self._packs(request).async_install(pack_id)
        except HomeAssistantError as err:
            return self.json_message(str(err), HTTPStatus.NOT_FOUND)
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
        frames = []
        for entry in loaded_fraimic_entries(hass):
            runtime = entry.runtime_data
            coordinator = runtime.coordinator
            info = coordinator.data or {}
            frames.append(
                {
                    "entry_id": entry.entry_id,
                    "title": entry.title,
                    "host": runtime.client.host,
                    "width": entry.data.get(CONF_WIDTH),
                    "height": entry.data.get(CONF_HEIGHT),
                    "rotation": entry.options.get(CONF_ROTATION, DEFAULT_ROTATION),
                    "online": coordinator.last_update_success,
                    "battery": (info.get("battery") or {}).get("percent"),
                    "charging": (info.get("battery") or {}).get("charging"),
                    "firmware": info.get("firmware_version"),
                }
            )
        return self.json({"frames": frames})
