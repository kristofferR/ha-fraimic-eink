"""Screen definition schema and dataclasses.

One schema, two front doors: the ``fraimic.render_screen`` service payload and
(later) config-subentry storage validate against the same shape, so a screen
built in YAML can be pasted into the UI and vice versa.

Widget dicts are flat (``type`` + ``slot`` + the widget's own options at the
top level) for pleasant YAML; internally options are split out into
``WidgetConfig.options``.

Pure voluptuous only — no Home Assistant imports — so this module loads in the
headless test suite. Entity ids are validated as plain strings here; whether
they exist is a runtime concern (a missing entity renders an error placeholder
rather than failing the screen).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, time

import voluptuous as vol

from ..const import DEFAULT_SCREEN_INTERVAL, MIN_SCREEN_INTERVAL, PALETTE_NAMES
from .layout import LAYOUT_SLOTS

KIND_DASHBOARD = "dashboard"
KIND_PICTURE = "picture"

_COLOR = vol.In(sorted(PALETTE_NAMES))
_HTTP_URL = vol.Match(re.compile(r"^https?://"), msg="expected an http(s) URL")
_ENTITY_ID = vol.Match(
    re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$"), msg="expected an entity id"
)

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def _clock_format(value: str) -> str:
    """A strftime format without second-or-finer tokens.

    The playlist skips uploads when the rendered content is unchanged; a
    seconds-bearing clock would defeat that on every cycle.
    """
    for token in ("%S", "%f", "%c", "%X", "%T", "%s"):
        if token in value:
            raise vol.Invalid(f"clock format must not contain {token}")
    return _strftime(value)


def _strftime(value: str) -> str:
    try:
        datetime(2026, 1, 5, 13, 37).strftime(value)
    except ValueError as err:
        raise vol.Invalid(f"invalid strftime format: {err}") from err
    return value


def _time_str(value: str) -> str:
    if not isinstance(value, str) or not _TIME_RE.match(value):
        raise vol.Invalid("expected a time as HH:MM")
    return value


# Per-widget-type option schemas (the widget dict minus ``type`` and ``slot``).
WIDGET_OPTION_SCHEMAS: dict[str, vol.Schema] = {
    "clock": vol.Schema(
        {vol.Optional("format", default="%H:%M"): vol.All(str, _clock_format)}
    ),
    "date": vol.Schema(
        {vol.Optional("format", default="%A, %-d %B"): vol.All(str, _strftime)}
    ),
    "stat": vol.Schema(
        {
            vol.Required("entity"): _ENTITY_ID,
            vol.Optional("name"): str,
            vol.Optional("icon"): str,
            vol.Optional("unit"): str,
            vol.Optional("precision"): vol.All(vol.Coerce(int), vol.Range(min=0, max=3)),
            vol.Optional("trend", default=False): bool,
            vol.Optional("trend_hours", default=1): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=48)
            ),
            vol.Optional("color"): _COLOR,
        }
    ),
    "entities": vol.Schema(
        {
            vol.Required("entities"): vol.All(
                [
                    vol.Any(
                        _ENTITY_ID,
                        vol.Schema(
                            {
                                vol.Required("entity"): _ENTITY_ID,
                                vol.Optional("name"): str,
                                vol.Optional("icon"): str,
                            }
                        ),
                    )
                ],
                vol.Length(min=1, max=30),
            ),
            vol.Optional("max_rows"): vol.All(vol.Coerce(int), vol.Range(min=1, max=30)),
        }
    ),
    "template": vol.Schema(
        {
            vol.Required("template"): str,
            vol.Optional("align", default="left"): vol.In(("left", "center")),
            vol.Optional("size", default="m"): vol.In(("s", "m", "l")),
        }
    ),
    "weather_current": vol.Schema(
        {
            vol.Required("entity"): _ENTITY_ID,
            vol.Optional("name"): str,
        }
    ),
    "weather_forecast": vol.Schema(
        {
            vol.Required("entity"): _ENTITY_ID,
            vol.Optional("mode", default="daily"): vol.In(("hourly", "daily")),
            vol.Optional("count", default=5): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=8)
            ),
        }
    ),
    "calendar": vol.Schema(
        {
            vol.Required("entities"): vol.All(
                [_ENTITY_ID], vol.Length(min=1, max=5)
            ),
            vol.Optional("days", default=7): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=14)
            ),
            vol.Optional("max_events"): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=20)
            ),
        }
    ),
    "todo": vol.Schema(
        {
            vol.Required("entity"): _ENTITY_ID,
            vol.Optional("max_items"): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=20)
            ),
            vol.Optional("show_completed", default=False): bool,
        }
    ),
    "chart": vol.Schema(
        {
            vol.Required("entities"): vol.All(
                [_ENTITY_ID], vol.Length(min=1, max=3)
            ),
            vol.Optional("hours", default=24): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=168)
            ),
            vol.Optional("style", default="line"): vol.In(("line", "area", "bar")),
            vol.Optional("min"): vol.Coerce(float),
            vol.Optional("max"): vol.Coerce(float),
            vol.Optional("name"): str,
        }
    ),
    "gauge": vol.Schema(
        {
            vol.Required("entity"): _ENTITY_ID,
            vol.Optional("min", default=0.0): vol.Coerce(float),
            vol.Optional("max", default=100.0): vol.Coerce(float),
            vol.Optional("name"): str,
            vol.Optional("unit"): str,
            vol.Optional("color"): _COLOR,
            vol.Optional("thresholds"): [
                vol.Schema(
                    {vol.Required("from"): vol.Coerce(float), vol.Required("color"): _COLOR}
                )
            ],
        }
    ),
    "progress": vol.Schema(
        {
            vol.Required("entity"): _ENTITY_ID,
            vol.Optional("min", default=0.0): vol.Coerce(float),
            vol.Optional("max", default=100.0): vol.Coerce(float),
            vol.Optional("name"): str,
            vol.Optional("color"): _COLOR,
        }
    ),
    "image": vol.Schema(
        {
            vol.Optional("url"): _HTTP_URL,
            vol.Optional("entity"): _ENTITY_ID,
            vol.Optional("fit", default="cover"): vol.In(("cover", "contain")),
        }
    ),
}

WINDOW_SCHEMA = vol.Schema(
    {
        vol.Optional("after", default="00:00"): _time_str,
        vol.Optional("before", default="23:59"): _time_str,
        vol.Optional("days", default=[]): [vol.In(DAYS)],
    }
)

def _validate_screen(data: dict) -> dict:
    """Cross-field validation: kind-dependent requirements, slots fit layout."""
    if data["kind"] == KIND_PICTURE:
        sources = [key for key in ("url", "entity") if data.get(key)]
        if len(sources) != 1:
            raise vol.Invalid("a picture screen needs exactly one of: url, entity")
        if data.get("widgets") or data.get("layout"):
            raise vol.Invalid("picture screens take no layout/widgets — just a source")
        return data
    if data.get("url") or data.get("entity"):
        raise vol.Invalid("url/entity are only valid on kind: picture screens")
    if not data.get("layout"):
        raise vol.Invalid("required key not provided: layout")
    if not data.get("widgets"):
        raise vol.Invalid("required key not provided: widgets")
    layout_slots = LAYOUT_SLOTS[data["layout"]]
    seen: set[str] = set()
    widgets = []
    for raw in data["widgets"]:
        if not isinstance(raw, dict):
            raise vol.Invalid("each widget must be a mapping")
        wtype = raw.get("type")
        if wtype not in WIDGET_OPTION_SCHEMAS:
            raise vol.Invalid(
                f"unknown widget type {wtype!r}; expected one of "
                f"{', '.join(sorted(WIDGET_OPTION_SCHEMAS))}"
            )
        slot = raw.get("slot")
        if slot not in layout_slots:
            raise vol.Invalid(
                f"slot {slot!r} is not valid for layout {data['layout']!r} "
                f"(expected one of {', '.join(layout_slots)})"
            )
        if slot in seen:
            raise vol.Invalid(f"slot {slot!r} has more than one widget")
        seen.add(slot)
        options = {k: v for k, v in raw.items() if k not in ("type", "slot")}
        try:
            options = WIDGET_OPTION_SCHEMAS[wtype](options)
        except vol.Invalid as err:
            raise vol.Invalid(f"widget {wtype!r} in slot {slot!r}: {err}") from err
        widgets.append({"type": wtype, "slot": slot, "options": options})
    data = dict(data)
    data["widgets"] = widgets
    return data


SCREEN_SCHEMA = vol.All(
    vol.Schema(
        {
            vol.Optional("name", default="Dashboard"): str,
            vol.Optional("kind", default=KIND_DASHBOARD): vol.In(
                (KIND_DASHBOARD, KIND_PICTURE)
            ),
            vol.Optional("layout"): vol.In(sorted(LAYOUT_SLOTS)),
            vol.Optional("widgets", default=[]): vol.All(list, vol.Length(max=4)),
            # Picture-screen source (kind: picture only) — shown full-bleed via
            # the normal photo pipeline (dithered, preprocessed).
            vol.Optional("url"): _HTTP_URL,
            vol.Optional("entity"): _ENTITY_ID,
            vol.Optional("fit"): vol.In(("cover", "contain", "contain_black", "stretch")),
            vol.Optional("mode"): vol.In(
                ("auto", "none", "bayer", "floyd_steinberg", "atkinson")
            ),
            vol.Optional("background", default="white"): _COLOR,
            vol.Optional("accent", default="red"): _COLOR,
            vol.Optional("padding", default=32): vol.All(
                vol.Coerce(int), vol.Range(min=0, max=200)
            ),
            vol.Optional("show_header", default=True): bool,
            # Playlist fields (used by the scheduler once it lands; carried in
            # the shared schema from day one so stored screens never migrate).
            vol.Optional("interval", default=DEFAULT_SCREEN_INTERVAL): vol.All(
                vol.Coerce(int), vol.Range(min=MIN_SCREEN_INTERVAL)
            ),
            vol.Optional("windows", default=[]): [WINDOW_SCHEMA],
            vol.Optional("enabled", default=True): bool,
        }
    ),
    _validate_screen,
)


@dataclass(frozen=True)
class WidgetConfig:
    type: str
    slot: str
    options: dict


@dataclass(frozen=True)
class TimeWindow:
    after: time
    before: time
    days: frozenset[int] = frozenset()  # 0=Mon .. 6=Sun; empty = every day


@dataclass(frozen=True)
class ScreenConfig:
    screen_id: str
    name: str
    layout: str
    widgets: tuple[WidgetConfig, ...]
    kind: str = KIND_DASHBOARD
    source: dict | None = None  # picture screens: url/entity/fit/mode
    background: str = "white"
    accent: str = "red"
    padding: int = 32
    show_header: bool = True
    interval: int = DEFAULT_SCREEN_INTERVAL
    windows: tuple[TimeWindow, ...] = ()
    enabled: bool = True


def _parse_time(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


def screen_from_dict(data: dict, screen_id: str = "adhoc") -> ScreenConfig:
    """Build a ScreenConfig from an (already SCREEN_SCHEMA-validated) dict."""
    source = None
    if data["kind"] == KIND_PICTURE:
        source = {
            key: data[key] for key in ("url", "entity", "fit", "mode") if key in data
        }
    return ScreenConfig(
        screen_id=screen_id,
        name=data["name"],
        kind=data["kind"],
        source=source,
        layout=data.get("layout", "full"),
        widgets=tuple(
            WidgetConfig(w["type"], w["slot"], w["options"]) for w in data["widgets"]
        ),
        background=data["background"],
        accent=data["accent"],
        padding=data["padding"],
        show_header=data["show_header"],
        interval=data["interval"],
        windows=tuple(
            TimeWindow(
                after=_parse_time(w["after"]),
                before=_parse_time(w["before"]),
                days=frozenset(DAYS.index(d) for d in w["days"]),
            )
            for w in data["windows"]
        ),
        enabled=data["enabled"],
    )
