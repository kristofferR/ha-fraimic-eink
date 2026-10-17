"""Auto mode: new art on a schedule once a frame's queue runs out.

HA-free so the decisions (weighted sources, repeat avoidance, cadence) run in
the headless test suite. ``auto_sources.py`` turns a chosen source into one
concrete picture; the scheduler keeps ``LOOKAHEAD`` resolved picks queued.
"""

from __future__ import annotations

import random
import re
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, time, timedelta
from typing import Any

import voluptuous as vol

from .const import DEFAULT_SCREEN_INTERVAL, MIN_SCREEN_INTERVAL
from .render.schema import DAYS, WINDOW_SCHEMA, ScreenConfig, TimeWindow

END_STOP = "stop"
END_REPEAT = "repeat"
END_AUTO = "auto"
END_ACTIONS = (END_STOP, END_REPEAT, END_AUTO)

SOURCE_SHUFFLE = "shuffle"  # a random museum each pick
SOURCE_GALLERY = "gallery"  # any gallery location: source + folder + search
SOURCE_PLAYLIST = "playlist"  # a random slide from a saved playlist
SOURCE_KINDS = (SOURCE_SHUFFLE, SOURCE_GALLERY, SOURCE_PLAYLIST)

CADENCE_QUEUE = "queue"  # the only cadence cloud delivery can honour
CADENCE_INTERVAL = "interval"
CADENCE_TIMES = "times"
CADENCES = (CADENCE_QUEUE, CADENCE_INTERVAL, CADENCE_TIMES)

AVOID_UNTIL_ALL_SHOWN = -1
DEFAULT_AVOID_DAYS = 30
LOOKAHEAD = 3
HISTORY_LIMIT = 1000
MAX_SOURCES = 12
SHUFFLE_LABEL = "Surprise me"

_TIME = vol.Match(re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$"), msg="expected HH:MM")


class AutoSourceQueued(Exception):
    """All candidates from a source are already in the upcoming queue."""


def _source_requirements(data: dict[str, Any]) -> dict[str, Any]:
    if data["kind"] == SOURCE_GALLERY and not data["source"]:
        raise vol.Invalid("a gallery source needs a source key")
    if data["kind"] == SOURCE_PLAYLIST and not data["playlist_id"]:
        raise vol.Invalid("a playlist source needs a playlist_id")
    return data


SOURCE_SCHEMA = vol.All(
    vol.Schema(
        {
            vol.Required("kind"): vol.In(SOURCE_KINDS),
            vol.Optional("source", default=""): str,
            vol.Optional("browse_id", default=""): str,
            vol.Optional("query", default=""): str,
            vol.Optional("playlist_id", default=""): str,
            vol.Optional("label", default=""): str,
            vol.Optional("weight", default=1): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=3)
            ),
        }
    ),
    _source_requirements,
)

# Every key is optional so the same schema validates partial updates.
SETTINGS_SCHEMA = vol.Schema(
    {
        vol.Optional("sources"): vol.All(
            [SOURCE_SCHEMA], vol.Length(min=1, max=MAX_SOURCES)
        ),
        vol.Optional("cadence"): vol.In(CADENCES),
        vol.Optional("interval"): vol.All(
            vol.Coerce(int), vol.Range(min=MIN_SCREEN_INTERVAL)
        ),
        vol.Optional("times"): vol.All([_TIME], vol.Length(max=12)),
        vol.Optional("days"): [vol.In(DAYS)],
        vol.Optional("active_hours"): vol.Any(None, WINDOW_SCHEMA),
        vol.Optional("avoid_repeats_days"): vol.All(
            vol.Coerce(int), vol.Range(min=AVOID_UNTIL_ALL_SHOWN, max=365)
        ),
        vol.Optional("orientation"): vol.In(("prefer", "strict")),
        vol.Optional("caption"): bool,
        vol.Optional("tone"): vol.In(("vivid", "balanced", "soft")),
        vol.Optional("fit"): vol.Any(None, vol.In(("cover", "contain", "contain_black"))),
        vol.Optional("overlays"): vol.In(("inherit", "none")),
    }
)


