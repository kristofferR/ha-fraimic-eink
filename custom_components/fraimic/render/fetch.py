"""Gather Home Assistant data for every widget of a screen.

All HA access happens here, on the event loop, *before* the CPU-bound
SVG/raster step. Fetches run concurrently; a failed fetch yields an
``{"error": ...}`` payload so the widget renders a placeholder instead of
failing the screen.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import TemplateError
from homeassistant.helpers.template import Template
from homeassistant.util import dt as dt_util

from .context import RenderContext
from .schema import ScreenConfig, WidgetConfig
from .widgets import WIDGET_REGISTRY

_LOGGER = logging.getLogger(__name__)

UNKNOWN_DISPLAY = "—"
WidgetFetcher = Callable[
    [HomeAssistant, dict[str, Any], RenderContext],
    Awaitable[dict[str, Any] | None],
]

# Sensible default MDI icons by domain / device class when the entity has none.
_DOMAIN_ICONS = {
    "light": "mdi:lightbulb",
    "switch": "mdi:toggle-switch",
    "lock": "mdi:lock",
    "climate": "mdi:thermostat",
    "person": "mdi:account",
    "device_tracker": "mdi:account",
    "media_player": "mdi:speaker",
    "cover": "mdi:window-shutter",
    "fan": "mdi:fan",
    "vacuum": "mdi:robot-vacuum",
}
_DEVICE_CLASS_ICONS = {
    "temperature": "mdi:thermometer",
    "humidity": "mdi:water-percent",
    "battery": "mdi:battery",
    "power": "mdi:flash",
    "energy": "mdi:lightning-bolt",
    "illuminance": "mdi:brightness-5",
    "motion": "mdi:motion-sensor",
    "door": "mdi:door",
    "window": "mdi:window-closed",
    "moisture": "mdi:water",
    "co2": "mdi:molecule-co2",
    "pm25": "mdi:blur",
}


async def async_build_context(
    hass: HomeAssistant, screen: ScreenConfig
) -> RenderContext:
    """Fetch data for every widget of ``screen`` concurrently."""
    ctx = RenderContext(now=dt_util.now(), language=hass.config.language)
    results = await asyncio.gather(
        *(_async_fetch_widget(hass, widget, ctx) for widget in screen.widgets),
        return_exceptions=True,
    )
    for index, result in enumerate(results):
        if isinstance(result, BaseException):
            widget = screen.widgets[index]
            _LOGGER.warning(
                "Fetching data for widget %r (slot %r) failed: %s",
                widget.type,
                widget.slot,
                result,
            )
            ctx.widget_data[index] = {"error": str(result)}
        else:
            ctx.widget_data[index] = result
    return ctx


async def _async_fetch_widget(
    hass: HomeAssistant, widget: WidgetConfig, ctx: RenderContext
) -> dict[str, Any] | None:
    if widget.type in _NO_FETCH_WIDGETS:
        return None
    if widget.type not in WIDGET_REGISTRY:
        return {"error": f"Unknown widget type {widget.type!r}"}
    if fetcher := _WIDGET_FETCHERS.get(widget.type):
        return await fetcher(hass, widget.options, ctx)
    return {"error": f"No data fetcher registered for widget type {widget.type!r}"}


def _default_icon(state: State) -> str | None:
    if icon := state.attributes.get("icon"):
        return icon
    if device_class := state.attributes.get("device_class"):
        if icon := _DEVICE_CLASS_ICONS.get(device_class):
            return icon
    return _DOMAIN_ICONS.get(state.domain)


def _display_value(state: State | None, precision: int | None = None) -> str:
    """Human-friendly short state string (without unit)."""
    if state is None or state.state in ("unknown", "unavailable"):
        return UNKNOWN_DISPLAY
    value = state.state
    try:
        number = float(value)
    except ValueError:
        # Non-numeric: "on" -> "On", "not_home" -> "Not home".
        return value.replace("_", " ").capitalize()
    if precision is not None:
        return f"{number:.{precision}f}"
    return value


async def _async_fetch_stat(
    hass: HomeAssistant, options: dict[str, Any], ctx: RenderContext
) -> dict[str, Any]:
    entity_id = options["entity"]
    state = hass.states.get(entity_id)
    if state is None:
        return {"error": f"Entity {entity_id} not found"}
    payload: dict[str, Any] = {
        "value": _display_value(state, options.get("precision")),
        "name": state.attributes.get("friendly_name") or entity_id,
        "unit": state.attributes.get("unit_of_measurement"),
        "icon": _default_icon(state),
        "trend_delta": None,
    }
    if options.get("trend"):
        payload["trend_delta"] = await _async_trend_delta(
            hass, entity_id, state, options["trend_hours"], ctx
        )
    return payload


async def _async_trend_delta(
    hass: HomeAssistant, entity_id: str, state: State, hours: int, ctx: RenderContext
) -> float | None:
    """Change in a numeric state vs ~``hours`` ago, via recorder history."""
    if "recorder" not in hass.config.components:
        return None
    try:
        current = float(state.state)
    except ValueError:
        return None
    from homeassistant.components.recorder import get_instance, history

    start = dt_util.as_utc(ctx.now) - timedelta(hours=hours)
    try:
        past = await get_instance(hass).async_add_executor_job(
            lambda: history.state_changes_during_period(
                hass,
                start,
                start + timedelta(minutes=30),
                entity_id,
                no_attributes=True,
                limit=1,
                include_start_time_state=True,
            )
        )
    except Exception as err:  # noqa: BLE001 - trend is decoration, never fatal
        _LOGGER.debug("Trend lookup for %s failed: %s", entity_id, err)
        return None
    for past_state in past.get(entity_id, []):
        try:
            return round(current - float(past_state.state), 2)
        except ValueError:
            continue
    return None


async def _async_fetch_entities(
    hass: HomeAssistant, options: dict[str, Any], _ctx: RenderContext
) -> dict[str, Any]:
    return _fetch_entities(hass, options)


def _fetch_entities(hass: HomeAssistant, options: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for item in options["entities"]:
        if isinstance(item, str):
            item = {"entity": item}
        entity_id = item["entity"]
        state = hass.states.get(entity_id)
        if state is None:
            rows.append(
                {"name": entity_id, "value": UNKNOWN_DISPLAY, "icon": item.get("icon")}
            )
            continue
        value = _display_value(state)
        if value != UNKNOWN_DISPLAY and (
            unit := state.attributes.get("unit_of_measurement")
        ):
            value = f"{value} {unit}"
        rows.append(
            {
                "name": item.get("name")
                or state.attributes.get("friendly_name")
                or entity_id,
                "value": value,
                "icon": item.get("icon") or _default_icon(state),
            }
        )
    return {"rows": rows}


async def _async_fetch_template(
    hass: HomeAssistant, options: dict[str, Any], _ctx: RenderContext
) -> dict[str, Any]:
    try:
        text = Template(options["template"], hass).async_render(parse_result=False)
    except TemplateError as err:
        return {"error": f"Template error: {err}"}
    return {"text": str(text)}


async def _async_fetch_weather_current(
    hass: HomeAssistant, options: dict[str, Any], _ctx: RenderContext
) -> dict[str, Any]:
    return _fetch_weather_current(hass, options)


def _fetch_weather_current(
    hass: HomeAssistant, options: dict[str, Any]
) -> dict[str, Any]:
    entity_id = options["entity"]
    state = hass.states.get(entity_id)
    if state is None:
        return {"error": f"Entity {entity_id} not found"}
    if state.state in ("unknown", "unavailable"):
        return {"error": f"{entity_id} is {state.state}"}
    return {
        "condition": state.state,
        "temperature": state.attributes.get("temperature"),
        "unit": state.attributes.get("temperature_unit"),
        "name": state.attributes.get("friendly_name") or entity_id,
    }


async def _async_fetch_weather_forecast(
    hass: HomeAssistant, options: dict[str, Any], _ctx: RenderContext
) -> dict[str, Any]:
    entity_id = options["entity"]
    mode = options["mode"]
    response = await hass.services.async_call(
        "weather",
        "get_forecasts",
        {"type": mode},
        target={"entity_id": entity_id},
        blocking=True,
        return_response=True,
    )
    forecast = (response or {}).get(entity_id, {}).get("forecast") or []
    items = []
    for entry in forecast[: options["count"]]:
        when = dt_util.parse_datetime(str(entry.get("datetime", "")))
        if when is None:
            label = ""
        else:
            local = dt_util.as_local(when)
            label = local.strftime("%H") if mode == "hourly" else local.strftime("%a")
        items.append(
            {
                "label": label,
                "condition": entry.get("condition"),
                "temp": entry.get("temperature"),
                "templow": entry.get("templow"),
            }
        )
    if not items:
        return {"error": f"No {mode} forecast from {entity_id}"}
    return {"items": items}


def _day_label(when: datetime, now: datetime) -> str:
    day = when.date()
    if day == now.date():
        return "Today"
    if (day - now.date()).days == 1:
        return "Tomorrow"
    return when.strftime("%A %-d %B")


async def _async_fetch_calendar(
    hass: HomeAssistant, options: dict[str, Any], ctx: RenderContext
) -> dict[str, Any]:
    end = ctx.now + timedelta(days=options["days"])
    response = await hass.services.async_call(
        "calendar",
        "get_events",
        {"start_date_time": ctx.now.isoformat(), "end_date_time": end.isoformat()},
        target={"entity_id": options["entities"]},
        blocking=True,
        return_response=True,
    )
    events = []
    for calendar in (response or {}).values():
        for event in calendar.get("events", []):
            start_raw = str(event.get("start", ""))
            # All-day events carry a bare date — parse_datetime would happily
            # read it as midnight and the row would show a bogus "00:00".
            all_day = "T" not in start_raw
            if all_day:
                parsed = dt_util.parse_date(start_raw)
                if parsed is None:
                    continue
                local = dt_util.as_local(ctx.now).replace(
                    year=parsed.year, month=parsed.month, day=parsed.day,
                    hour=0, minute=0, second=0, microsecond=0,
                )
                time_label = ""
            else:
                start_dt = dt_util.parse_datetime(start_raw)
                if start_dt is None:
                    continue
                local = dt_util.as_local(start_dt)
                time_label = local.strftime("%H:%M")
            # An event already underway (multi-day, or started earlier today)
            # belongs under "Today", not its historic start date.
            label_at = dt_util.as_local(ctx.now) if local < ctx.now else local
            events.append(
                (
                    local.isoformat(),
                    {
                        "day": _day_label(label_at, ctx.now),
                        "time": time_label,
                        "title": event.get("summary", ""),
                    },
                )
            )
    events.sort(key=lambda pair: pair[0])
    limit = options.get("max_events") or 20
    return {"events": [event for _, event in events[:limit]]}


async def _async_fetch_todo(
    hass: HomeAssistant, options: dict[str, Any], _ctx: RenderContext
) -> dict[str, Any]:
    entity_id = options["entity"]
    statuses = ["needs_action"]
    if options["show_completed"]:
        statuses.append("completed")
    response = await hass.services.async_call(
        "todo",
        "get_items",
        {"status": statuses},
        target={"entity_id": entity_id},
        blocking=True,
        return_response=True,
    )
    raw_items = (response or {}).get(entity_id, {}).get("items") or []
    return {
        "items": [
            {"summary": item.get("summary", ""), "done": item.get("status") == "completed"}
            for item in raw_items
        ]
    }


async def _async_fetch_chart(
    hass: HomeAssistant, options: dict[str, Any], ctx: RenderContext
) -> dict[str, Any]:
    if "recorder" not in hass.config.components:
        return {"error": "Recorder is not available for history charts"}
    from homeassistant.components.recorder import get_instance, history

    hours = options["hours"]
    end = dt_util.as_utc(ctx.now)
    start = end - timedelta(hours=hours)
    entity_ids = options["entities"]
    try:
        states = await get_instance(hass).async_add_executor_job(
            lambda: history.get_significant_states(
                hass,
                start,
                end,
                entity_ids,
                significant_changes_only=False,
                no_attributes=True,
            )
        )
    except Exception as err:  # noqa: BLE001 - surfaced as a widget error
        return {"error": f"History lookup failed: {err}"}

    span = (end - start).total_seconds()
    series = []
    for entity_id in entity_ids:
        points: list[tuple[float, float]] = []
        for state in states.get(entity_id, []):
            try:
                value = float(state.state)
            except (ValueError, TypeError):
                continue
            frac = (state.last_updated - start).total_seconds() / span
            points.append((min(max(frac, 0.0), 1.0), value))
        if len(points) > 300:
            stride = len(points) // 300 + 1
            points = points[::stride]
        current = hass.states.get(entity_id)
        current_value = None
        if current is not None:
            try:
                current_value = float(current.state)
            except (ValueError, TypeError):
                current_value = None
        if current_value is not None:
            if not points:
                points = [(0.0, current_value), (1.0, current_value)]
            elif points[-1][0] >= 1.0:
                points[-1] = (1.0, current_value)
            else:
                points.append((1.0, current_value))
        name = (
            current.attributes.get("friendly_name") if current else None
        ) or entity_id
        series.append({"name": name, "points": points})

    time_fmt = "%H:%M" if hours <= 48 else "%-d %b"
    return {
        "series": series,
        "start_label": dt_util.as_local(start).strftime(time_fmt),
        "end_label": dt_util.as_local(end).strftime(time_fmt),
    }


async def _async_fetch_numeric(
    hass: HomeAssistant, options: dict[str, Any], _ctx: RenderContext
) -> dict[str, Any]:
    return _fetch_numeric(hass, options)


def _fetch_numeric(hass: HomeAssistant, options: dict[str, Any]) -> dict[str, Any]:
    """Shared fetch for gauge/progress: one numeric state.

    ``display`` excludes the unit — the renderers place the unit themselves
    (below the gauge value, appended by the progress bar).
    """
    entity_id = options["entity"]
    state = hass.states.get(entity_id)
    if state is None:
        return {"error": f"Entity {entity_id} not found"}
    payload: dict[str, Any] = {
        "display": _display_value(state),
        "name": state.attributes.get("friendly_name") or entity_id,
        "unit": state.attributes.get("unit_of_measurement"),
        "value": None,
    }
    try:
        payload["value"] = float(state.state)
    except ValueError:
        pass
    return payload


async def _async_fetch_image(
    hass: HomeAssistant, options: dict[str, Any], _ctx: RenderContext
) -> dict[str, Any]:
    from ..source import async_get_source_bytes

    raw = await async_get_source_bytes(
        hass,
        url=options.get("url"),
        entity_id=options.get("entity"),
        redact_url=True,
    )
    return {"bytes": raw}


_NO_FETCH_WIDGETS = frozenset({"clock", "date"})
_WIDGET_FETCHERS: dict[str, WidgetFetcher] = {
    "stat": _async_fetch_stat,
    "entities": _async_fetch_entities,
    "template": _async_fetch_template,
    "weather_current": _async_fetch_weather_current,
    "weather_forecast": _async_fetch_weather_forecast,
    "calendar": _async_fetch_calendar,
    "todo": _async_fetch_todo,
    "chart": _async_fetch_chart,
    "gauge": _async_fetch_numeric,
    "progress": _async_fetch_numeric,
    "image": _async_fetch_image,
}
