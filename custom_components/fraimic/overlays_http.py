"""Authenticated panel API for frame-owned overlays."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

from aiohttp import web
from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.exceptions import HomeAssistantError

from .helpers import loaded_fraimic_entries
from .http_helpers import require_loaded_entry
from .overlays import (
    ANCHORS,
    OVERLAY_TYPES,
    PLATES,
    SIZES,
    OverlayManager,
    get_overlay_manager,
    overlay_entities,
    overlay_preset,
)


def _manager(hass) -> OverlayManager:
    manager = get_overlay_manager(hass)
    if manager is None:
        raise web.HTTPServiceUnavailable(text="Fraimic overlays are not loaded")
    return manager


def _assert_admin(request: web.Request) -> None:
    if not getattr(request.get("hass_user"), "is_admin", False):
        raise web.HTTPForbidden(text="Admin required")


async def _body(request: web.Request) -> dict[str, Any]:
    try:
        data = await request.json()
    except ValueError:
        raise web.HTTPBadRequest(text="Body must be JSON") from None
    if not isinstance(data, dict):
        raise web.HTTPBadRequest(text="Body must be a JSON object")
    return data


def _thumbnail(slide) -> str | None:
    source = slide.source or {}
    if image_id := source.get("library_image"):
        return f"/api/fraimic/library/thumb/{image_id}"
    metadata = source.get("metadata") or {}
    return source.get("url") or metadata.get("thumbnail_url")


def _preview_items(entry) -> list[dict[str, Any]]:
    scheduler = entry.runtime_data.scheduler
    slides = scheduler.screens[:6]
    items = [
        {
            "id": slide.screen_id,
            "title": slide.name,
            "thumbnail_url": _thumbnail(slide),
            "darkest": index == 0 and len(slides) > 1,
            "lightest": index == len(slides) - 1 and len(slides) > 1,
        }
        for index, slide in enumerate(slides)
    ]
    if entry.runtime_data.last_preview is not None and not items:
        items.append(
            {
                "id": "current",
                "title": "Current picture",
                "thumbnail_url": f"/api/fraimic/player/artwork/{entry.entry_id}",
                "darkest": False,
                "lightest": False,
            }
        )
    return items


def _payload(hass, entry) -> dict[str, Any]:
    manager = _manager(hass)
    return {
        "frame": {
            "id": entry.entry_id,
            "name": entry.title,
            "width": entry.data.get("width"),
            "height": entry.data.get("height"),
            "rotation": entry.options.get("rotation", 0),
        },
        "overlays": manager.for_frame(entry.entry_id),
        "preview_thumbnails": _preview_items(entry),
        "entities": overlay_entities(hass),
        "types": list(OVERLAY_TYPES),
        "anchors": list(ANCHORS),
        "sizes": list(SIZES),
        "plates": list(PLATES),
        "presets": ["clock", "todo", "info", "side", "caption", "morning"],
    }


class FrameOverlaysView(HomeAssistantView):
    url = "/api/fraimic/overlays"
    name = "api:fraimic:overlays"

    async def get(self, request: web.Request) -> web.Response:
        hass = request.app[KEY_HASS]
        entry = require_loaded_entry(hass, request.query.get("entry_id"))
        return self.json(_payload(hass, entry))

    async def post(self, request: web.Request) -> web.Response:
        _assert_admin(request)
        hass = request.app[KEY_HASS]
        body = await _body(request)
        entry = require_loaded_entry(hass, body.get("entry_id"))
        action = body.get("action", "save")
        try:
            if action == "save":
                overlays = body.get("overlays")
                if not isinstance(overlays, list):
                    raise ValueError("overlays must be a list")
                await _manager(hass).async_replace(entry.entry_id, overlays)
            elif action == "preset":
                name = body.get("preset")
                if not isinstance(name, str):
                    raise ValueError("preset is required")
                overlays = overlay_preset(name, overlay_entities(hass))
                await _manager(hass).async_replace(entry.entry_id, overlays)
            elif action == "copy":
                target = require_loaded_entry(hass, body.get("target_entry_id"))
                await _manager(hass).async_copy(entry.entry_id, target.entry_id)
            else:
                raise ValueError("Unknown overlay action")
            if body.get("apply_now"):
                scheduler = entry.runtime_data.scheduler
                if scheduler.current_screen is None or scheduler.displayed_hash is None:
                    raise HomeAssistantError(
                        "Apply now is unavailable for the picture currently on the frame"
                    )
                await scheduler.async_select(scheduler.current_screen, hold=True)
        except (TypeError, ValueError, HomeAssistantError) as err:
            return self.json_message(str(err), HTTPStatus.CONFLICT)
        return self.json(_payload(hass, entry))


class OverlayFramesView(HomeAssistantView):
    url = "/api/fraimic/overlays/frames"
    name = "api:fraimic:overlays:frames"

    async def get(self, request: web.Request) -> web.Response:
        hass = request.app[KEY_HASS]
        return self.json(
            {
                "frames": [
                    {
                        "id": entry.entry_id,
                        "name": entry.title,
                        "overlay_count": len(_manager(hass).for_frame(entry.entry_id)),
                    }
                    for entry in loaded_fraimic_entries(hass)
                ]
            }
        )


def overlay_views() -> tuple[HomeAssistantView, ...]:
    return FrameOverlaysView(), OverlayFramesView()
