"""Scene platform — one activatable HA scene entity per Fraimic scene.

Scenes are domain-level (they span frames), but HA entities must belong to a
config entry. The first Fraimic entry to load claims hosting; every entity is
grouped under a virtual "Fraimic Scenes" device so they don't clutter a single
frame's device page. If the hosting entry is reloaded, HA reloads its
platforms and the (still domain-level) scenes are re-hosted by whichever entry
sets up next.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.scene import Scene as SceneEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, MANUFACTURER
from .coordinator import FraimicConfigEntry
from .helpers import loaded_fraimic_entries
from .scene_model import Scene
from .scenes import SIGNAL_SCENES_UPDATED, SceneManager, get_scene_manager

_LOGGER = logging.getLogger(__name__)

DATA_SCENE_HOST = "scene_host"
DATA_SCENE_HOST_CANDIDATES = "scene_host_candidates"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FraimicConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Host the domain's scene entities on the first entry that loads."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    candidates: set[str] = domain_data.setdefault(DATA_SCENE_HOST_CANDIDATES, set())
    candidates.add(entry.entry_id)
    domain_data.setdefault(DATA_SCENE_HOST, entry.entry_id)

    @callback
    def _release_host() -> None:
        candidates.discard(entry.entry_id)
        if domain_data.get(DATA_SCENE_HOST) == entry.entry_id:
            loaded = {loaded.entry_id for loaded in loaded_fraimic_entries(hass)}
            next_host = next(
                (candidate for candidate in candidates if candidate in loaded), None
            )
            if next_host is None:
                domain_data.pop(DATA_SCENE_HOST, None)
            else:
                domain_data[DATA_SCENE_HOST] = next_host
                async_dispatcher_send(hass, SIGNAL_SCENES_UPDATED)

    entry.async_on_unload(_release_host)

    manager = get_scene_manager(hass)
    if manager is None:
        return

    entities: dict[str, FraimicSceneEntity] = {}

    @callback
    def _sync_entities() -> None:
        """Reconcile entities with the manager's current scene set."""
        if domain_data.get(DATA_SCENE_HOST) != entry.entry_id:
            return
        added = [
            FraimicSceneEntity(manager, scene_id)
            for scene_id in manager.scenes
            if scene_id not in entities
        ]
        added_ids = set()
        for entity in added:
            entities[entity.scene_id] = entity
            added_ids.add(entity.scene_id)
        if added:
            async_add_entities(added)

        registry = er.async_get(hass)
        for scene_id in list(entities):
            if scene_id in manager.scenes:
                if scene_id in added_ids:
                    continue
                entities[scene_id].async_write_ha_state()
                continue
            entity = entities.pop(scene_id)
            if entity.registry_entry is not None:
                # Removes the registry entry, which also removes the entity.
                registry.async_remove(entity.registry_entry.entity_id)
            else:
                hass.async_create_task(entity.async_remove(force_remove=True))

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_SCENES_UPDATED, _sync_entities)
    )
    _sync_entities()


class FraimicSceneEntity(SceneEntity):
    """Activating the entity pushes the scene's images to their frames."""

    _attr_device_info = DeviceInfo(
        identifiers={(DOMAIN, "fraimic_scenes")},
        manufacturer=MANUFACTURER,
        model="Scenes",
        name="Fraimic Scenes",
    )

    def __init__(self, manager: SceneManager, scene_id: str) -> None:
        self._manager = manager
        self.scene_id = scene_id
        self._attr_unique_id = f"fraimic_scene_{scene_id}"

    @property
    def _scene(self) -> Scene | None:
        return self._manager.scenes.get(self.scene_id)

    @property
    def name(self) -> str:
        scene = self._scene
        return scene.name if scene else "Removed scene"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        scene = self._scene
        if scene is None:
            return {}
        return {"frames": len(scene.mappings), "source": scene.source}

    async def async_activate(self, **kwargs: Any) -> None:
        results = await self._manager.async_send(self.scene_id)
        failed = [entry_id for entry_id, r in results.items() if not r["ok"]]
        if failed:
            _LOGGER.warning(
                "Scene %s: %d/%d frames failed: %s",
                self.name,
                len(failed),
                len(results),
                {k: results[k]["error"] for k in failed},
            )
