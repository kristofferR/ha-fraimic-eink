"""AI art settings, Create and fraimic.create_art against a real Home Assistant."""

from __future__ import annotations

import io
import shutil
from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, PropertyMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from PIL import Image
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fraimic.ai_art import GeneratedImage, month_start
from custom_components.fraimic.ai_manager import AI_ACCOUNT, AiArtManager, get_ai_manager
from custom_components.fraimic.const import (
    CONF_DELIVERY_MODE,
    DELIVERY_BACKEND,
    DOMAIN,
    LIBRARY_DIR,
)
from custom_components.fraimic.library import FraimicLibrary, get_library
from custom_components.fraimic.local_backend import (
    CONF_BACKEND_TOKEN,
    CONF_BACKEND_URL,
    CONF_VOICE_AI,
    CONF_VOICE_MODE,
    CONF_VOICE_STT,
    LocalBackend,
)

from .conftest import setup_entry

KEY = "sk-or-v1-private-fixture-key-abcd"
MODEL = "black-forest-labs/flux-3-image-klein"
CATALOG: list[dict[str, Any]] = [
    {
        "id": MODEL,
        "name": "FLUX 3 Image Klein",
        "aspect_ratios": ["3:4", "4:3", "9:16"],
        "resolutions": ["1K", "1.5K", "2K"],
    }
]


def _manager(hass: HomeAssistant) -> AiArtManager:
    manager = get_ai_manager(hass)
    assert manager is not None
    return manager


def _library(hass: HomeAssistant) -> FraimicLibrary:
    library = get_library(hass)
    assert library is not None
    return library


def _jpeg() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 48), "teal").save(buffer, "JPEG")
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def empty_library(hass: HomeAssistant) -> Generator[None]:
    """The harness config dir is shared across runs; start and end with no library."""
    path = hass.config.path(LIBRARY_DIR)
    shutil.rmtree(path, ignore_errors=True)
    yield
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def openrouter() -> Generator[AsyncMock]:
    generate = AsyncMock(
        return_value=GeneratedImage(_jpeg(), "image/jpeg", MODEL, 0.011)
    )
    with (
        patch(
            "custom_components.fraimic.ai_manager.openrouter_models",
            AsyncMock(return_value=CATALOG),
        ),
        patch("custom_components.fraimic.ai_manager.openrouter_generate", generate),
    ):
        yield generate


async def test_settings_api_never_returns_the_key(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, hass_client: Any
) -> None:
    client = await hass_client()
    reply = await client.post(
        "/api/fraimic/ai/settings", json={"provider": "openrouter", "openrouter_key": KEY}
    )
    assert reply.status == 200
    assert KEY not in await reply.text()
    body = await reply.json()
    assert body["configured"] is True
    assert body["openrouter"] == {
        "has_key": True,
        "key_hint": "abcd",
        "model": MODEL,
    }
    # An omitted key keeps the saved one.
    reply = await client.post("/api/fraimic/ai/settings", json={"style": "woodcut"})
    assert (await reply.json())["style"] == "woodcut"
    assert _manager(hass).settings.openrouter_key == KEY

    reply = await client.post("/api/fraimic/ai/settings", json={"local_url": "ftp://x"})
    assert reply.status == 400


