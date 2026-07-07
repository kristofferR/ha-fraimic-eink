"""Pure data model for Fraimic scenes (no Home Assistant imports).

A scene is a named set of frame→image assignments: "flip the whole wall at
once". Scenes reference library image ids and config entry ids; they are pure
local state (they describe *this* installation's frames, so unlike images they
would never make sense to sync anywhere).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SCENE_SOURCE_USER = "user"
SCENE_SOURCE_PACK = "pack"


@dataclass
class Scene:
    """One named frame→image mapping."""

    scene_id: str
    name: str
    # config entry_id -> library image_id
    mappings: dict[str, str] = field(default_factory=dict)
    created_at: float = 0.0
    source: str = SCENE_SOURCE_USER
    source_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene_id": self.scene_id,
            "name": self.name,
            "mappings": self.mappings,
            "created_at": self.created_at,
            "source": self.source,
            "source_id": self.source_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Scene:
        raw_mappings = data.get("mappings") or {}
        if not isinstance(raw_mappings, dict):
            raw_mappings = {}
        mappings = {
            str(entry_id): str(image_id)
            for entry_id, image_id in raw_mappings.items()
            if image_id
        }
        return cls(
            scene_id=str(data["scene_id"]),
            name=str(data.get("name") or "Scene"),
            mappings=mappings,
            created_at=float(data.get("created_at") or 0.0),
            source=str(data.get("source") or SCENE_SOURCE_USER),
            source_id=str(data["source_id"]) if data.get("source_id") else None,
        )


def scenes_to_dict(scenes: dict[str, Scene]) -> dict[str, Any]:
    return {"scenes": {scene_id: scene.to_dict() for scene_id, scene in scenes.items()}}


def scenes_from_dict(data: dict[str, Any]) -> dict[str, Scene]:
    """Parse stored scenes, skipping entries too broken to load."""
    scenes: dict[str, Scene] = {}
    if not isinstance(data, dict):
        return scenes
    raw_scenes = data.get("scenes") or {}
    if not isinstance(raw_scenes, dict):
        return scenes
    for scene_id, raw in raw_scenes.items():
        try:
            raw = dict(raw)
            raw.setdefault("scene_id", scene_id)
            scenes[str(scene_id)] = Scene.from_dict(raw)
        except (TypeError, ValueError, KeyError):
            continue
    return scenes
