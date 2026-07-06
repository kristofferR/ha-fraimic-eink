"""HTTP API for the panel's WYSIWYG screen editor.

Everything here manipulates the same config-subentry storage the device-page
subentry flow uses — one schema, three front doors (YAML service, subentry
flow, panel editor). The preview endpoint renders a candidate screen through
the real pipeline and returns the PNG without saving or uploading anything;
that live round-trip is what makes the editor WYSIWYG.
"""

from __future__ import annotations

import logging
from http import HTTPStatus
from types import MappingProxyType
from typing import Any

import voluptuous as vol
from aiohttp import web
from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN, PALETTE_NAMES
from .helpers import loaded_fraimic_entries
from .render.display import async_render_screen
from .render.layout import LAYOUT_SLOTS
from .render.schema import KIND_PICTURE, SCREEN_SCHEMA, screen_from_dict
from .screens import SUBENTRY_TYPE_SCREEN
from .screens_editor import PICTURE_FIELDS, SCREEN_FIELDS, WIDGET_FIELDS

_LOGGER = logging.getLogger(__name__)


def _resolve_entry(hass: HomeAssistant, entry_id: Any):
    for entry in loaded_fraimic_entries(hass):
        if entry.entry_id == entry_id:
            return entry
    raise web.HTTPBadRequest(text="Unknown or unloaded entry_id")


def _validate_screen(raw: Any) -> dict:
    if not isinstance(raw, dict):
        raise web.HTTPBadRequest(text="screen must be an object")
    try:
        return SCREEN_SCHEMA(dict(raw))
    except vol.Invalid as err:
        # Surface the voluptuous message: it's the editor's inline validation.
        raise web.HTTPBadRequest(text=f"Invalid screen: {err}") from err


class _ScreensViewBase(HomeAssistantView):
    async def _json_body(self, request: web.Request) -> dict[str, Any]:
        try:
            data = await request.json()
        except ValueError:
            raise web.HTTPBadRequest(text="Body must be JSON") from None
        if not isinstance(data, dict):
            raise web.HTTPBadRequest(text="Body must be a JSON object")
        return data


class ScreensListView(_ScreensViewBase):
    """List a frame's stored screens (raw subentry data, editable shape)."""

    url = "/api/fraimic/screens"
    name = "api:fraimic:screens:list"

    async def get(self, request: web.Request) -> web.Response:
        hass = request.app[KEY_HASS]
        entry = _resolve_entry(hass, request.query.get("entry_id"))
        screens = [
            {
                "screen_id": subentry.subentry_id,
                "title": subentry.title,
                "data": dict(subentry.data),
            }
            for subentry in entry.subentries.values()
            if subentry.subentry_type == SUBENTRY_TYPE_SCREEN
        ]
        return self.json({"screens": screens})


class ScreenDescriptorsView(_ScreensViewBase):
    """Form metadata: widget fields, layouts, palette. Static per version."""

    url = "/api/fraimic/screens/descriptors"
    name = "api:fraimic:screens:descriptors"

    async def get(self, request: web.Request) -> web.Response:
        return self.json(
            {
                "widgets": WIDGET_FIELDS,
                "layouts": {layout: list(slots) for layout, slots in LAYOUT_SLOTS.items()},
                "palette": sorted(PALETTE_NAMES),
                "screen_fields": SCREEN_FIELDS,
                "picture_fields": PICTURE_FIELDS,
            }
        )