async def test_create_saves_a_frame_shaped_creation_with_its_cost(
    hass: HomeAssistant,
    loaded_entry: MockConfigEntry,
    hass_client: Any,
    openrouter: AsyncMock,
) -> None:
    client = await hass_client()
    reply = await client.post(
        "/api/fraimic/ai/create",
        json={"entry_id": loaded_entry.entry_id, "request": "a fox reading"},
    )
    assert reply.status == 409
    assert "Set up AI art" in (await reply.json())["message"]

    await _manager(hass).async_update(
        {"provider": "openrouter", "openrouter_key": KEY}
    )
    reply = await client.post(
        "/api/fraimic/ai/create",
        json={"entry_id": loaded_entry.entry_id, "request": "a fox reading", "style": "woodcut"},
    )
    assert reply.status == 200
    result = await reply.json()
    assert result["cost"] == 0.011
    assert result["prompt"].startswith("Woodcut print of a fox reading.")

    assert openrouter.await_args is not None
    _session, key, model, prompt, width, height = openrouter.await_args.args
    assert (key, model["id"], width, height) == (KEY, MODEL, 1600, 1200)
    assert prompt == result["prompt"]
    image = _library(hass).get(result["image_id"])
    creation = image.creation
    assert creation is not None and creation.metadata is not None
    assert image.filename.endswith(".jpg")
    assert creation.account_id == AI_ACCOUNT
    assert creation.transcript == "a fox reading"
    assert creation.style == "Woodcut"
    assert creation.metadata["source"] == "panel"
    assert _manager(hass).month_usage() == {"count": 1, "cost": 0.011}

    # An edited prompt is sent exactly as written.
    reply = await client.post(
        "/api/fraimic/ai/create",
        json={"entry_id": loaded_entry.entry_id, "request": "a fox", "prompt": "Exactly this."},
    )
    assert (await reply.json())["prompt"] == "Exactly this."


async def test_create_can_use_another_ready_service_once(
    hass: HomeAssistant,
    loaded_entry: MockConfigEntry,
    hass_client: Any,
    openrouter: AsyncMock,
) -> None:
    await _manager(hass).async_update({"provider": "openrouter", "openrouter_key": KEY})
    client = await hass_client()
    body = {"entry_id": loaded_entry.entry_id, "request": "a fox", "provider": "local"}
    reply = await client.post("/api/fraimic/ai/create", json=body)
    assert reply.status == 409
    assert "not set up" in (await reply.json())["message"]

    reply = await client.post(
        "/api/fraimic/ai/settings",
        json={"local_url": "http://gpu.local:7860", "local_api": "sdwebui"},
    )
    assert (await reply.json())["ready"] == {"openrouter": True, "local": True, "ai_task": False}
    local = AsyncMock(return_value=GeneratedImage(_jpeg(), "image/jpeg", "sdxl"))
    with patch("custom_components.fraimic.ai_manager.local_generate", local):
        reply = await client.post("/api/fraimic/ai/create", json={**body, "model": "sdxl"})
    assert reply.status == 200
    assert (await reply.json())["provider"] == "local"
    assert local.await_args is not None
    _session, url, api, model, *_ = local.await_args.args
    assert (url, api, model) == ("http://gpu.local:7860", "sdwebui", "sdxl")
    openrouter.assert_not_awaited()
    assert _manager(hass).settings.provider == "openrouter"


async def test_create_art_service_saves_and_shows(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, openrouter: AsyncMock
) -> None:
    await _manager(hass).async_update(
        {"provider": "openrouter", "openrouter_key": KEY}
    )
    library = _library(hass)
    with patch.object(
        type(library), "async_send_to_entry", AsyncMock(return_value=True)
    ) as send:
        response = await hass.services.async_call(
            DOMAIN,
            "create_art",
            {"prompt": "a lighthouse at dusk", "style": "Photo"},
            blocking=True,
            return_response=True,
        )
    assert response is not None
    assert response["shown"] is True
    assert response["cost"] == 0.011
    assert str(response["prompt"]).startswith("Photograph of a lighthouse at dusk.")
    send.assert_awaited_once_with(response["image_id"], loaded_entry)
    creation = library.get(str(response["image_id"])).creation
    assert creation is not None and creation.metadata is not None
    assert creation.metadata["source"] == "automation"


