"""Field descriptors for the panel's WYSIWYG screen editor.

The editor renders its forms from this hand-authored description of the
widget option schemas (voluptuous schemas aren't introspectable enough to
generate forms from). A test asserts the keys stay in sync with
``render.schema.WIDGET_OPTION_SCHEMAS`` so a new widget type can't silently
miss the editor.

Field ``type`` vocabulary understood by the frontend form renderer:
``text``, ``textarea``, ``number``, ``bool``, ``select`` (with ``options``),
``entity`` (text input with an entity-id datalist), ``entity_list``
(textarea, one entity id per line).

Pure data, no Home Assistant imports — standalone-testable.
"""

from __future__ import annotations

from typing import Any, Final

_COLOR_OPTIONS = ["black", "white", "yellow", "red", "blue", "green"]


def _field(key: str, ftype: str, label: str, **extra: Any) -> dict[str, Any]:
    return {"key": key, "type": ftype, "label": label, **extra}


WIDGET_FIELDS: Final[dict[str, dict[str, Any]]] = {
    "clock": {
        "label": "Clock",
        "fields": [
            _field("format", "text", "Time format", default="%H:%M", help="strftime, no seconds"),
        ],
    },
    "date": {
        "label": "Date",
        "fields": [
            _field("format", "text", "Date format", default="%A, %-d %B"),
        ],
    },
    "stat": {
        "label": "Stat (single value)",
        "fields": [
            _field("entity", "entity", "Entity", required=True),
            _field("name", "text", "Name"),
            _field("icon", "text", "Icon", help="mdi:name"),
            _field("unit", "text", "Unit"),
            _field("precision", "number", "Decimals", min=0, max=3),
            _field("trend", "bool", "Trend arrow", default=False),
            _field("trend_hours", "number", "Trend hours", default=1, min=1, max=48),
            _field("color", "select", "Accent colour", options=_COLOR_OPTIONS),
        ],
    },
    "entities": {
        "label": "Entity list",
        "fields": [
            _field("entities", "entity_list", "Entities", required=True),
            _field("max_rows", "number", "Max rows", min=1, max=30),
        ],
    },
    "template": {
        "label": "Template text",
        "fields": [
            _field("template", "textarea", "Jinja template", required=True),
            _field("align", "select", "Align", options=["left", "center"], default="left"),
            _field("size", "select", "Size", options=["s", "m", "l"], default="m"),
        ],
    },
    "weather_current": {
        "label": "Weather now",
        "fields": [
            _field("entity", "entity", "Weather entity", required=True),
            _field("name", "text", "Name"),
        ],
    },
    "weather_forecast": {
        "label": "Weather forecast",
        "fields": [
            _field("entity", "entity", "Weather entity", required=True),
            _field("mode", "select", "Mode", options=["daily", "hourly"], default="daily"),
            _field("count", "number", "Periods", default=5, min=1, max=8),
        ],
    },
    "calendar": {
        "label": "Agenda",
        "fields": [
            _field("entities", "entity_list", "Calendars", required=True),
            _field("days", "number", "Days ahead", default=7, min=1, max=14),
            _field("max_events", "number", "Max events", min=1, max=20),
        ],
    },
    "todo": {
        "label": "To-do list",
        "fields": [
            _field("entity", "entity", "Todo entity", required=True),
            _field("max_items", "number", "Max items", min=1, max=20),
            _field("show_completed", "bool", "Show completed", default=False),
        ],
    },
    "chart": {
        "label": "History chart",
        "fields": [
            _field("entities", "entity_list", "Entities (max 3)", required=True),
            _field("hours", "number", "Hours of history", default=24, min=1, max=168),
            _field("style", "select", "Style", options=["line", "area", "bar"], default="line"),
            _field("min", "number", "Y min"),
            _field("max", "number", "Y max"),
            _field("name", "text", "Name"),
        ],
    },
    "gauge": {
        "label": "Gauge",
        "fields": [
            _field("entity", "entity", "Entity", required=True),
            _field("min", "number", "Min", default=0),
            _field("max", "number", "Max", default=100),
            _field("name", "text", "Name"),
            _field("unit", "text", "Unit"),
            _field("color", "select", "Colour", options=_COLOR_OPTIONS),
        ],
    },
    "progress": {
        "label": "Progress bar",
        "fields": [
            _field("entity", "entity", "Entity", required=True),
            _field("min", "number", "Min", default=0),
            _field("max", "number", "Max", default=100),
            _field("name", "text", "Name"),
            _field("color", "select", "Colour", options=_COLOR_OPTIONS),
        ],
    },
    "image": {
        "label": "Image",
        "fields": [
            _field("url", "text", "Image URL", help="or use an entity below"),
            _field("entity", "entity", "Camera/image entity"),
            _field("fit", "select", "Fit", options=["cover", "contain"], default="cover"),
        ],
    },
}

# Screen-level fields shared by the editor (widget-independent).
SCREEN_FIELDS: Final[list[dict[str, Any]]] = [
    _field("background", "select", "Background", options=_COLOR_OPTIONS, default="white"),
    _field("accent", "select", "Accent", options=_COLOR_OPTIONS, default="red"),
    _field("padding", "number", "Padding (px)", default=32, min=0, max=200),
    _field("show_header", "bool", "Show header", default=True),
    _field("interval", "number", "Playlist interval (s)", default=1800, min=300),
    _field("enabled", "bool", "In playlist rotation", default=True),
]

PICTURE_FIELDS: Final[list[dict[str, Any]]] = [
    _field("url", "text", "Image URL", help="e.g. a dashboard-screenshot add-on URL"),
    _field("entity", "entity", "Camera/image entity", help="alternative to a URL"),
    _field(
        "fit", "select", "Fit", options=["cover", "contain", "contain_black", "stretch"]
    ),
    _field(
        "mode",
        "select",
        "Dither mode",
        options=["auto", "none", "bayer", "floyd_steinberg", "atkinson"],
    ),
]
