"""Frame-owned overlays and their palette-safe picture compositor."""

from __future__ import annotations

import asyncio
import copy
import logging
import uuid
from dataclasses import replace
from datetime import datetime
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN, PALETTE_NAMES
from .render.context import RenderContext
from .render.fetch import async_build_context
from .render.layout import Rect
from .render.schema import WIDGET_OPTION_SCHEMAS, ScreenConfig, WidgetConfig
from .render.svg import SvgDoc, rasterize, snap_to_colors
from .render.theme import PALETTE_HEX, Theme
from .render.widgets import WIDGET_REGISTRY
from .render.widgets.base import render_error

DATA_OVERLAYS = "overlays"
STORE_KEY = f"{DOMAIN}_overlays"
STORE_VERSION = 1
GRID_COLUMNS = 12
GRID_ROWS = 8

OVERLAY_TYPES = (
    "clock",
    "date",
    "todo",
    "agenda",
    "weather",
    "stat",
    "entities",
    "chart",
    "gauge",
    "text",
    "caption",
)
ANCHORS = (
    "top_left",
    "top",
    "top_right",
    "left",
    "center",
    "right",
    "bottom_left",
    "bottom",
    "bottom_right",
)
SIZES = ("s", "m", "l")
PLATES = ("none", "panel", "outline")
VISIBILITY_MODES = ("always", "times", "condition")

_LOGGER = logging.getLogger(__name__)

_TYPE_TO_WIDGET = {
    "clock": "clock",
    "date": "date",
    "todo": "todo",
    "agenda": "calendar",
    "weather": "weather_current",
    "stat": "stat",
    "entities": "entities",
    "chart": "chart",
    "gauge": "gauge",
    "text": "template",
    "caption": "template",
}
_DEFAULT_GEOMETRY = {
    "clock": ("top_left", "s"),
    "date": ("top_left", "s"),
    "todo": ("bottom_right", "l"),
    "agenda": ("right", "l"),
    "weather": ("bottom_left", "m"),
    "stat": ("top_right", "s"),
    "entities": ("right", "m"),
    "chart": ("bottom", "l"),
    "gauge": ("bottom_right", "m"),
    "text": ("bottom", "m"),
    "caption": ("bottom_left", "m"),
}
_SIZE_CELLS = {"s": (3, 1), "m": (5, 2), "l": (5, 3)}


