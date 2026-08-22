"""Authenticated playlist API for the redesigned Fraimic panel."""

from __future__ import annotations

from collections import Counter
from http import HTTPStatus
from typing import Any
from urllib.parse import quote, urlencode

from aiohttp import web
from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import (
    CONF_PLAYLIST_PREFETCH,
    DEFAULT_PLAYLIST_PREFETCH,
    DOMAIN,
    MODE_AUTO,
)
from .frame_name import frame_display_name
from .helpers import loaded_fraimic_entries
from .http_helpers import require_loaded_entry
from .library import get_library
from .playlists import (
    DATA_PLAYLISTS,
    Playlist,
    PlaylistChangedError,
    PlaylistManager,
    PlaylistNotFoundError,
    PlaylistSlide,
)
from .render.schema import KIND_DASHBOARD
from .screens import SUBENTRY_TYPE_SCREEN


class PlaylistRequestError(ValueError):
    """Raised when a playlist request body has an invalid shape."""


def _manager(hass: HomeAssistant) -> PlaylistManager:
    manager = hass.data.get(DOMAIN, {}).get(DATA_PLAYLISTS)
    if manager is None:
        raise web.HTTPServiceUnavailable(text="Fraimic playlists are not loaded")
    return manager


def _assert_admin(request: web.Request) -> None:
    if not getattr(request.get("hass_user"), "is_admin", False):
        raise web.HTTPForbidden(text="Admin required")


async def _stop_camera_loop(entry: Any) -> None:
    """Stop camera playback and restore the persisted playlist state."""
    stopper = entry.runtime_data.stop_camera_loop
    if stopper is not None:
        stopper()
    scheduler = entry.runtime_data.scheduler
    if scheduler.stored_enabled and not scheduler.enabled:
        await scheduler.async_set_enabled(
            True,
            rotate=False,
            clear_hold=False,
            persist=False,
        )


def _playing_frames(
    hass: HomeAssistant, manager: PlaylistManager, playlist_id: str
) -> list[dict[str, Any]]:
    playing = []
    for entry in loaded_fraimic_entries(hass):
        scheduler = entry.runtime_data.scheduler
        if (
            manager.assignments.get(entry.entry_id) != playlist_id
            or not scheduler.enabled
            or not scheduler.screens
        ):
            continue
        playing.append(
            {
                "id": entry.entry_id,
                "name": frame_display_name(hass, entry),
                "since": (
                    scheduler.last_rotation.isoformat()
                    if scheduler.last_rotation is not None
                    else None
                ),
            }
        )
    return playing


def _slide_kind(slide: PlaylistSlide) -> str:
    if slide.data.get("kind") == KIND_DASHBOARD:
        return "blank"
    if slide.data.get("provider") and not slide.data.get("provider_item"):
        return "live"
    return "picture"


def _original_slide_thumbnail(slide: PlaylistSlide) -> str | None:
    data = slide.data
    if image_id := data.get("library_image"):
        return f"/api/fraimic/library/thumb/{image_id}"
    metadata = data.get("metadata") or {}
    return data.get("url") or metadata.get("thumbnail_url")


def _slide_thumbnail(
    slide: PlaylistSlide,
    *,
    playlist_id: str | None = None,
    entry_id: str | None = None,
    version: float | None = None,
) -> str | None:
    data = slide.data
    fixed_picture = bool(
        data.get("library_image")
        or (data.get("provider") and data.get("provider_item"))
    )
    if fixed_picture and playlist_id and entry_id:
        query = urlencode(
            {"entry_id": entry_id, "v": f"{version or 0:.6f}"}
        )
        return (
            f"/api/fraimic/playlists/{quote(playlist_id, safe='')}"
            f"/slides/{quote(slide.slide_id, safe='')}/thumbnail?{query}"
        )
    return _original_slide_thumbnail(slide)


