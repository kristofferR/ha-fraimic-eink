"""Scene manager: named frame→image mappings pushed as one action.

Scenes live in Home Assistant's ``.storage`` (they are pure local state).
Activation renders every mapped frame's buffer first — sequentially, the
dither is CPU-bound — then uploads to all frames concurrently, isolating
per-frame failures so one sleeping frame doesn't stop the rest of the wall.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .helpers import loaded_fraimic_entries
from .library import FraimicLibrary, async_upload_rendered
from .scene_model import (
    SCENE_SOURCE_USER,
    Scene,
    scenes_from_dict,
    scenes_to_dict,
)

_LOGGER = logging.getLogger(__name__)

DATA_SCENES = "scenes"
STORAGE_KEY = f"{DOMAIN}.scenes"
STORAGE_VERSION = 1

# Dispatcher signal fired on any scene CRUD, so the scene entities follow.
SIGNAL_SCENES_UPDATED = f"{DOMAIN}_scenes_updated"


class SceneNotFoundError(HomeAssistantError):
    """Raised when a scene id does not exist."""


@callback
def get_scene_manager(hass: HomeAssistant) -> SceneManager | None:
    """Return the domain-wide scene manager, if initialized."""
    return hass.data.get(DOMAIN, {}).get(DATA_SCENES)


class SceneManager:
    """Domain-level scene registry + activation."""

    def __init__(self, hass: HomeAssistant, library: FraimicLibrary) -> None:
        self.hass = hass
        self.library = library
        self.scenes: dict[str, Scene] = {}
        self._store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)

    async def async_setup(self) -> None:
        data = await self._store.async_load()
        self.scenes = scenes_from_dict(data or {})

    async def _async_save(self) -> None:
        await self._store.async_save(scenes_to_dict(self.scenes))
        async_dispatcher_send(self.hass, SIGNAL_SCENES_UPDATED)

    # ------------------------------------------------------------------ CRUD

    def get(self, scene_id: str) -> Scene:
        scene = self.scenes.get(scene_id)
        if scene is None:
            raise SceneNotFoundError(f"No Fraimic scene with id {scene_id}")
        return scene

    def find_by_name(self, name: str) -> Scene:
        """Case-insensitive scene lookup for the service/voice path."""
        wanted = name.strip().casefold()
        matches = [
            scene
            for scene in self.scenes.values()
            if scene.name.strip().casefold() == wanted
        ]
        if len(matches) == 1:
            return matches[0]
        if matches:
            raise HomeAssistantError(f"Multiple Fraimic scenes named {name!r}")
        raise HomeAssistantError(f"No Fraimic scene named {name!r}")

    def _validate_name(self, name: str, *, scene_id: str | None = None) -> str:
        cleaned = name.strip()
        if not cleaned:
            raise HomeAssistantError("Scene name cannot be empty")
        wanted = cleaned.casefold()
        for scene in self.scenes.values():
            if scene.scene_id != scene_id and scene.name.strip().casefold() == wanted:
                raise HomeAssistantError(
                    f"A Fraimic scene named {cleaned!r} already exists"
                )
        return cleaned

    def _validate_mappings(self, mappings: dict[str, str]) -> dict[str, str]:
        cleaned: dict[str, str] = {}
        for entry_id, image_id in mappings.items():
            if not image_id:
                continue
            # Fails loudly on a dangling library reference.
            self.library.get(image_id)
            cleaned[str(entry_id)] = str(image_id)
        if not cleaned:
            raise HomeAssistantError("A scene needs at least one frame→image mapping")
        return cleaned

    async def async_create(
        self,
        name: str,
        mappings: dict[str, str],
        *,
        source: str = SCENE_SOURCE_USER,
    ) -> Scene:
        name = self._validate_name(name)
        mappings = self._validate_mappings(mappings)
        scene = Scene(
            scene_id=uuid.uuid4().hex[:12],
            name=name,
            mappings=mappings,
            created_at=time.time(),
            source=source,
        )
        self.scenes[scene.scene_id] = scene
        await self._async_save()
        return scene

    async def async_update(
        self,
        scene_id: str,
        *,
        name: str | None = None,
        mappings: dict[str, str] | None = None,
    ) -> Scene:
        scene = self.get(scene_id)
        next_name = scene.name
        next_mappings = scene.mappings
        if name is not None:
            next_name = self._validate_name(name, scene_id=scene_id)
        if mappings is not None:
            next_mappings = self._validate_mappings(mappings)
        scene.name = next_name
        scene.mappings = next_mappings
        await self._async_save()
        return scene

    async def async_delete(self, scene_id: str) -> None:
        self.get(scene_id)
        del self.scenes[scene_id]
        await self._async_save()

    @callback
    def remove_image_references(self, image_id: str) -> list[str]:
        """Drop a deleted library image from every scene's mappings.

        Returns the ids of scenes that changed (caller saves). A scene left
        with no mappings is kept — the user can re-map it in the panel.
        """
        changed = []
        for scene in self.scenes.values():
            before = len(scene.mappings)
            scene.mappings = {
                entry_id: mapped
                for entry_id, mapped in scene.mappings.items()
                if mapped != image_id
            }
            if len(scene.mappings) != before:
                changed.append(scene.scene_id)
        return changed

    async def async_prune_image(self, image_id: str) -> None:
        if self.remove_image_references(image_id):
            await self._async_save()

    # ------------------------------------------------------------ activation

    async def async_send(self, scene_id: str) -> dict[str, dict[str, Any]]:
        """Activate a scene. Returns per-entry ``{"ok": bool, "error": ...}``."""
        scene = self.get(scene_id)
        scene_name = scene.name
        mappings = dict(scene.mappings)
        entries = {
            entry.entry_id: entry
            for entry in loaded_fraimic_entries(self.hass)
            if entry.entry_id in mappings
        }
        results: dict[str, dict[str, Any]] = {
            entry_id: {"ok": False, "error": "Frame is not loaded"}
            for entry_id in mappings
            if entry_id not in entries
        }
        if not entries:
            raise HomeAssistantError(
                f"None of the frames in scene {scene_name!r} are currently loaded"
            )

        schedulers = {}
        active_entries = {}
        for entry_id, entry in entries.items():
            try:
                schedulers[entry_id] = _begin_scene_upload(entry)
            except HomeAssistantError as err:
                results[entry_id] = {"ok": False, "error": str(err)}
            else:
                active_entries[entry_id] = entry

        try:
            # Phase 1: render sequentially (CPU-bound; cache makes repeats instant).
            prepared = {}
            media_titles = {}
            for entry_id, entry in active_entries.items():
                image_id = mappings[entry_id]
                try:
                    media_titles[entry_id] = self.library.get(image_id).filename
                    prepared[entry_id] = await self.library.async_render_for_entry(
                        image_id, entry
                    )
                except HomeAssistantError as err:
                    results[entry_id] = {"ok": False, "error": str(err)}
                    _finish_scene_upload(schedulers.pop(entry_id, None), uploaded=False)
                except asyncio.CancelledError:
                    raise
                except Exception as err:  # noqa: BLE001 - isolate per-frame failures
                    _LOGGER.warning(
                        "Scene %s failed to render for %s: %s",
                        scene_name,
                        getattr(entry, "title", entry_id),
                        err,
                    )
                    results[entry_id] = {"ok": False, "error": str(err)}
                    _finish_scene_upload(schedulers.pop(entry_id, None), uploaded=False)

            # Phase 2: upload concurrently; one wedged/sleeping frame can't block
            # or fail the others.
            async def _push(entry_id: str) -> None:
                uploaded = False
                try:
                    await async_upload_rendered(
                        active_entries[entry_id],
                        *prepared[entry_id],
                        media_title=media_titles[entry_id],
                    )
                    uploaded = True
                except HomeAssistantError as err:
                    results[entry_id] = {"ok": False, "error": str(err)}
                except asyncio.CancelledError:
                    raise
                except Exception as err:  # noqa: BLE001 - isolate per-frame failures
                    _LOGGER.warning(
                        "Scene %s failed to upload to %s: %s",
                        scene_name,
                        getattr(active_entries[entry_id], "title", entry_id),
                        err,
                    )
                    results[entry_id] = {"ok": False, "error": str(err)}
                else:
                    results[entry_id] = {"ok": True, "error": None}
                finally:
                    _finish_scene_upload(
                        schedulers.pop(entry_id, None), uploaded=uploaded
                    )

            await asyncio.gather(*(_push(entry_id) for entry_id in prepared))
        finally:
            for scheduler in list(schedulers.values()):
                _finish_scene_upload(scheduler, uploaded=False)
            schedulers.clear()

        failures = [r["error"] for r in results.values() if not r["ok"]]
        if failures and not any(r["ok"] for r in results.values()):
            raise HomeAssistantError(
                f"Scene {scene_name!r} failed on every frame: {failures[0]}"
            )
        return results


def _begin_scene_upload(entry) -> Any:
    """Block playlist work while a scene upload is being prepared."""
    scheduler = getattr(entry.runtime_data, "scheduler", None)
    if scheduler is None:
        return None
    if scheduler.busy or scheduler.external_upload_active:
        raise HomeAssistantError("A playlist upload is already in progress")
    scheduler.begin_external_upload()
    return scheduler


def _finish_scene_upload(scheduler: Any, *, uploaded: bool) -> None:
    """Release a scene-upload guard and hold the playlist after success."""
    if scheduler is not None:
        scheduler.finish_external_upload(uploaded=uploaded)