@dataclass(frozen=True)
class AutoSource:
    """One place auto mode draws art from."""

    kind: str
    source: str = ""
    browse_id: str = ""
    query: str = ""
    playlist_id: str = ""
    label: str = ""
    weight: int = 1

    @property
    def key(self) -> str:
        """Identity for de-duplication and failure backoff."""
        return "\x00".join(
            (self.kind, self.source, self.browse_id, self.query, self.playlist_id)
        )

    @property
    def title(self) -> str:
        return self.label or (SHUFFLE_LABEL if self.kind == SOURCE_SHUFFLE else "Auto")

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "source": self.source,
            "browse_id": self.browse_id,
            "query": self.query,
            "playlist_id": self.playlist_id,
            "label": self.label,
            "weight": self.weight,
        }


@dataclass(frozen=True)
class AutoSettings:
    """Per-frame auto mode options (whether it runs is the queue's end action)."""

    sources: tuple[AutoSource, ...] = (AutoSource(SOURCE_SHUFFLE, label=SHUFFLE_LABEL),)
    cadence: str = CADENCE_QUEUE
    interval: int = DEFAULT_SCREEN_INTERVAL
    times: tuple[time, ...] = ()
    days: frozenset[int] = frozenset()  # empty = every day
    active_hours: TimeWindow | None = None
    avoid_repeats_days: int = DEFAULT_AVOID_DAYS
    strict_orientation: bool = False
    caption: bool = False
    tone: str = "balanced"
    fit: str | None = None  # None = the frame's default fit
    overlays: str = "inherit"

    def to_dict(self) -> dict[str, Any]:
        return {
            "sources": [source.to_dict() for source in self.sources],
            "cadence": self.cadence,
            "interval": self.interval,
            "times": [value.strftime("%H:%M") for value in self.times],
            "days": [DAYS[day] for day in sorted(self.days)],
            "active_hours": _window_to_dict(self.active_hours),
            "avoid_repeats_days": self.avoid_repeats_days,
            "orientation": "strict" if self.strict_orientation else "prefer",
            "caption": self.caption,
            "tone": self.tone,
            "fit": self.fit,
            "overlays": self.overlays,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AutoSettings:
        return cls().updated(data)

    def updated(self, patch: dict[str, Any]) -> AutoSettings:
        """Apply a validated partial update; raises ``vol.Invalid``."""
        data = SETTINGS_SCHEMA(dict(patch))
        settings = replace(
            self,
            **{
                key: value
                for key, value in {
                    "sources": tuple(
                        _labelled(AutoSource(**source))
                        for source in data.get("sources", ())
                    )
                    or None,
                    "cadence": data.get("cadence"),
                    "interval": data.get("interval"),
                    "times": tuple(sorted({_parse_time(v) for v in data["times"]}))
                    if "times" in data
                    else None,
                    "days": frozenset(DAYS.index(day) for day in data["days"])
                    if "days" in data
                    else None,
                    "avoid_repeats_days": data.get("avoid_repeats_days"),
                    "strict_orientation": data["orientation"] == "strict"
                    if "orientation" in data
                    else None,
                    "caption": data.get("caption"),
                    "tone": data.get("tone"),
                    "overlays": data.get("overlays"),
                }.items()
                if value is not None
            },
        )
        if "fit" in data:
            settings = replace(settings, fit=data["fit"])
        if "active_hours" in data:
            settings = replace(settings, active_hours=_parse_window(data["active_hours"]))
        if len({source.key for source in settings.sources}) != len(settings.sources):
            raise vol.Invalid("each auto source can only be added once")
        if settings.cadence == CADENCE_TIMES and not settings.times:
            raise vol.Invalid("set times need at least one time of day")
        return settings

    def next_change(
        self, last_change: datetime | None, queue_interval: int
    ) -> datetime | None:
        """When an auto pick may replace a picture shown at ``last_change``.

        ``last_change`` must be in the frame's local timezone so set times
        follow the wall clock across DST changes. None = due now.
        """
        if last_change is None:
            return None
        if self.cadence == CADENCE_QUEUE:
            return last_change.astimezone(UTC) + timedelta(seconds=queue_interval)
        if self.cadence == CADENCE_INTERVAL:
            return last_change.astimezone(UTC) + timedelta(seconds=self.interval)
        for offset in range(8):
            day = last_change.date() + timedelta(days=offset)
            if self.days and day.weekday() not in self.days:
                continue
            for value in self.times:
                slot = datetime.combine(day, value, tzinfo=last_change.tzinfo)
                if slot > last_change:
                    return slot
        return None


def _labelled(source: AutoSource) -> AutoSource:
    return source if source.label else replace(source, label=source.title)


def _parse_time(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


def _parse_window(data: dict[str, Any] | None) -> TimeWindow | None:
    if data is None:
        return None
    return TimeWindow(
        after=_parse_time(data["after"]),
        before=_parse_time(data["before"]),
        days=frozenset(DAYS.index(day) for day in data["days"]),
    )


def _window_to_dict(window: TimeWindow | None) -> dict[str, Any] | None:
    if window is None:
        return None
    return {
        "after": window.after.strftime("%H:%M"),
        "before": window.before.strftime("%H:%M"),
        "days": [DAYS[day] for day in sorted(window.days)],
    }


def pick_source(
    sources: Iterable[AutoSource],
    unavailable: set[str] | frozenset[str] = frozenset(),
    rng: random.Random | None = None,
) -> AutoSource | None:
    """Weighted random choice among sources that are not backing off."""
    usable = [source for source in sources if source.key not in unavailable]
    if not usable:
        return None
    return (rng or random).choices(usable, weights=[s.weight for s in usable])[0]


def picture_key(screen: ScreenConfig) -> str | None:
    """Stable identity of the artwork a slide shows, for repeat avoidance."""
    source = screen.source or {}
    if image_id := source.get("library_image"):
        return f"library:{image_id}"
    if source.get("provider") and source.get("provider_item"):
        return f"provider:{source['provider']}:{source['provider_item']}"
    if url := source.get("url"):
        return f"url:{url}"
    return None


@dataclass
class AutoHistory:
    """When each artwork was last shown (or skipped), oldest first."""

    entries: dict[str, datetime] = field(default_factory=dict)

    def record(self, key: str, at: datetime) -> None:
        self.entries.pop(key, None)
        self.entries[key] = at
        while len(self.entries) > HISTORY_LIMIT:
            del self.entries[next(iter(self.entries))]

    def recent(self, avoid_days: int, now: datetime) -> set[str]:
        """Keys that should not be picked again yet."""
        if avoid_days == 0:
            return set()
        if avoid_days == AVOID_UNTIL_ALL_SHOWN:
            return set(self.entries)
        cutoff = now - timedelta(days=avoid_days)
        return {key for key, at in self.entries.items() if at >= cutoff}

    def choose(
        self,
        keys: Iterable[str],
        avoid_days: int,
        now: datetime,
        *,
        exclude: set[str] | frozenset[str] = frozenset(),
        rng: random.Random | None = None,
    ) -> str | None:
        """A random fresh key, else the least recently shown one.

        Small pools never stall: once everything was shown recently, the
        oldest showing wins. ``exclude`` (already queued) is never returned.
        """
        candidates = list(dict.fromkeys(key for key in keys if key not in exclude))
        if not candidates:
            return None
        recent = self.recent(avoid_days, now)
        fresh = [key for key in candidates if key not in recent]
        if fresh:
            return (rng or random).choice(fresh)
        order = {key: index for index, key in enumerate(self.entries)}
        return min(candidates, key=lambda key: order.get(key, -1))

    def to_list(self) -> list[list[str]]:
        return [[key, at.isoformat()] for key, at in self.entries.items()]

    @classmethod
    def from_list(cls, data: Any) -> AutoHistory:
        history = cls()
        for row in data if isinstance(data, list) else ():
            try:
                key, stamp = row
                history.record(str(key), datetime.fromisoformat(stamp))
            except (TypeError, ValueError):
                continue
        return history