def _slide_payload(
    slide: PlaylistSlide,
    *,
    on_frame: bool = False,
    editable: bool = False,
    thumbnail_url: str | None = None,
) -> dict[str, Any]:
    data = slide.data
    metadata = data.get("metadata") or {}
    kind = _slide_kind(slide)
    if kind == "live":
        meta = "Fresh artwork each rotation, nothing stored"
    elif kind == "blank":
        meta = "Blank background"
    elif entity := data.get("entity"):
        meta = str(entity)
    else:
        meta = "Picture"
    overlays = "custom" if kind == "blank" else slide.overlays
    return {
        "id": slide.slide_id,
        "kind": kind,
        "title": data.get("name") or "Untitled",
        "artist": metadata.get("artist"),
        "meta": meta,
        "thumbnail_url": thumbnail_url or _original_slide_thumbnail(slide),
        "library_image": data.get("library_image"),
        "fit": data.get("fit", "cover"),
        "mode": data.get("mode", MODE_AUTO),
        "tone": slide.tone,
        "overlays": overlays,
        "live": kind == "live",
        "shuffle_album": data.get("provider") == "shuffle",
        "blank": kind == "blank",
        "on_frame": on_frame,
        "editable": editable,
    }


def _composition(playlist: Playlist) -> dict[str, int]:
    counts = Counter(_slide_kind(slide) for slide in playlist.slides)
    return {
        "pictures": counts["picture"],
        "live_sources": counts["live"],
        "blank": counts["blank"],
    }


def _playlist_payload(
    hass: HomeAssistant,
    manager: PlaylistManager,
    playlist: Playlist,
    *,
    detail: bool = False,
    entry_id: str | None = None,
) -> dict[str, Any]:
    playing = _playing_frames(hass, manager, playlist.playlist_id)
    on_frame_ids = {
        entry.runtime_data.scheduler.current_id
        for entry in loaded_fraimic_entries(hass)
        if manager.assignments.get(entry.entry_id) == playlist.playlist_id
    }
    legacy_ids = {
        subentry.subentry_id
        for entry in loaded_fraimic_entries(hass)
        for subentry in entry.subentries.values()
        if subentry.subentry_type == SUBENTRY_TYPE_SCREEN
    }
    payload: dict[str, Any] = {
        "id": playlist.playlist_id,
        "name": playlist.name,
        "slide_count": len(playlist.slides),
        "composition": _composition(playlist),
        "interval": playlist.interval,
        "shuffle": playlist.shuffle,
        "thumbnails": [
            _slide_thumbnail(
                slide,
                playlist_id=playlist.playlist_id,
                entry_id=entry_id,
                version=playlist.modified_at,
            )
            for slide in playlist.slides[:4]
        ],
        "playing": playing,
        "modified_at": playlist.modified_at,
    }
    if detail:
        payload["slides"] = [
            _slide_payload(
                slide,
                on_frame=slide.slide_id in on_frame_ids,
                editable=slide.slide_id in legacy_ids,
                thumbnail_url=_slide_thumbnail(
                    slide,
                    playlist_id=playlist.playlist_id,
                    entry_id=entry_id,
                    version=playlist.modified_at,
                ),
            )
            for slide in playlist.slides
        ]
    return payload


class PlaylistThumbnailView(HomeAssistantView):
    """Serve a small cached e-ink preview for a fixed playlist slide."""

    url = "/api/fraimic/playlists/{playlist_id}/slides/{slide_id}/thumbnail"
    name = "api:fraimic:playlist:slide:thumbnail"

    async def get(
        self, request: web.Request, playlist_id: str, slide_id: str
    ) -> web.Response:
        hass = request.app[KEY_HASS]
        entry = require_loaded_entry(hass, request.query.get("entry_id"))
        manager = _manager(hass)
        screen = manager.render_slide(playlist_id, slide_id)
        if screen is None:
            raise web.HTTPNotFound(text="Playlist slide not found")
        from .render.display import cached_prepared_thumbnail

        try:
            enabled = int(
                entry.options.get(
                    CONF_PLAYLIST_PREFETCH, DEFAULT_PLAYLIST_PREFETCH
                )
            ) > 0
        except (TypeError, ValueError):
            enabled = DEFAULT_PLAYLIST_PREFETCH > 0
        preview = cached_prepared_thumbnail(hass, entry, screen) if enabled else None
        if preview is not None:
            return web.Response(
                body=preview,
                content_type="image/png",
                headers={"Cache-Control": "private, max-age=60"},
            )
        playlist = manager.require(playlist_id)
        slide = next(
            (item for item in playlist.slides if item.slide_id == slide_id), None
        )
        if slide is not None and (image_id := slide.data.get("library_image")):
            library = get_library(hass)
            if library is not None:
                try:
                    thumbnail = await library.async_get_thumbnail(image_id)
                except HomeAssistantError:
                    pass
                else:
                    return web.Response(
                        body=thumbnail,
                        content_type="image/jpeg",
                        headers={"Cache-Control": "private, max-age=60"},
                    )
        if slide is not None and (
            provider := slide.data.get("provider")
        ) and (item_id := slide.data.get("provider_item")):
            from .gallery_http import _async_gallery_image

            try:
                thumbnail, content_type = await _async_gallery_image(
                    hass, entry, provider, item_id, thumbnail=True
                )
            except (HomeAssistantError, OSError):
                pass
            else:
                return web.Response(
                    body=thumbnail,
                    content_type=content_type,
                    headers={"Cache-Control": "private, max-age=60"},
                )
        fallback = _original_slide_thumbnail(slide) if slide is not None else None
        if fallback:
            raise web.HTTPFound(
                location=fallback, headers={"Cache-Control": "no-store"}
            )
        raise web.HTTPNotFound(text="No thumbnail is available")


