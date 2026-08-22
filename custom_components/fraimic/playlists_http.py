"""Authenticated playlist API for the redesigned Fraimic panel."""

from __future__ import annotations

from collections import Counter
from http import HTTPStatus
from typing import Any

from aiohttp import web
from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
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
                "name": entry.title,
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
    if slide.data.get("provider"):
        return "live"
    return "picture"


def _slide_thumbnail(slide: PlaylistSlide) -> str | None:
    data = slide.data
    if image_id := data.get("library_image"):
        return f"/api/fraimic/library/thumb/{image_id}"
    return data.get("url")


def _slide_payload(
    slide: PlaylistSlide, *, on_frame: bool = False, editable: bool = False
) -> dict[str, Any]:
    data = slide.data
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
        "artist": None,
        "meta": meta,
        "thumbnail_url": _slide_thumbnail(slide),
        "library_image": data.get("library_image"),
        "fit": data.get("fit", "cover"),
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
        "thumbnails": [_slide_thumbnail(slide) for slide in playlist.slides[:4]],
        "playing": playing,
        "modified_at": playlist.modified_at,
    }
    if detail:
        payload["slides"] = [
            _slide_payload(
                slide,
                on_frame=slide.slide_id in on_frame_ids,
                editable=slide.slide_id in legacy_ids,
            )
            for slide in playlist.slides
        ]
    return payload


async def _refresh_assigned(
    hass: HomeAssistant,
    manager: PlaylistManager,
    playlist_id: str,
    *,
    reset: bool = False,
) -> None:
    for entry in loaded_fraimic_entries(hass):
        if manager.assignments.get(entry.entry_id) == playlist_id:
            await entry.runtime_data.scheduler.async_refresh_playlist(reset=reset)


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
                    _playlist_payload(hass, manager, playlist)
                    for playlist in ordered
                ],
                "selected_frame_id": request.query.get("entry_id"),
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
            _playlist_payload(hass, _manager(hass), playlist, detail=True),
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
        return self.json(_playlist_payload(hass, manager, playlist, detail=True))

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
        return self.json(_playlist_payload(hass, manager, playlist, detail=True))

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
                stopper = entry.runtime_data.stop_camera_loop
                if stopper is not None:
                    stopper()
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
        return self.json(_playlist_payload(hass, manager, playlist, detail=True))


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
        stopper = entry.runtime_data.stop_camera_loop
        if stopper is not None:
            stopper()
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
                    hass, manager, playlist, detail=True
                ),
            }
        )


def playlist_views() -> tuple[HomeAssistantView, ...]:
    return (
        PlaylistsView(),
        PlaylistView(),
        PlaylistControlView(),
        PlaylistSlidesView(),
    )
