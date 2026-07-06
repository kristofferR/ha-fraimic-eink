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
from datetime import timedelta
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


_NO_FETCH_WIDGETS = frozenset({"clock", "date"})
_WIDGET_FETCHERS: dict[str, WidgetFetcher] = {
    "stat": _async_fetch_stat,
    "entities": _async_fetch_entities,
    "template": _async_fetch_template,
}
