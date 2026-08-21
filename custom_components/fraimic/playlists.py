"""Domain-wide named playlists and migration from legacy frame slides."""

from __future__ import annotations

import asyncio
import copy
import logging
import math
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field, replace
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    DEFAULT_SCREEN_INTERVAL,
    DOMAIN,
    MIN_SCREEN_INTERVAL,
    PLAYLIST_TONE_VALUES,
)
from .render.schema import KIND_PICTURE, SCREEN_SCHEMA, ScreenConfig, screen_from_dict
from .screens import SUBENTRY_TYPE_SCREEN

DATA_PLAYLISTS = "playlists"
STORE_KEY = f"{DOMAIN}_playlists"
STORE_VERSION = 1

_LOGGER = logging.getLogger(__name__)


class PlaylistNotFoundError(KeyError):
    """Raised when a playlist changed or was removed."""


class PlaylistChangedError(ValueError):
    """Raised when an optimistic playlist mutation is stale."""


def _validated_slide_data(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate raw or already-normalized legacy data into one stored shape."""
    candidate = copy.deepcopy(raw)
    widgets = candidate.get("widgets")
    if isinstance(widgets, list):
        candidate["widgets"] = [
            {
                "type": widget.get("type"),
                "slot": widget.get("slot"),
                **(
                    widget.get("options", {})
                    if isinstance(widget.get("options"), dict)
                    else {}
                ),
            }
            if isinstance(widget, dict) and "options" in widget
            else widget
            for widget in widgets
        ]
    return SCREEN_SCHEMA(candidate)


@dataclass
class PlaylistSlide:
    """One ordered slide with playlist-scoped presentation settings."""

    slide_id: str
    data: dict[str, Any]
    tone: str = "balanced"
    overlays: str = "inherit"

    @classmethod
    def from_dict(cls, raw: Any) -> PlaylistSlide | None:
        if not isinstance(raw, dict):
            _LOGGER.warning(
                "Ignoring invalid stored playlist slide: expected a mapping, got %s",
                type(raw).__name__,
            )
            return None
        slide_id = raw.get("id")
        data = raw.get("data")
        if not isinstance(slide_id, str) or not isinstance(data, dict):
            _LOGGER.warning(
                "Ignoring invalid stored playlist slide %s: missing id or data",
                slide_id if isinstance(slide_id, str) else "<unknown>",
            )
            return None
        try:
            validated = _validated_slide_data(data)
        except vol.Invalid as err:
            _LOGGER.warning(
                "Ignoring invalid stored playlist slide %s: %s", slide_id, err
            )
            return None
        tone = raw.get("tone", "balanced")
        overlays = raw.get("overlays", "inherit")
        return cls(
            slide_id=slide_id,
            data=validated,
            tone=tone if tone in PLAYLIST_TONE_VALUES else "balanced",
            overlays=(
                overlays if overlays in {"inherit", "none", "custom"} else "inherit"
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.slide_id,
            "data": copy.deepcopy(self.data),
            "tone": self.tone,
            "overlays": self.overlays,
        }


@dataclass
class Playlist:
    """Named playlist shared by every loaded frame."""

    playlist_id: str
    name: str
    interval: int = DEFAULT_SCREEN_INTERVAL
    shuffle: bool = False
    slides: list[PlaylistSlide] = field(default_factory=list)
    modified_at: float = field(default_factory=time.time)

    @classmethod
    def from_dict(cls, raw: Any) -> Playlist | None:
        if not isinstance(raw, dict):
            _LOGGER.warning(
                "Ignoring invalid stored playlist: expected a mapping, got %s",
                type(raw).__name__,
            )
            return None
        playlist_id = raw.get("id")
        name = raw.get("name")
        if not isinstance(playlist_id, str) or not isinstance(name, str):
            _LOGGER.warning(
                "Ignoring invalid stored playlist %s: missing id or name",
                playlist_id if isinstance(playlist_id, str) else "<unknown>",
            )
            return None
        raw_slides = raw.get("slides", [])
        if not isinstance(raw_slides, list):
            raw_slides = []
        slides = [
            slide
            for item in raw_slides
            if (slide := PlaylistSlide.from_dict(item)) is not None
        ]
        interval = raw.get("interval", DEFAULT_SCREEN_INTERVAL)
        if not isinstance(interval, int) or isinstance(interval, bool):
            interval = DEFAULT_SCREEN_INTERVAL
        try:
            modified_at = float(raw.get("modified_at", 0) or 0)
        except (TypeError, ValueError):
            modified_at = 0
        if not math.isfinite(modified_at):
            modified_at = 0
        return cls(
            playlist_id=playlist_id,
            name=name.strip() or "Playlist",
            interval=max(MIN_SCREEN_INTERVAL, interval),
            shuffle=raw.get("shuffle") is True,
            slides=slides,
            modified_at=modified_at,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.playlist_id,
            "name": self.name,
            "interval": self.interval,
            "shuffle": self.shuffle,
            "slides": [slide.to_dict() for slide in self.slides],
            "modified_at": self.modified_at,
        }


class PlaylistManager:
    """Persist playlists, frame assignments, and one-way legacy migration."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.playlists: list[Playlist] = []
        self.assignments: dict[str, str] = {}
        self._migrated_entries: set[str] = set()
        self._store: Store[dict[str, Any]] = Store(hass, STORE_VERSION, STORE_KEY)
        self._lock = asyncio.Lock()
        self._undo: dict[str, tuple[float, str, int, PlaylistSlide]] = {}

    async def async_setup(self) -> None:
        data = await self._store.async_load() or {}
        if not isinstance(data, dict):
            data = {}
        raw_playlists = data.get("playlists", [])
        if not isinstance(raw_playlists, list):
            _LOGGER.warning("Ignoring invalid stored playlist collection")
            raw_playlists = []
        self.playlists = [
            playlist
            for raw in raw_playlists
            if (playlist := Playlist.from_dict(raw)) is not None
        ]
        valid_ids = {playlist.playlist_id for playlist in self.playlists}
        assignments = data.get("assignments", {})
        if isinstance(assignments, dict):
            self.assignments = {
                frame_id: playlist_id
                for frame_id, playlist_id in assignments.items()
                if isinstance(frame_id, str) and playlist_id in valid_ids
            }
        migrated = data.get("migrated_entries", [])
        if not isinstance(migrated, list):
            migrated = []
        self._migrated_entries = {
            entry_id for entry_id in migrated if isinstance(entry_id, str)
        }

    async def async_migrate_entry(self, entry: Any) -> None:
        """Snapshot legacy slides into a frame-named playlist exactly once."""
        if entry.entry_id in self._migrated_entries:
            return
        async with self._lock:
            if entry.entry_id in self._migrated_entries:
                return
            slides = self._legacy_slides(entry)
            if slides:
                playlist = Playlist(
                    playlist_id=uuid.uuid4().hex,
                    name=entry.title,
                    interval=slides[0].data.get("interval", DEFAULT_SCREEN_INTERVAL),
                    slides=slides,
                )
                self.playlists.append(playlist)
                self.assignments.setdefault(entry.entry_id, playlist.playlist_id)
            self._migrated_entries.add(entry.entry_id)
            await self._async_save()

    async def async_sync_legacy_slide(self, entry: Any, slide_id: str) -> None:
        """Copy one explicit legacy-editor update into its migrated slide."""
        current = next(
            (
                slide
                for slide in self._legacy_slides(entry)
                if slide.slide_id == slide_id
            ),
            None,
        )
        if current is None:
            return
        async with self._lock:
            changed = False
            for playlist in self.playlists:
                for stored in playlist.slides:
                    if stored.slide_id == slide_id and stored.data != current.data:
                        stored.data = current.data
                        playlist.modified_at = time.time()
                        changed = True
            if changed:
                await self._async_save()

    @staticmethod
    def _legacy_slides(entry: Any) -> list[PlaylistSlide]:
        """Read the current valid legacy subentries without mutating storage."""
        slides: list[PlaylistSlide] = []
        for subentry in getattr(entry, "subentries", {}).values():
            if subentry.subentry_type != SUBENTRY_TYPE_SCREEN:
                continue
            raw = dict(subentry.data)
            raw["name"] = subentry.title or raw.get("name") or "Slide"
            try:
                data = _validated_slide_data(raw)
            except vol.Invalid:
                continue
            slides.append(PlaylistSlide(subentry.subentry_id, data))
        return slides

    def get(self, playlist_id: str | None) -> Playlist | None:
        if playlist_id is None:
            return None
        return next(
            (
                playlist
                for playlist in self.playlists
                if playlist.playlist_id == playlist_id
            ),
            None,
        )

    def require(self, playlist_id: str) -> Playlist:
        playlist = self.get(playlist_id)
        if playlist is None:
            raise PlaylistNotFoundError(playlist_id)
        return playlist

    def assigned_to(self, frame_id: str) -> Playlist | None:
        return self.get(self.assignments.get(frame_id))

    def assigned_frames(self, playlist_id: str) -> list[str]:
        return [
            frame_id
            for frame_id, assigned_id in self.assignments.items()
            if assigned_id == playlist_id
        ]

    def render_slides(self, playlist_id: str | None) -> list[ScreenConfig]:
        playlist = self.get(playlist_id)
        if playlist is None:
            return []
        rendered: list[ScreenConfig] = []
        for slide in playlist.slides:
            if rendered_slide := self._render_slide(playlist, slide):
                rendered.append(rendered_slide)
        return rendered

    @staticmethod
    def _render_slide(playlist: Playlist, slide: PlaylistSlide) -> ScreenConfig | None:
        data = dict(slide.data)
        data["interval"] = playlist.interval
        try:
            rendered = screen_from_dict(data, slide.slide_id)
        except (KeyError, TypeError, ValueError):
            return None
        if rendered.kind == KIND_PICTURE:
            source = dict(rendered.source or {})
            source["tone"] = slide.tone
            rendered = replace(rendered, source=source)
        return replace(
            rendered,
            interval=playlist.interval,
            overlay_mode=slide.overlays,
        )

    def render_slide(self, playlist_id: str, slide_id: str) -> ScreenConfig | None:
        playlist = self.get(playlist_id)
        if playlist is None:
            return None
        slide = next(
            (item for item in playlist.slides if item.slide_id == slide_id), None
        )
        return self._render_slide(playlist, slide) if slide is not None else None

    def render_slide_by_id(self, slide_id: str) -> ScreenConfig | None:
        for playlist in self.playlists:
            if rendered_slide := self.render_slide(playlist.playlist_id, slide_id):
                return rendered_slide
        return None

    async def async_create(self, name: str) -> Playlist:
        name = name.strip()
        if not name:
            raise ValueError("Playlist name is required")
        playlist = Playlist(uuid.uuid4().hex, name)
        async with self._lock:
            self.playlists.append(playlist)
            await self._async_save()
        return playlist

    async def async_rename(self, playlist_id: str, name: str) -> Playlist:
        name = name.strip()
        if not name:
            raise ValueError("Playlist name is required")
        async with self._lock:
            playlist = self.require(playlist_id)
            playlist.name = name
            playlist.modified_at = time.time()
            await self._async_save()
            return playlist

    async def async_duplicate(self, playlist_id: str) -> Playlist:
        async with self._lock:
            source = self.require(playlist_id)
            duplicate = Playlist(
                playlist_id=uuid.uuid4().hex,
                name=f"{source.name} copy",
                interval=source.interval,
                shuffle=source.shuffle,
                slides=[
                    replace(copy.deepcopy(slide), slide_id=uuid.uuid4().hex)
                    for slide in source.slides
                ],
            )
            self.playlists.append(duplicate)
            await self._async_save()
            return duplicate

    async def async_delete(self, playlist_id: str) -> list[str]:
        async with self._lock:
            playlist = self.require(playlist_id)
            self.playlists.remove(playlist)
            affected = self.assigned_frames(playlist_id)
            for frame_id in affected:
                self.assignments.pop(frame_id, None)
            await self._async_save()
            return affected

    async def async_assign(self, frame_id: str, playlist_id: str | None) -> None:
        async with self._lock:
            if playlist_id is None:
                self.assignments.pop(frame_id, None)
            else:
                self.require(playlist_id)
                self.assignments[frame_id] = playlist_id
            await self._async_save()

    async def async_set_options(
        self,
        playlist_id: str,
        *,
        interval: int | None = None,
        shuffle: bool | None = None,
    ) -> Playlist:
        async with self._lock:
            playlist = self.require(playlist_id)
            if interval is not None:
                if isinstance(interval, bool) or interval < MIN_SCREEN_INTERVAL:
                    raise ValueError("Interval is too short")
                playlist.interval = interval
            if shuffle is not None:
                playlist.shuffle = shuffle
            playlist.modified_at = time.time()
            await self._async_save()
            return playlist

    async def async_reorder(self, playlist_id: str, ordered_ids: list[str]) -> None:
        async with self._lock:
            playlist = self.require(playlist_id)
            existing = [slide.slide_id for slide in playlist.slides]
            if Counter(existing) != Counter(ordered_ids):
                raise PlaylistChangedError(
                    "The playlist changed before it was reordered"
                )
            by_id = {slide.slide_id: slide for slide in playlist.slides}
            playlist.slides = [by_id[slide_id] for slide_id in ordered_ids]
            playlist.modified_at = time.time()
            await self._async_save()

    async def async_add_slides(
        self,
        playlist_id: str,
        raw_slides: list[dict[str, Any]],
        *,
        insert_at: int | None = None,
    ) -> Playlist:
        """Validate and append or position slides supplied by the add menu."""
        if insert_at is not None and (
            isinstance(insert_at, bool) or not isinstance(insert_at, int)
        ):
            raise ValueError("Playlist position must be a number")
        slides: list[PlaylistSlide] = []
        for raw in raw_slides:
            if not isinstance(raw, dict):
                raise ValueError(  # noqa: TRY004 - public mutation contract
                    "Invalid slide: expected a mapping"
                )
            try:
                data = _validated_slide_data(raw)
            except (TypeError, vol.Invalid) as err:
                raise ValueError(f"Invalid slide: {err}") from err
            tone = data.get("tone", "balanced")
            slides.append(
                PlaylistSlide(
                    uuid.uuid4().hex,
                    data,
                    tone=tone if tone in PLAYLIST_TONE_VALUES else "balanced",
                )
            )
        if not slides:
            raise ValueError("Choose at least one slide")
        async with self._lock:
            playlist = self.require(playlist_id)
            if insert_at is None:
                playlist.slides.extend(slides)
            else:
                index = max(0, min(insert_at, len(playlist.slides)))
                playlist.slides[index:index] = slides
            playlist.modified_at = time.time()
            await self._async_save()
            return playlist

    async def async_prune_image(self, image_id: str) -> set[str]:
        """Remove every slide that refers to a deleted library picture."""
        affected: set[str] = set()
        async with self._lock:
            for playlist in self.playlists:
                kept = [
                    slide
                    for slide in playlist.slides
                    if slide.data.get("library_image") != image_id
                ]
                if len(kept) == len(playlist.slides):
                    continue
                playlist.slides = kept
                playlist.modified_at = time.time()
                affected.add(playlist.playlist_id)
            if affected:
                await self._async_save()
        return affected

    async def async_remove_slide(self, playlist_id: str, slide_id: str) -> str:
        async with self._lock:
            playlist = self.require(playlist_id)
            index = next(
                (
                    position
                    for position, slide in enumerate(playlist.slides)
                    if slide.slide_id == slide_id
                ),
                None,
            )
            if index is None:
                raise PlaylistChangedError("That slide is no longer in the playlist")
            slide = playlist.slides.pop(index)
            token = uuid.uuid4().hex
            now = time.monotonic()
            self._undo = {
                key: undo for key, undo in self._undo.items() if undo[0] >= now
            }
            self._undo[token] = (now + 8, playlist_id, index, slide)
            playlist.modified_at = time.time()
            await self._async_save()
            return token

    async def async_undo_remove(self, playlist_id: str, token: str) -> None:
        async with self._lock:
            undo = self._undo.get(token)
            if undo is None or undo[0] < time.monotonic():
                self._undo.pop(token, None)
                raise PlaylistChangedError("Undo is no longer available")
            _, owner_id, index, slide = undo
            if owner_id != playlist_id:
                raise PlaylistChangedError("Undo belongs to another playlist")
            self._undo.pop(token, None)
            playlist = self.require(playlist_id)
            if any(item.slide_id == slide.slide_id for item in playlist.slides):
                raise PlaylistChangedError("That slide is already in the playlist")
            playlist.slides.insert(min(index, len(playlist.slides)), slide)
            playlist.modified_at = time.time()
            await self._async_save()

    async def async_update_slide(
        self,
        playlist_id: str,
        slide_id: str,
        *,
        fit: str | None = None,
        tone: str | None = None,
        overlays: str | None = None,
    ) -> None:
        async with self._lock:
            playlist = self.require(playlist_id)
            slide = next(
                (item for item in playlist.slides if item.slide_id == slide_id),
                None,
            )
            if slide is None:
                raise PlaylistChangedError("That slide is no longer in the playlist")
            if fit is not None:
                if fit not in {"cover", "contain"}:
                    raise ValueError("Unknown fit")
                if slide.data.get("kind") == KIND_PICTURE:
                    slide.data["fit"] = fit
            if tone is not None:
                if tone not in PLAYLIST_TONE_VALUES:
                    raise ValueError("Unknown tone")
                slide.tone = tone
            if overlays is not None:
                if overlays not in {"inherit", "none", "custom"}:
                    raise ValueError("Unknown overlay mode")
                slide.overlays = overlays
            playlist.modified_at = time.time()
            await self._async_save()

    async def _async_save(self) -> None:
        await self._store.async_save(
            {
                "playlists": [playlist.to_dict() for playlist in self.playlists],
                "assignments": dict(self.assignments),
                "migrated_entries": sorted(self._migrated_entries),
            }
        )