async def _refresh_assigned(
    hass: HomeAssistant,
    manager: PlaylistManager,
    playlist_id: str,
    *,
    reset: bool = False,
) -> None:
    for entry in loaded_fraimic_entries(hass):
        assigned = manager.assignments.get(entry.entry_id) == playlist_id
        await entry.runtime_data.scheduler.async_refresh_playlist(
            reset=reset and assigned
        )


class _PlaylistView(HomeAssistantView):
    async def _body(self, request: web.Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except ValueError:
            raise web.HTTPBadRequest(text="Body must be JSON") from None
        if not isinstance(body, dict):
            raise web.HTTPBadRequest(text="Body must be a JSON object")
        return body

    def _error(self, err: Exception) -> web.Response:
        if isinstance(err, PlaylistNotFoundError):
            return self.json_message("Playlist not found", HTTPStatus.NOT_FOUND)
        return self.json_message(str(err), HTTPStatus.CONFLICT)


class PlaylistsView(_PlaylistView):
    """List and create playlists."""

    url = "/api/fraimic/playlists"
    name = "api:fraimic:playlists"

    async def get(self, request: web.Request) -> web.Response:
        hass = request.app[KEY_HASS]
        manager = _manager(hass)
        entry_id = request.query.get("entry_id")
        ordered = sorted(
            manager.playlists,
            key=lambda playlist: (
                not bool(_playing_frames(hass, manager, playlist.playlist_id)),
                -playlist.modified_at,
            ),
        )
        return self.json(
            {
                "playlists": [
                    _playlist_payload(
                        hass, manager, playlist, entry_id=entry_id
                    )
                    for playlist in ordered
                ],
                "selected_frame_id": entry_id,
            }
        )

    async def post(self, request: web.Request) -> web.Response:
        _assert_admin(request)
        hass = request.app[KEY_HASS]
        body = await self._body(request)
        try:
            playlist = await _manager(hass).async_create(str(body.get("name", "")))
        except ValueError as err:
            return self.json_message(str(err), HTTPStatus.BAD_REQUEST)
        return self.json(
            _playlist_payload(
                hass,
                _manager(hass),
                playlist,
                detail=True,
                entry_id=body.get("entry_id"),
            ),
            status_code=HTTPStatus.CREATED,
        )


class PlaylistView(_PlaylistView):
    """Read, rename, duplicate, or delete one playlist."""

    url = "/api/fraimic/playlists/{playlist_id}"
    name = "api:fraimic:playlist"

    async def get(self, request: web.Request, playlist_id: str) -> web.Response:
        hass = request.app[KEY_HASS]
        manager = _manager(hass)
        try:
            playlist = manager.require(playlist_id)
        except PlaylistNotFoundError as err:
            return self._error(err)
        return self.json(
            _playlist_payload(
                hass,
                manager,
                playlist,
                detail=True,
                entry_id=request.query.get("entry_id"),
            )
        )

    async def post(self, request: web.Request, playlist_id: str) -> web.Response:
        _assert_admin(request)
        hass = request.app[KEY_HASS]
        manager = _manager(hass)
        body = await self._body(request)
        action = body.get("action")
        try:
            if action == "rename":
                playlist = await manager.async_rename(
                    playlist_id, str(body.get("name", ""))
                )
            elif action == "duplicate":
                playlist = await manager.async_duplicate(playlist_id)
            else:
                return self.json_message("Unknown action", HTTPStatus.BAD_REQUEST)
        except (PlaylistNotFoundError, ValueError) as err:
            return self._error(err)
        return self.json(
            _playlist_payload(
                hass,
                manager,
                playlist,
                detail=True,
                entry_id=body.get("entry_id"),
            )
        )

    async def delete(self, request: web.Request, playlist_id: str) -> web.Response:
        _assert_admin(request)
        hass = request.app[KEY_HASS]
        manager = _manager(hass)
        try:
            affected = await manager.async_delete(playlist_id)
        except PlaylistNotFoundError as err:
            return self._error(err)
        for entry in loaded_fraimic_entries(hass):
            if entry.entry_id in affected:
                await entry.runtime_data.scheduler.async_set_enabled(False)
                await entry.runtime_data.scheduler.async_refresh_playlist(reset=True)
            else:
                await entry.runtime_data.scheduler.async_refresh_playlist()
        return self.json({"deleted": playlist_id})


class PlaylistControlView(_PlaylistView):
    """Assign playback or change playlist-wide timing and shuffle."""

    url = "/api/fraimic/playlists/{playlist_id}/control"
    name = "api:fraimic:playlist:control"

    async def post(self, request: web.Request, playlist_id: str) -> web.Response:
        _assert_admin(request)
        hass = request.app[KEY_HASS]
        manager = _manager(hass)
        body = await self._body(request)
        action = body.get("action")
        try:
            playlist = manager.require(playlist_id)
            if action == "play":
                entry = require_loaded_entry(hass, body.get("entry_id"))
                await _stop_camera_loop(entry)
                await manager.async_assign(entry.entry_id, playlist_id)
                await entry.runtime_data.scheduler.async_refresh_playlist(
                    reset=True, start=True
                )
            elif action == "stop":
                entry = require_loaded_entry(hass, body.get("entry_id"))
                if manager.assignments.get(entry.entry_id) == playlist_id:
                    await entry.runtime_data.scheduler.async_set_enabled(False)
            elif action == "shuffle":
                if not isinstance(body.get("shuffle"), bool):
                    return self.json_message(
                        "shuffle must be a boolean", HTTPStatus.BAD_REQUEST
                    )
                playlist = await manager.async_set_options(
                    playlist_id, shuffle=body["shuffle"]
                )
                await _refresh_assigned(hass, manager, playlist_id)
            elif action == "interval":
                interval = body.get("interval")
                if not isinstance(interval, int) or isinstance(interval, bool):
                    return self.json_message(
                        "interval must be seconds", HTTPStatus.BAD_REQUEST
                    )
                playlist = await manager.async_set_options(
                    playlist_id, interval=interval
                )
                await _refresh_assigned(hass, manager, playlist_id)
            else:
                return self.json_message("Unknown action", HTTPStatus.BAD_REQUEST)
        except (PlaylistNotFoundError, ValueError, HomeAssistantError) as err:
            return self._error(err)
        return self.json(
            _playlist_payload(
                hass,
                manager,
                playlist,
                detail=True,
                entry_id=body.get("entry_id"),
            )
        )


class PlaylistSlidesView(_PlaylistView):
    """Reorder, remove, restore, configure, or play one playlist slide."""

    url = "/api/fraimic/playlists/{playlist_id}/slides"
    name = "api:fraimic:playlist:slides"

    async def _reorder(
        self,
        hass: HomeAssistant,
        manager: PlaylistManager,
        playlist_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        ordered_ids = body.get("ordered_ids")
        if not isinstance(ordered_ids, list) or not all(
            isinstance(slide_id, str) for slide_id in ordered_ids
        ):
            raise PlaylistRequestError("ordered_ids must be slide ids")
        await manager.async_reorder(playlist_id, ordered_ids)
        await _refresh_assigned(hass, manager, playlist_id)
        return {}

    async def _add(
        self,
        hass: HomeAssistant,
        manager: PlaylistManager,
        playlist_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        slides = body.get("slides")
        if not isinstance(slides, list):
            raise PlaylistRequestError("slides must be a list")
        library = get_library(hass)
        for slide in slides:
            if not isinstance(slide, dict):
                raise PlaylistRequestError("slides must contain objects")
            if (image_id := slide.get("library_image")) and (
                library is None or image_id not in library.images
            ):
                raise web.HTTPNotFound(text="Library picture not found")
        await manager.async_add_slides(playlist_id, slides)
        await _refresh_assigned(hass, manager, playlist_id)
        return {}

    async def _remove(
        self,
        hass: HomeAssistant,
        manager: PlaylistManager,
        playlist_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        slide_id = body.get("slide_id")
        if not isinstance(slide_id, str):
            raise PlaylistRequestError("slide_id is required")
        token = await manager.async_remove_slide(playlist_id, slide_id)
        await _refresh_assigned(hass, manager, playlist_id)
        return {"undo_token": token}

    async def _undo(
        self,
        hass: HomeAssistant,
        manager: PlaylistManager,
        playlist_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        token = body.get("undo_token")
        if not isinstance(token, str):
            raise PlaylistRequestError("undo_token is required")
        await manager.async_undo_remove(playlist_id, token)
        await _refresh_assigned(hass, manager, playlist_id)
        return {}

    async def _settings(
        self,
        hass: HomeAssistant,
        manager: PlaylistManager,
        playlist_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        slide_id = body.get("slide_id")
        if not isinstance(slide_id, str):
            raise PlaylistRequestError("slide_id is required")
        await manager.async_update_slide(
            playlist_id,
            slide_id,
            fit=body.get("fit"),
            mode=body.get("mode"),
            tone=body.get("tone"),
            overlays=body.get("overlays"),
        )
        await _refresh_assigned(hass, manager, playlist_id)
        return {}

    async def _play(
        self,
        hass: HomeAssistant,
        manager: PlaylistManager,
        playlist_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        slide_id = body.get("slide_id")
        if not isinstance(slide_id, str):
            raise PlaylistRequestError("slide_id is required")
        slide = manager.render_slide(playlist_id, slide_id)
        if slide is None:
            raise PlaylistChangedError("That slide is no longer available")
        entry = require_loaded_entry(hass, body.get("entry_id"))
        scheduler = entry.runtime_data.scheduler
        scheduler.raise_if_upload_active()
        await _stop_camera_loop(entry)
        if body["action"] == "show_now":
            # Queue first so an asleep-frame retry survives an HA restart,
            # then immediately consume it through the normal manual path.
            await scheduler.async_add_to_queue(slide, play_next=True)
            await scheduler.async_next()
        else:
            if not scheduler.screens:
                raise PlaylistRequestError(
                    "Choose a playlist on this frame before playing next"
                )
            await scheduler.async_add_to_queue(slide, play_next=True)
        return {}

    async def post(self, request: web.Request, playlist_id: str) -> web.Response:
        _assert_admin(request)
        hass = request.app[KEY_HASS]
        manager = _manager(hass)
        body = await self._body(request)
        action = body.get("action")
        handlers = {
            "reorder": self._reorder,
            "add": self._add,
            "remove": self._remove,
            "undo": self._undo,
            "settings": self._settings,
            "show_now": self._play,
            "play_next": self._play,
        }
        handler = handlers.get(action)
        if handler is None:
            return self.json_message("Unknown action", HTTPStatus.BAD_REQUEST)
        try:
            result = await handler(hass, manager, playlist_id, body)
            playlist = manager.require(playlist_id)
        except PlaylistRequestError as err:
            return self.json_message(str(err), HTTPStatus.BAD_REQUEST)
        except (
            PlaylistNotFoundError,
            PlaylistChangedError,
            ValueError,
            HomeAssistantError,
        ) as err:
            return self._error(err)
        return self.json(
            {
                **result,
                "playlist": _playlist_payload(
                    hass,
                    manager,
                    playlist,
                    detail=True,
                    entry_id=body.get("entry_id"),
                ),
            }
        )


def playlist_views() -> tuple[HomeAssistantView, ...]:
    return (
        PlaylistsView(),
        PlaylistView(),
        PlaylistControlView(),
        PlaylistSlidesView(),
        PlaylistThumbnailView(),
    )