def _optional_string(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _normalize_visibility(raw: Any) -> dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    mode = data.get("mode") if data.get("mode") in VISIBILITY_MODES else "always"
    days = [
        day
        for day in data.get("days", [])
        if day in {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
    ]
    return {
        "mode": mode,
        "from": str(data.get("from", "00:00")),
        "to": str(data.get("to", "23:59")),
        "days": days,
        "entity": _optional_string(data.get("entity")),
        "state": str(data.get("state", "on")),
        "hide_when_empty": data.get("hide_when_empty", True) is not False,
    }


def _widget_options(overlay_type: str, raw: Any) -> dict[str, Any]:
    options = copy.deepcopy(raw) if isinstance(raw, dict) else {}
    widget_type = _TYPE_TO_WIDGET[overlay_type]
    weather_view = None
    if overlay_type == "weather":
        weather_view = options.pop("view", "current")
        widget_type = (
            "weather_forecast" if weather_view == "forecast" else "weather_current"
        )
    if overlay_type == "caption":
        return {
            "fields": [
                field
                for field in options.get("fields", ["title", "artist", "source"])
                if field in {"title", "artist", "source", "year"}
            ]
        }
    schema = WIDGET_OPTION_SCHEMAS[widget_type]
    try:
        validated = schema(options)
        if weather_view is not None:
            validated["view"] = weather_view
        return validated
    except vol.Invalid as err:
        raise ValueError(f"Invalid {overlay_type} options: {err}") from err


def normalize_overlay(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise TypeError("Each overlay must be an object")
    overlay_type = raw.get("type")
    if overlay_type not in OVERLAY_TYPES:
        raise ValueError("Unknown overlay type")
    default_anchor, default_size = _DEFAULT_GEOMETRY[overlay_type]
    anchor = raw.get("anchor") if raw.get("anchor") in ANCHORS else default_anchor
    size = raw.get("size") if raw.get("size") in SIZES else default_size
    default_w, default_h = _SIZE_CELLS[size]

    def grid_value(key: str, default: int, maximum: int) -> int:
        value = raw.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{key} must be an integer grid coordinate")
        return min(maximum, max(0, value))

    w = grid_value("w", default_w, GRID_COLUMNS)
    h = grid_value("h", default_h, GRID_ROWS)
    x, y = _anchor_origin(anchor, w, h)
    x = grid_value("x", x, GRID_COLUMNS - 1)
    y = grid_value("y", y, GRID_ROWS - 1)
    w = min(w, GRID_COLUMNS - x)
    h = min(h, GRID_ROWS - y)
    return {
        "id": raw.get("id") if isinstance(raw.get("id"), str) else uuid.uuid4().hex,
        "type": overlay_type,
        "enabled": raw.get("enabled", True) is not False,
        "options": _widget_options(overlay_type, raw.get("options")),
        "anchor": anchor,
        "size": size,
        "x": x,
        "y": y,
        "w": max(1, w),
        "h": max(1, h),
        "plate": raw.get("plate") if raw.get("plate") in PLATES else "panel",
        "plate_color": (
            raw.get("plate_color")
            if raw.get("plate_color") in PALETTE_NAMES
            else "white"
        ),
        "text_size": raw.get("text_size") if raw.get("text_size") in SIZES else "m",
        "visibility": _normalize_visibility(raw.get("visibility")),
    }


def _anchor_origin(anchor: str, w: int, h: int) -> tuple[int, int]:
    columns = {
        "left": 0,
        "center": (GRID_COLUMNS - w) // 2,
        "right": GRID_COLUMNS - w,
    }
    rows = {
        "top": 0,
        "center": (GRID_ROWS - h) // 2,
        "bottom": GRID_ROWS - h,
    }
    horizontal = "center"
    vertical = "center"
    if "left" in anchor:
        horizontal = "left"
    elif "right" in anchor:
        horizontal = "right"
    if "top" in anchor:
        vertical = "top"
    elif "bottom" in anchor:
        vertical = "bottom"
    return columns[horizontal], rows[vertical]


def overlay_preset(name: str, entities: dict[str, list[str]]) -> list[dict[str, Any]]:
    todo = next(iter(entities.get("todo", [])), "todo.todo")
    weather = next(iter(entities.get("weather", [])), "weather.home")
    calendar = next(iter(entities.get("calendar", [])), "calendar.home")
    sensor = next(iter(entities.get("sensor", [])), "sensor.temperature")
    presets: dict[str, list[dict[str, Any]]] = {
        "clock": [{"type": "clock", "options": {"format": "%H:%M"}}],
        "todo": [{"type": "todo", "options": {"entity": todo, "max_items": 6}}],
        "info": [
            {"type": "clock", "anchor": "bottom_left", "options": {"format": "%H:%M"}},
            {"type": "weather", "anchor": "bottom", "options": {"entity": weather}},
            {
                "type": "date",
                "anchor": "bottom_right",
                "options": {"format": "%a %-d %b"},
            },
        ],
        "side": [
            {
                "type": "agenda",
                "options": {"entities": [calendar], "days": 3, "max_events": 6},
            },
            {"type": "stat", "anchor": "top_right", "options": {"entity": sensor}},
        ],
        "caption": [
            {"type": "caption", "options": {"fields": ["title", "artist", "source"]}}
        ],
        "morning": [
            {
                "type": "clock",
                "anchor": "top_left",
                "size": "m",
                "options": {"format": "%H:%M"},
            },
            {
                "type": "weather",
                "anchor": "top_right",
                "size": "m",
                "options": {"entity": weather},
            },
            {
                "type": "agenda",
                "anchor": "bottom",
                "size": "l",
                "w": 10,
                "options": {"entities": [calendar], "days": 1, "max_events": 5},
            },
        ],
    }
    if name not in presets:
        raise ValueError("Unknown overlay preset")
    timed = name == "morning"
    result = []
    for raw in presets[name]:
        if timed:
            raw["visibility"] = {
                "mode": "times",
                "from": "06:00",
                "to": "09:00",
                "days": ["mon", "tue", "wed", "thu", "fri"],
            }
        result.append(normalize_overlay(raw))
    return result


class OverlayManager:
    """Persist one ordered overlay collection per frame."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.frames: dict[str, list[dict[str, Any]]] = {}
        self._store: Store[dict[str, Any]] = Store(hass, STORE_VERSION, STORE_KEY)
        self._lock = asyncio.Lock()

    async def async_setup(self) -> None:
        data = await self._store.async_load() or {}
        raw_frames = data.get("frames", {}) if isinstance(data, dict) else {}
        if not isinstance(raw_frames, dict):
            return
        for frame_id, raw_overlays in raw_frames.items():
            if not isinstance(frame_id, str) or not isinstance(raw_overlays, list):
                continue
            parsed = []
            for raw in raw_overlays:
                try:
                    parsed.append(normalize_overlay(raw))
                except (TypeError, ValueError) as err:
                    _LOGGER.warning("Ignoring invalid overlay on %s: %s", frame_id, err)
            self.frames[frame_id] = parsed

    def for_frame(self, frame_id: str) -> list[dict[str, Any]]:
        return copy.deepcopy(self.frames.get(frame_id, []))

    async def async_replace(
        self, frame_id: str, raw_overlays: list[Any]
    ) -> list[dict[str, Any]]:
        overlays = [normalize_overlay(raw) for raw in raw_overlays]
        ids = [overlay["id"] for overlay in overlays]
        if len(ids) != len(set(ids)):
            raise ValueError("Overlay ids must be unique")
        async with self._lock:
            self.frames[frame_id] = overlays
            await self._store.async_save({"frames": self.frames})
        return self.for_frame(frame_id)

    async def async_copy(self, source_id: str, target_id: str) -> list[dict[str, Any]]:
        copied = self.for_frame(source_id)
        for overlay in copied:
            overlay["id"] = uuid.uuid4().hex
        return await self.async_replace(target_id, copied)


def get_overlay_manager(hass: HomeAssistant) -> OverlayManager | None:
    return hass.data.get(DOMAIN, {}).get(DATA_OVERLAYS)


def overlay_entities(hass: HomeAssistant) -> dict[str, list[str]]:
    domains = ("todo", "weather", "calendar", "sensor", "binary_sensor")
    return {
        domain: sorted(state.entity_id for state in hass.states.async_all(domain))
        for domain in domains
    }


def _visible(hass: HomeAssistant, overlay: dict[str, Any], now: datetime) -> bool:
    if not overlay["enabled"]:
        return False
    visibility = overlay["visibility"]
    mode = visibility["mode"]
    if mode == "condition":
        entity_id = visibility.get("entity")
        state = hass.states.get(entity_id) if entity_id else None
        return state is not None and state.state == visibility.get("state")
    if mode != "times":
        return True
    days = visibility.get("days") or []
    if (
        days
        and ("mon", "tue", "wed", "thu", "fri", "sat", "sun")[now.weekday()] not in days
    ):
        return False
    current = now.strftime("%H:%M")
    start, end = visibility.get("from", "00:00"), visibility.get("to", "23:59")
    return (
        start <= current <= end if start <= end else current >= start or current <= end
    )


def _caption_text(options: dict[str, Any], art: dict[str, Any] | None) -> str:
    if not art:
        return ""
    values = {
        "title": art.get("title"),
        "artist": art.get("artist"),
        "source": art.get("source_name") or art.get("provider"),
        "year": art.get("year"),
    }
    return " · ".join(
        str(values[field]) for field in options["fields"] if values.get(field)
    )


def _render_specs(
    overlays: list[dict[str, Any]], art: dict[str, Any] | None
) -> tuple[list[dict[str, Any]], ScreenConfig]:
    specs: list[dict[str, Any]] = []
    widgets: list[WidgetConfig] = []
    for overlay in overlays:
        widget_type = _TYPE_TO_WIDGET[overlay["type"]]
        options = copy.deepcopy(overlay["options"])
        if overlay["type"] == "weather":
            widget_type = (
                "weather_forecast"
                if options.pop("view", "current") == "forecast"
                else "weather_current"
            )
        elif overlay["type"] == "caption":
            caption = _caption_text(options, art)
            if not caption:
                continue
            options = {"template": caption, "align": "left", "size": "m"}
        specs.append(overlay)
        widgets.append(WidgetConfig(widget_type, "main", options))
    return specs, ScreenConfig(
        screen_id="frame_overlays",
        name="Overlays",
        layout="full",
        widgets=tuple(widgets),
        show_header=False,
    )


def _empty_payload(data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    for key in ("rows", "events", "items", "forecast"):
        if key in data:
            return not bool(data[key])
    return False


def _render_overlay_png(
    base_png: bytes,
    specs: list[dict[str, Any]],
    screen: ScreenConfig,
    ctx: RenderContext,
    width: int,
    height: int,
) -> bytes:
    doc = SvgDoc(width, height, PALETTE_HEX["black"])
    doc.image(base_png, 0, 0, width, height)
    doc.colors.update(PALETTE_HEX.values())
    cell_w, cell_h = width / GRID_COLUMNS, height / GRID_ROWS
    for index in reversed(range(len(specs))):
        overlay = specs[index]
        data = ctx.widget_data.get(index)
        if overlay["visibility"].get("hide_when_empty") and _empty_payload(data):
            continue
        x = round(overlay["x"] * cell_w)
        y = round(overlay["y"] * cell_h)
        w = round(overlay["w"] * cell_w)
        h = round(overlay["h"] * cell_h)
        color = PALETTE_HEX[overlay["plate_color"]]
        plate = overlay["plate"]
        stroke = max(2, round(min(width, height) / 600))
        if plate == "panel":
            doc.rect(x, y, w, h, color)
        elif plate == "outline":
            doc.rect(x, y, w, stroke, color)
            doc.rect(x, y + h - stroke, w, stroke, color)
            doc.rect(x, y, stroke, h, color)
            doc.rect(x + w - stroke, y, stroke, h, color)
        pad = max(8, round(min(width, height) / 75))
        rect = Rect(x + pad, y + pad, max(1, w - pad * 2), max(1, h - pad * 2))
        theme = Theme.for_screen(
            width,
            height,
            background=overlay["plate_color"],
            accent="red",
            padding=0,
            show_header=False,
        )
        scale = {"s": 0.8, "m": 1.0, "l": 1.25}[overlay["text_size"]]
        theme = replace(
            theme,
            display=round(theme.display * scale),
            value=round(theme.value * scale),
            title=round(theme.title * scale),
            body=round(theme.body * scale),
            small=round(theme.small * scale),
            label=round(theme.label * scale),
            icon=round(theme.icon * scale),
        )
        renderer = WIDGET_REGISTRY.get(screen.widgets[index].type)
        try:
            if renderer is None:
                render_error(doc, rect, "Unknown overlay", theme)
            else:
                renderer(
                    doc,
                    rect,
                    screen.widgets[index].options,
                    data,
                    ctx,
                    theme,
                )
        except Exception:
            _LOGGER.exception("Overlay %s could not render", overlay["id"])
            render_error(doc, rect, "Overlay unavailable", theme)
    return snap_to_colors(rasterize(doc.to_string(), width, height), doc.colors)


async def async_apply_frame_overlays(
    hass: HomeAssistant,
    entry,
    base_png: bytes,
    art: dict[str, Any] | None,
) -> tuple[bytes, int]:
    manager = get_overlay_manager(hass)
    if manager is None:
        return base_png, 0
    now = dt_util.now()
    overlays = [
        overlay
        for overlay in manager.for_frame(entry.entry_id)
        if _visible(hass, overlay, now)
    ]
    if not overlays:
        return base_png, 0
    specs, screen = _render_specs(overlays, art)
    if not specs:
        return base_png, 0
    ctx = await async_build_context(hass, screen)
    from .render.display import viewed_size

    width, height = viewed_size(entry)
    try:
        rendered = await hass.async_add_executor_job(
            _render_overlay_png, base_png, specs, screen, ctx, width, height
        )
    except Exception as err:
        raise HomeAssistantError(f"Could not render frame overlays: {err}") from err
    return rendered, len(specs)
