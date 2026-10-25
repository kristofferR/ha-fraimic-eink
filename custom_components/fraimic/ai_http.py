"""Panel API for AI art: settings, service checks, the model list and Create."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

import voluptuous as vol
from aiohttp import web
from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .ai_art import BUILTIN_BY_ID, AiArtError
from .ai_manager import AiArtManager, get_ai_manager
from .const import CONF_DELIVERY_MODE, DELIVERY_BACKEND, viewed_size
from .frame_name import frame_display_name
from .helpers import loaded_fraimic_entries
from .http_helpers import require_loaded_entry
from .library import get_library

# AI Task feature bits (homeassistant.components.ai_task.AITaskEntityFeature);
# read from state attributes so this module never imports the integration.
GENERATE_DATA = 1
GENERATE_IMAGE = 4


def _assert_admin(request: web.Request) -> None:
    if not getattr(request.get("hass_user"), "is_admin", False):
        raise web.HTTPForbidden(text="Admin access required")


def _manager(request: web.Request) -> AiArtManager:
    manager = get_ai_manager(request.app[KEY_HASS])
    if manager is None:
        raise web.HTTPServiceUnavailable(text="Fraimic is not loaded")
    return manager


async def _body(request: web.Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except ValueError:
        raise web.HTTPBadRequest(text="Body must be JSON") from None
    if not isinstance(body, dict):
        raise web.HTTPBadRequest(text="Body must be a JSON object")
    return body


def _choices(hass: HomeAssistant) -> dict[str, Any]:
    """Entities and library images the settings dialog can pick from."""
    from homeassistant.components import stt

    def tasks(feature: int) -> list[dict[str, str]]:
        return [
            {"id": state.entity_id, "name": state.name}
            for state in hass.states.async_all("ai_task")
            if int(state.attributes.get("supported_features") or 0) & feature
        ]

    speech = []
    for state in hass.states.async_all("stt"):
        entity = stt.async_get_speech_to_text_entity(hass, state.entity_id)
        speech.append(
            {
                "id": state.entity_id,
                "name": state.name,
                "languages": sorted(entity.supported_languages) if entity else [],
            }
        )
    agents = [{"id": "homeassistant", "name": "Home Assistant"}] + [
        {"id": state.entity_id, "name": state.name}
        for state in hass.states.async_all("conversation")
        if state.entity_id != "conversation.home_assistant"
    ]
    library = get_library(hass)
    images = sorted(
        library.images.values() if library else (),
        key=lambda image: image.uploaded_at,
        reverse=True,
    )
    return {
        "image_entities": tasks(GENERATE_IMAGE),
        "data_entities": tasks(GENERATE_DATA),
        "stt": speech,
        "agents": agents,
        "images": [
            {"id": image.image_id, "title": image.filename.rsplit(".", 1)[0]}
            for image in images[:500]
        ],
        "language": hass.config.language,
    }


def settings_payload(hass: HomeAssistant, manager: AiArtManager) -> dict[str, Any]:
    """Everything the AI art dialog shows. The API key never leaves HA."""
    settings = manager.settings
    key = settings.openrouter_key
    voice = []
    for entry in loaded_fraimic_entries(hass):
        voice.append(
            {
                "entry_id": entry.entry_id,
                "name": frame_display_name(hass, entry),
                "available": entry.options.get(CONF_DELIVERY_MODE) == DELIVERY_BACKEND,
                **manager.voice(entry.entry_id).to_dict(),
            }
        )
    return {
        "provider": settings.provider,
        "configured": settings.configured,
        "openrouter": {
            "has_key": bool(key),
            "key_hint": key[-4:] if len(key) > 8 else "",
            "model": settings.openrouter_model,
        },
        "local": {
            "url": settings.local_url,
            "api": settings.local_api,
            "model": settings.local_model,
            "steps": settings.local_steps,
        },
        "ai_task_entity": settings.ai_task_entity,
        "style": settings.style,
        "styles": [
            {
                **style.to_dict(),
                "builtin": style.id in BUILTIN_BY_ID,
                "modified": style.id in BUILTIN_BY_ID
                and style != BUILTIN_BY_ID[style.id],
            }
            for style in settings.styles
        ],
        "builtin_styles": {
            style_id: style.to_dict() for style_id, style in BUILTIN_BY_ID.items()
        },
        "rewrite_entity": settings.rewrite_entity,
        "voice": voice,
        "choices": _choices(hass),
        "usage": manager.month_usage(),
    }


class AiSettingsView(HomeAssistantView):
    url = "/api/fraimic/ai/settings"
    name = "api:fraimic:ai:settings"

    async def get(self, request: web.Request) -> web.Response:
        _assert_admin(request)
        hass = request.app[KEY_HASS]
        return self.json(settings_payload(hass, _manager(request)))

    async def post(self, request: web.Request) -> web.Response:
        """Save a partial update; an omitted ``openrouter_key`` keeps the saved one."""
        _assert_admin(request)
        hass = request.app[KEY_HASS]
        manager = _manager(request)
        try:
            await manager.async_update(await _body(request))
        except vol.Invalid as err:
            return self.json_message(f"Invalid settings: {err}", HTTPStatus.BAD_REQUEST)
        return self.json(settings_payload(hass, manager))


class AiCheckView(HomeAssistantView):
    url = "/api/fraimic/ai/check"
    name = "api:fraimic:ai:check"

    async def post(self, request: web.Request) -> web.Response:
        """Test an unsaved OpenRouter key or local server address."""
        _assert_admin(request)
        try:
            return self.json(await _manager(request).async_check(await _body(request)))
        except vol.Invalid as err:
            return self.json({"ok": False, "error": str(err.msg)})


class AiModelsView(HomeAssistantView):
    url = "/api/fraimic/ai/models"
    name = "api:fraimic:ai:models"

    async def get(self, request: web.Request) -> web.Response:
        _assert_admin(request)
        hass = request.app[KEY_HASS]
        entry = require_loaded_entry(hass, request.query.get("entry_id"))
        width, height = viewed_size(entry)
        try:
            models = await _manager(request).async_models(
                width, height, request.query.get("model")
            )
        except AiArtError as err:
            return self.json_message(str(err), HTTPStatus.BAD_GATEWAY)
        return self.json({"models": models})


class AiCreateView(HomeAssistantView):
    url = "/api/fraimic/ai/create"
    name = "api:fraimic:ai:create"

    async def post(self, request: web.Request) -> web.Response:
        """Make one picture for a frame and save it under Creations."""
        _assert_admin(request)
        hass = request.app[KEY_HASS]
        body = await _body(request)
        entry = require_loaded_entry(hass, body.get("entry_id"))

        def text(name: str) -> str | None:
            value = body.get(name)
            return value.strip() or None if isinstance(value, str) else None

        try:
            image, metadata = await _manager(request).async_create(
                entry,
                text("request") or "",
                source="panel",
                style=text("style"),
                prompt=text("prompt"),
                model=text("model"),
            )
        except HomeAssistantError as err:
            return self.json_message(str(err), HTTPStatus.CONFLICT)
        return self.json(
            {
                "image_id": image.image_id,
                "title": image.filename.rsplit(".", 1)[0],
                **metadata,
            }
        )


def ai_views() -> tuple[HomeAssistantView, ...]:
    return (AiSettingsView(), AiCheckView(), AiModelsView(), AiCreateView())
