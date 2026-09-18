"""A frame's playback session, independent of saved playlists."""

from __future__ import annotations

import copy
import random
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime

from .const import DEFAULT_SCREEN_INTERVAL, MIN_SCREEN_INTERVAL
from .render.playlist import eligible
from .render.schema import (
    SCREEN_SCHEMA,
    ScreenConfig,
    screen_from_dict,
    screen_to_dict,
)


@dataclass
class QueueItem:
    screen: ScreenConfig
    sequence: int
    playlist_id: str | None = None
    playlist_name: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.screen.screen_id,
            "screen": screen_to_dict(self.screen),
            "overlays": self.screen.overlay_mode,
            "sequence": self.sequence,
            "playlist_id": self.playlist_id,
            "playlist_name": self.playlist_name,
        }

    @classmethod
    def from_dict(cls, data: dict) -> QueueItem:
        screen = screen_from_dict(SCREEN_SCHEMA(data["screen"]), data["id"])
        return cls(
            replace(screen, overlay_mode=data.get("overlays", "inherit")),
            int(data["sequence"]),
            data.get("playlist_id"),
            data.get("playlist_name"),
        )


@dataclass
class PlaybackQueue:
    items: list[QueueItem] = field(default_factory=list)
    cursor: str | None = None
    interval: int = DEFAULT_SCREEN_INTERVAL
    shuffle: bool = False
    repeat: bool = False

    @property
    def position(self) -> int:
        return next(
            (
                i
                for i, item in enumerate(self.items)
                if item.screen.screen_id == self.cursor
            ),
            -1,
        )

    @property
    def upcoming(self) -> list[QueueItem]:
        return self.items[self.position + 1 :]

    def get(self, item_id: str | None) -> QueueItem | None:
        return next(
            (item for item in self.items if item.screen.screen_id == item_id), None
        )

    def candidate(self, now: datetime, *, previous: bool = False) -> QueueItem | None:
        if previous:
            candidates = list(reversed(self.items[: max(0, self.position)]))
            if self.repeat:
                candidates.extend(reversed(self.items[max(0, self.position) :]))
        else:
            candidates = self.upcoming
            if self.repeat:
                candidates = [*candidates, *self.items[: self.position + 1]]
        return next((item for item in candidates if eligible(item.screen, now)), None)

    def advance(self, item_id: str, now: datetime) -> None:
        """Consume an item while keeping window-deferred items upcoming."""
        item = self.get(item_id)
        if item is None:
            return
        target = self.items.index(item)
        deferred = [
            candidate
            for candidate in self.items[self.position + 1 : target]
            if not eligible(candidate.screen, now)
        ]
        for candidate in deferred:
            self.items.remove(candidate)
        target = self.items.index(item)
        self.items[target + 1 : target + 1] = deferred
        self.cursor = item_id

    def add(
        self,
        screens: list[ScreenConfig],
        *,
        index: int | None = None,
        playlist_id: str | None = None,
        playlist_name: str | None = None,
    ) -> list[QueueItem]:
        sequence = max((item.sequence for item in self.items), default=-1) + 1
        added = [
            QueueItem(
                replace(copy.deepcopy(screen), screen_id=f"queue_{uuid.uuid4().hex}"),
                sequence + i,
                playlist_id,
                playlist_name,
            )
            for i, screen in enumerate(screens)
        ]
        at = (
            len(self.items)
            if index is None
            else self.position + 1 + max(0, min(index, len(self.upcoming)))
        )
        self.items[at:at] = added
        return added

    def clear(self) -> None:
        current = self.get(self.cursor)
        self.items = [current] if current else []
        self.repeat = False

    def remove(self, index: int, item_id: str) -> None:
        upcoming = self.upcoming
        if (
            not 0 <= index < len(upcoming)
            or upcoming[index].screen.screen_id != item_id
        ):
            raise ValueError("That queue item is no longer available")
        self.items.remove(upcoming[index])

    def reorder(self, ordered_ids: list[str]) -> None:
        upcoming = {item.screen.screen_id: item for item in self.upcoming}
        if len(ordered_ids) != len(upcoming) or set(ordered_ids) != set(upcoming):
            raise ValueError("The queue changed before it could be reordered")
        self.items[self.position + 1 :] = [upcoming[item_id] for item_id in ordered_ids]
        # An explicit order becomes the order restored when shuffle is disabled.
        for sequence, item in enumerate(self.items):
            item.sequence = sequence

    def set_shuffle(self, enabled: bool) -> None:
        upcoming = self.upcoming
        if enabled:
            random.shuffle(upcoming)
        else:
            upcoming.sort(key=lambda item: item.sequence)
        self.items[self.position + 1 :] = upcoming
        self.shuffle = enabled

    def to_dict(self) -> dict:
        return {
            "items": [item.to_dict() for item in self.items],
            "cursor": self.cursor,
            "interval": self.interval,
            "shuffle": self.shuffle,
            "repeat": self.repeat,
        }

    @classmethod
    def from_dict(cls, data: dict) -> PlaybackQueue:
        queue = cls(
            interval=int(data["interval"]),
            shuffle=data.get("shuffle") is True,
            repeat=data.get("repeat") is True,
        )
        if queue.interval < MIN_SCREEN_INTERVAL:
            raise ValueError("Invalid queue interval")
        for raw in data["items"]:
            item = QueueItem.from_dict(raw)
            if queue.get(item.screen.screen_id) is not None:
                raise ValueError("Duplicate queue item id")
            queue.items.append(item)
        queue.cursor = data.get("cursor") if queue.get(data.get("cursor")) else None
        return queue
