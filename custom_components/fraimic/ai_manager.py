"""Shared AI art settings and picture generation for every frame.

One store holds the image service, styles, the optional prompt rewrite and
each frame's voice-button settings. Voice settings live here rather than in
config entry options because any options change reloads the frame.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .ai_art import (
    MAX_PROMPT,
    MAX_REQUEST,
    PROVIDER_AI_TASK,
    PROVIDER_LOCAL,
    PROVIDER_OPENROUTER,
    RECOMMENDED_MODELS,
    REWRITE_INSTRUCTIONS,
    AiArtError,
    AiSettings,
    GeneratedImage,
    VoiceSettings,
    apply_template,
    closest_aspect,
    local_detect,
    local_generate,
    month_start,
    openrouter_credits,
    openrouter_generate,
    openrouter_models,
    openrouter_pricing,
    pick_resolution,
    price_for,
    sniff_mime,
)
from .const import DOMAIN, MAX_SOURCE_BYTES, viewed_size
from .library import get_library
from .library_model import Creation, LibraryImage
from .local_backend import (
    CONF_VOICE_AGENT,
    CONF_VOICE_AI,
    CONF_VOICE_IMAGE,
    CONF_VOICE_LANGUAGE,
    CONF_VOICE_MODE,
    CONF_VOICE_STT,
)

_LOGGER = logging.getLogger(__name__)

DATA_AI_ART = "ai_art"
# Creation account for typed and automation pictures; voice uses its own.
AI_ACCOUNT = "fraimic:ai"
CATALOG_TTL = 12 * 3600


@callback
def get_ai_manager(hass: HomeAssistant) -> AiArtManager | None:
    """The domain-wide AI art manager, if Fraimic is set up."""
    manager: AiArtManager | None = hass.data.get(DOMAIN, {}).get(DATA_AI_ART)
    return manager


def _slug(text: str) -> str:
    words = re.findall(r"[\w]+", text.casefold())[:8]
    return "-".join(words)[:60]


class AiArtManager:
    """Settings store plus the one place pictures are generated."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store: Store[dict[str, Any]] = Store(hass, 1, f"{DOMAIN}.ai_art")
        self.settings = AiSettings()
        self._usage: dict[str, Any] = {}
        self._catalog: tuple[float, list[dict[str, Any]]] | None = None
        self._pricing: dict[str, tuple[float, list[dict[str, Any]]]] = {}
        # One picture at a time: a local GPU should not get parallel jobs.
        self._lock = asyncio.Lock()

    async def async_setup(self) -> None:
        data = await self._store.async_load() or {}
        self.settings = AiSettings.from_dict(data)
        if isinstance(data.get("usage"), dict):
            self._usage = data["usage"]
        else:
            # Seed usage once from pictures created before usage had its own record.
            self._usage = {"month": month_start(), **self._library_usage()}
            await self._async_save()

    async def _async_save(self) -> None:
        await self._store.async_save({**self.settings.to_dict(), "usage": self._usage})

    async def async_update(self, patch: dict[str, Any]) -> AiSettings:
        """Validate and save a partial update; raises ``vol.Invalid``."""
        self.settings = self.settings.updated(patch)
        await self._async_save()
        return self.settings

    def voice(self, entry_id: str) -> VoiceSettings:
        return self.settings.voice.get(entry_id, VoiceSettings())

    async def async_migrate_entry(self, entry: ConfigEntry) -> None:
        """Copy voice options from before these settings existed, once."""
        options = entry.options
        if entry.entry_id in self.settings.voice or CONF_VOICE_MODE not in options:
            return
        patch: dict[str, Any] = {
            "voice": {
                entry.entry_id: {
                    "mode": options.get(CONF_VOICE_MODE) or "fixed",
                    "image": options.get(CONF_VOICE_IMAGE) or "",
                    "stt": options.get(CONF_VOICE_STT) or "",
                    "language": options.get(CONF_VOICE_LANGUAGE) or "",
                    "agent": options.get(CONF_VOICE_AGENT) or "homeassistant",
                    "ai_task_entity": options.get(CONF_VOICE_AI) or "",
                }
            }
        }
        if (entity := options.get(CONF_VOICE_AI)) and not self.settings.provider:
            patch |= {"provider": PROVIDER_AI_TASK, "ai_task_entity": entity}
        try:
            await self.async_update(patch)
        except vol.Invalid as err:
            _LOGGER.warning("Could not move voice settings for %s: %s", entry.title, err)

    # ------------------------------------------------------------ OpenRouter

    async def async_catalog(self) -> list[dict[str, Any]]:
        """OpenRouter's image models, cached for half a day."""
        now = time.monotonic()
        if self._catalog is None or now - self._catalog[0] > CATALOG_TTL:
            models = await openrouter_models(async_get_clientsession(self.hass))
            self._catalog = (now, models)
        return self._catalog[1]

    async def _price(self, model: dict[str, Any], width: int, height: int) -> float | None:
        now = time.monotonic()
        cached = self._pricing.get(model["id"])
        if cached is None or now - cached[0] > CATALOG_TTL:
            try:
                pricing = await openrouter_pricing(
                    async_get_clientsession(self.hass), model["id"]
                )
            except AiArtError:
                return None
            cached = self._pricing[model["id"]] = (now, pricing)
        resolution = pick_resolution(max(width, height), model["resolutions"])
        return price_for(cached[1], resolution)

    async def async_models(
        self, width: int, height: int, extra: str | None = None
    ) -> list[dict[str, Any]]:
        """Image models for the picker, priced for this frame where possible.

        Prices need one request per model, so only the recommended models,
        the saved one and ``extra`` get them.
        """
        catalog = await self.async_catalog()
        priced = {*RECOMMENDED_MODELS, self.settings.openrouter_model, extra}
        rows = [model for model in catalog if model["id"] in priced]
        prices = await asyncio.gather(*(self._price(m, width, height) for m in rows))
        price_by_id = {model["id"]: price for model, price in zip(rows, prices)}
        order = list(RECOMMENDED_MODELS)
        return sorted(
            (
                {
                    "id": model["id"],
                    "name": model["name"],
                    "note": RECOMMENDED_MODELS.get(model["id"], ""),
                    "recommended": model["id"] in RECOMMENDED_MODELS,
                    "price": price_by_id.get(model["id"]),
                    "fits_frame": bool(
                        closest_aspect(width, height, model["aspect_ratios"])
                    ),
                }
                for model in catalog
            ),
            key=lambda row: (
                order.index(row["id"]) if row["recommended"] else len(order),
                row["name"].casefold(),
            ),
        )

    # ------------------------------------------------------------ checks

    async def async_check(self, patch: dict[str, Any]) -> dict[str, Any]:
        """Test a service before saving it; never raises for a bad answer."""
        settings = self.settings.updated(patch)
        session = async_get_clientsession(self.hass)
        try:
            if settings.provider == PROVIDER_OPENROUTER:
                if not settings.openrouter_key:
                    return {"ok": False, "error": "Paste an OpenRouter API key"}
                credits = await openrouter_credits(session, settings.openrouter_key)
                return {"ok": True, "credits": credits}
            if settings.provider == PROVIDER_LOCAL:
                if not settings.local_url:
                    return {"ok": False, "error": "Enter the server address"}
                api, models = await local_detect(session, settings.local_url)
                return {"ok": True, "api": api, "models": models}
        except AiArtError as err:
            return {"ok": False, "error": str(err)}
        return {"ok": False, "error": "Nothing to check for this service"}

    # ------------------------------------------------------------ generation

    def final_prompt(self, request: str, style: str | None = None) -> str:
        """The prompt a request becomes without a rewrite."""
        return apply_template(self.settings.style_for(style).template, request)

    async def async_generate(
        self,
        request: str,
        *,
        width: int,
        height: int,
        task_name: str,
        style: str | None = None,
        prompt: str | None = None,
        model: str | None = None,
        ai_task_entity: str | None = None,
    ) -> tuple[GeneratedImage, dict[str, Any]]:
        """Make one picture; ``prompt`` skips the rewrite and the template."""
        settings = self.settings
        if ai_task_entity and settings.provider == PROVIDER_AI_TASK:
            settings = settings.updated({"ai_task_entity": ai_task_entity})
        if not settings.configured:
            raise HomeAssistantError("Set up AI art in the Fraimic panel first")
        request = " ".join(request.split())
        if not request and not prompt:
            raise HomeAssistantError("Describe the picture first")
        if len(request) > MAX_REQUEST:
            raise HomeAssistantError(f"Keep the request under {MAX_REQUEST} characters")
        chosen = settings.style_for(style)
        rewritten = None
        if prompt:
            prompt = prompt.strip()
        else:
            text = request
            if settings.rewrite_entity:
                text = rewritten = await self._rewrite(request, task_name)
            prompt = apply_template(chosen.template, text)
        prompt = prompt[:MAX_PROMPT]
        started = time.monotonic()
        async with self._lock:
            try:
                image = await self._generate(settings, prompt, width, height, model, task_name)
            except AiArtError as err:
                raise HomeAssistantError(str(err)) from err
            start = month_start()
            usage = (
                self._usage if self._usage.get("month") == start
                else {"count": 0, "cost": 0.0}
            )
            self._usage = {
                "month": start,
                "count": usage["count"] + 1,
                "cost": usage["cost"] + (image.cost or 0.0),
            }
            await self._async_save()
        if len(image.data) > MAX_SOURCE_BYTES:
            raise HomeAssistantError("The generated picture is too large")
        return image, {
            "provider": settings.provider,
            "model": image.model,
            "prompt": prompt,
            "request": request,
            "rewritten": rewritten,
            "style": chosen.name,
            "cost": image.cost,
            "seconds": round(time.monotonic() - started, 1),
            "mime_type": image.mime_type,
        }

    async def _generate(
        self,
        settings: AiSettings,
        prompt: str,
        width: int,
        height: int,
        model: str | None,
        task_name: str,
    ) -> GeneratedImage:
        session = async_get_clientsession(self.hass)
        if settings.provider == PROVIDER_OPENROUTER:
            model_id = model or settings.openrouter_model
            try:
                catalog = await self.async_catalog()
            except AiArtError:
                catalog = []  # still generate; only the frame shape is lost
            entry = next(
                (row for row in catalog if row["id"] == model_id),
                {"id": model_id, "aspect_ratios": [], "resolutions": []},
            )
            return await openrouter_generate(
                session, settings.openrouter_key, entry, prompt, width, height
            )
        if settings.provider == PROVIDER_LOCAL:
            return await local_generate(
                session,
                settings.local_url,
                settings.local_api,
                model or settings.local_model,
                prompt,
                width,
                height,
                settings.local_steps,
            )
        return await self._generate_ai_task(settings.ai_task_entity, prompt, task_name)

    async def _generate_ai_task(
        self, entity_id: str, prompt: str, task_name: str
    ) -> GeneratedImage:
        from homeassistant.components import ai_task, media_source

        result = await ai_task.async_generate_image(
            self.hass, task_name=task_name, entity_id=entity_id, instructions=prompt
        )
        media_id = result.get("media_source_id") if isinstance(result, dict) else None
        if not isinstance(media_id, str):
            raise AiArtError("The AI Task entity did not return a picture")
        media = await media_source.async_resolve_media(self.hass, media_id, None)
        path = media.path
        if path is None:
            raise AiArtError("The AI Task entity did not keep a local picture")

        def read() -> bytes:
            with path.open("rb") as file:
                return file.read(MAX_SOURCE_BYTES + 1)

        data = await self.hass.async_add_executor_job(read)
        model = result.get("model") if isinstance(result, dict) else None
        return GeneratedImage(
            data, sniff_mime(data), model if isinstance(model, str) else entity_id
        )

    async def _rewrite(self, request: str, task_name: str) -> str:
        from homeassistant.components import ai_task

        result = await ai_task.async_generate_data(
            self.hass,
            task_name=f"{task_name}_prompt",
            entity_id=self.settings.rewrite_entity,
            instructions=REWRITE_INSTRUCTIONS.format(request=request),
        )
        text = " ".join(str(result.data or "").split()).strip('"')
        if not text:
            raise HomeAssistantError("The prompt rewrite returned nothing")
        return text[:MAX_REQUEST]

    async def async_create(
        self,
        entry: ConfigEntry,
        request: str,
        *,
        source: str,
        style: str | None = None,
        prompt: str | None = None,
        model: str | None = None,
    ) -> tuple[LibraryImage, dict[str, Any]]:
        """Make a picture shaped for ``entry`` and save it under Creations."""
        library = get_library(self.hass)
        if library is None:
            raise HomeAssistantError("The Fraimic library is not loaded")
        width, height = viewed_size(entry)
        image, metadata = await self.async_generate(
            request,
            width=width,
            height=height,
            task_name="fraimic_create",
            style=style,
            prompt=prompt,
            model=model,
        )
        creation = Creation(
            account_id=AI_ACCOUNT,
            upload_id=uuid.uuid4().hex,
            created_at=time.time(),
            transcript=metadata["request"] or metadata["prompt"],
            style=metadata["style"],
            orientation="portrait" if height > width else "landscape",
            metadata={**metadata, "frame": entry.entry_id, "source": source},
        )
        extension = {"image/jpeg": "jpg", "image/webp": "webp"}.get(image.mime_type, "png")
        name = _slug(metadata["request"] or metadata["prompt"]) or "creation"
        saved = await library.async_add_image(
            image.data, f"{name}.{extension}", creation=creation
        )
        return saved, metadata

    def month_usage(self) -> dict[str, Any]:
        """Generated pictures and their recorded cost this month."""
        if self._usage.get("month") != month_start():
            return {"count": 0, "cost": 0.0}
        return {"count": self._usage["count"], "cost": round(self._usage["cost"], 4)}

    def _library_usage(self) -> dict[str, Any]:
        """Usage migration for pictures already in the library."""
        library = get_library(self.hass)
        start = month_start()
        count, cost = 0, 0.0
        for image in library.images.values() if library else ():
            creation = image.creation
            if creation is None or (creation.created_at or 0) < start:
                continue
            metadata = creation.metadata or {}
            if "provider" not in metadata:
                continue
            count += 1
            if isinstance(metadata.get("cost"), int | float):
                cost += float(metadata["cost"])
        return {"count": count, "cost": round(cost, 4)}