@pytest.mark.usefixtures("frame_client")
async def test_voice_options_move_into_ai_settings(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=config_entry.version,
        unique_id=config_entry.unique_id,
        data=dict(config_entry.data),
        options={
            **config_entry.options,
            CONF_DELIVERY_MODE: DELIVERY_BACKEND,
            CONF_BACKEND_URL: "http://companion.example:8443",
            CONF_BACKEND_TOKEN: "private-fixture-bridge-token" * 2,
            CONF_VOICE_MODE: "art",
            CONF_VOICE_STT: "stt.whisper",
            CONF_VOICE_AI: "ai_task.images",
        },
    )
    with patch.object(LocalBackend, "request", new_callable=AsyncMock) as request:
        request.return_value = {"busy": False, "jobs": []}
        await setup_entry(hass, entry)
    manager = _manager(hass)
    voice = manager.voice(entry.entry_id)
    assert (voice.mode, voice.stt, voice.agent) == ("art", "stt.whisper", "homeassistant")
    assert (manager.settings.provider, manager.settings.ai_task_entity) == (
        "ai_task",
        "ai_task.images",
    )
    second = MockConfigEntry(domain=DOMAIN, options={
        CONF_VOICE_MODE: "art", CONF_VOICE_AI: "ai_task.other_images",
    })
    await manager.async_migrate_entry(second)
    reloaded = AiArtManager(hass)
    await reloaded.async_setup()
    with patch.object(reloaded, "_generate_ai_task", AsyncMock(
        return_value=GeneratedImage(_jpeg(), "image/jpeg", "test")
    )) as generate:
        for candidate in (entry, second):
            voice = reloaded.voice(candidate.entry_id)
            await reloaded.async_generate(
                "a fox", width=1600, height=1200, task_name="voice",
                ai_task_entity=voice.ai_task_entity,
            )
    assert [call.args[0] for call in generate.await_args_list] == [
        "ai_task.images", "ai_task.other_images",
    ]


async def test_usage_survives_discard_restart_and_month_rollover(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, openrouter: AsyncMock
) -> None:
    manager = _manager(hass)
    await manager.async_update({"provider": "openrouter", "openrouter_key": KEY})
    image, _ = await manager.async_create(loaded_entry, "a fox", source="panel")
    legacy = AiArtManager(hass)
    with patch.object(legacy._store, "async_load", AsyncMock(return_value=manager.settings.to_dict())):
        await legacy.async_setup()
    assert legacy.month_usage() == {"count": 1, "cost": 0.011}
    await _library(hass).async_delete_image(image.image_id)
    reloaded = AiArtManager(hass)
    await reloaded.async_setup()
    assert reloaded.month_usage() == {"count": 1, "cost": 0.011}
    await reloaded.async_update({"style": "woodcut"})
    await reloaded.async_create(loaded_entry, "a second fox", source="panel")
    assert reloaded.month_usage() == {"count": 2, "cost": 0.022}
    with patch("custom_components.fraimic.ai_manager.month_start", return_value=month_start() + 32 * 86400):
        assert reloaded.month_usage() == {"count": 0, "cost": 0.0}
        await reloaded.async_create(loaded_entry, "a new fox", source="panel")
        assert reloaded.month_usage() == {"count": 1, "cost": 0.011}


async def test_create_art_busy_rejects_before_generation(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, openrouter: AsyncMock
) -> None:
    await _manager(hass).async_update({"provider": "openrouter", "openrouter_key": KEY})
    scheduler = loaded_entry.runtime_data.scheduler
    with patch.object(type(scheduler), "busy", new_callable=PropertyMock, return_value=True):
        with pytest.raises(HomeAssistantError, match="playlist upload"):
            await hass.services.async_call(DOMAIN, "create_art", {"prompt": "a fox"}, blocking=True)
        openrouter.assert_not_awaited()
        # Saving without displaying does not need the upload guard.
        await hass.services.async_call(DOMAIN, "create_art", {"prompt": "a fox", "show": False}, blocking=True)
        openrouter.assert_awaited_once()


@pytest.mark.parametrize("failure", ["generation", "display"])
async def test_create_art_releases_upload_guard_on_failure(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, openrouter: AsyncMock, failure: str
) -> None:
    manager = _manager(hass)
    await manager.async_update({"provider": "openrouter", "openrouter_key": KEY})
    target, method = (manager, "async_create") if failure == "generation" else (_library(hass), "async_send_to_entry")
    scheduler = loaded_entry.runtime_data.scheduler
    with patch.object(target, method, AsyncMock(side_effect=HomeAssistantError("failed"))):
        with pytest.raises(HomeAssistantError, match="failed"):
            await hass.services.async_call(DOMAIN, "create_art", {"prompt": "a fox"}, blocking=True)
    assert scheduler._external_upload_count == 0