class ScreenPreviewView(_ScreensViewBase):
    """Render a candidate screen to PNG — live data, nothing saved/uploaded."""

    url = "/api/fraimic/screens/preview"
    name = "api:fraimic:screens:preview"

    async def post(self, request: web.Request) -> web.Response:
        hass = request.app[KEY_HASS]
        body = await self._json_body(request)
        entry = _resolve_entry(hass, body.get("entry_id"))
        data = _validate_screen(body.get("screen"))
        screen = screen_from_dict(data)
        try:
            if screen.kind == KIND_PICTURE:
                png = await self._render_picture(hass, entry, screen)
            else:
                png, _mode = await async_render_screen(hass, entry, screen)
        except HomeAssistantError as err:
            return self.json_message(str(err), HTTPStatus.BAD_REQUEST)
        return web.Response(body=png, content_type="image/png")

    async def _render_picture(self, hass, entry, screen) -> bytes:
        """Picture screens preview through the photo pipeline's preview PNG."""
        from .const import ATTR_FIT, ATTR_MODE
        from .services import async_convert_for_entry
        from .source import async_get_source_bytes

        source = screen.source or {}
        raw = await async_get_source_bytes(
            hass, url=source.get("url"), entity_id=source.get("entity"), redact_url=True
        )
        overrides: dict = {}
        if fit := source.get("fit"):
            overrides[ATTR_FIT] = fit
        if mode := source.get("mode"):
            overrides[ATTR_MODE] = mode
        _bin, preview_png, _mode = await async_convert_for_entry(
            hass, entry, raw, overrides
        )
        if preview_png is None:  # pragma: no cover - preview defaults on
            raise HomeAssistantError("Renderer returned no preview")
        return preview_png


class ScreenSaveView(_ScreensViewBase):
    """Create or update a stored screen subentry from the editor."""

    url = "/api/fraimic/screens/save"
    name = "api:fraimic:screens:save"

    async def post(self, request: web.Request) -> web.Response:
        hass = request.app[KEY_HASS]
        body = await self._json_body(request)
        entry = _resolve_entry(hass, body.get("entry_id"))
        data = _validate_screen(body.get("screen"))
        title = data.get("name") or "Screen"

        if subentry_id := body.get("screen_id"):
            subentry = entry.subentries.get(subentry_id)
            if subentry is None or subentry.subentry_type != SUBENTRY_TYPE_SCREEN:
                return self.json_message("No such stored screen", HTTPStatus.NOT_FOUND)
            hass.config_entries.async_update_subentry(
                entry, subentry, data=MappingProxyType(data), title=title
            )
            return self.json({"screen_id": subentry_id, "saved": True})

        subentry = ConfigSubentry(
            data=MappingProxyType(data),
            subentry_type=SUBENTRY_TYPE_SCREEN,
            title=title,
            unique_id=None,
        )
        hass.config_entries.async_add_subentry(entry, subentry)
        return self.json({"screen_id": subentry.subentry_id, "saved": True})


class ScreenDeleteView(_ScreensViewBase):
    """Delete a stored screen."""

    url = "/api/fraimic/screens/{screen_id}"
    name = "api:fraimic:screens:delete"

    async def delete(self, request: web.Request, screen_id: str) -> web.Response:
        hass = request.app[KEY_HASS]
        entry = _resolve_entry(hass, request.query.get("entry_id"))
        subentry = entry.subentries.get(screen_id)
        if subentry is None or subentry.subentry_type != SUBENTRY_TYPE_SCREEN:
            return self.json_message("No such stored screen", HTTPStatus.NOT_FOUND)
        hass.config_entries.async_remove_subentry(entry, screen_id)
        return self.json({"deleted": screen_id})


class ScreenSendView(_ScreensViewBase):
    """Render a stored or candidate screen and push it to the frame now."""

    url = "/api/fraimic/screens/send"
    name = "api:fraimic:screens:send"

    async def post(self, request: web.Request) -> web.Response:
        from .render.display import async_show_screen
        from .screens import screen_by_key

        hass = request.app[KEY_HASS]
        body = await self._json_body(request)
        entry = _resolve_entry(hass, body.get("entry_id"))
        if screen_id := body.get("screen_id"):
            screen = screen_by_key(entry, screen_id)
            if screen is None:
                return self.json_message("No such stored screen", HTTPStatus.NOT_FOUND)
        else:
            screen = screen_from_dict(_validate_screen(body.get("screen")))
        try:
            result = await async_show_screen(hass, entry, screen, preview_only=False)
        except HomeAssistantError as err:
            return self.json_message(str(err), HTTPStatus.BAD_GATEWAY)
        return self.json({"sent": True, "result": dict(result or {})})


def screens_views() -> tuple[HomeAssistantView, ...]:
    """The editor's views, registered by http_api.async_register_views."""
    return (
        ScreensListView(),
        ScreenDescriptorsView(),
        ScreenPreviewView(),
        ScreenSaveView(),
        ScreenDeleteView(),
        ScreenSendView(),
    )
