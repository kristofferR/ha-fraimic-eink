"""Config-subentry flow: create and reconfigure dashboard screens in the UI.

Flow shape (TRMNL-style): one form for the screen basics (name, layout,
colours, rotation interval / time window), then for each slot of the chosen
layout a widget-type picker followed by that widget's options form. Picking
"picture" as the layout short-circuits to a single source form instead.

The stored subentry ``data`` is exactly the ``fraimic.render_screen`` service
payload shape (flat widgets), validated by the same SCREEN_SCHEMA.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigSubentryFlow, SubentryFlowResult
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    IconSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TemplateSelector,
    TextSelector,
    TimeSelector,
)

from .const import (
    DEFAULT_SCREEN_INTERVAL,
    DITHER_MODES,
    FIT_MODES,
    MIN_SCREEN_INTERVAL,
    PROVIDER_SHUFFLE,
)
from .providers import PROVIDERS
from .render.layout import LAYOUT_SLOTS
from .render.schema import DAYS, SCREEN_SCHEMA

PICTURE = "picture"
WIDGET_NONE = "none"

_LAYOUT_OPTIONS = [
    SelectOptionDict(value="full", label="Full screen — 1 widget"),
    SelectOptionDict(value="half_horizontal", label="Split top / bottom — 2 widgets"),
    SelectOptionDict(value="half_vertical", label="Split left / right — 2 widgets"),
    SelectOptionDict(value="quadrant", label="Quadrants — 4 widgets"),
    SelectOptionDict(value=PICTURE, label="Picture — one full-bleed image / URL"),
]
_COLOR_OPTIONS = [
    SelectOptionDict(value=name, label=name.capitalize())
    for name in ("white", "black", "red", "blue", "green", "yellow")
]
_WIDGET_OPTIONS = [
    SelectOptionDict(value=WIDGET_NONE, label="Leave empty"),
    SelectOptionDict(value="clock", label="Clock"),
    SelectOptionDict(value="date", label="Date"),
    SelectOptionDict(value="stat", label="Stat — one big value"),
    SelectOptionDict(value="entities", label="Entity list"),
    SelectOptionDict(value="template", label="Template text"),
    SelectOptionDict(value="weather_current", label="Weather — current"),
    SelectOptionDict(value="weather_forecast", label="Weather — forecast"),
    SelectOptionDict(value="calendar", label="Calendar agenda"),
    SelectOptionDict(value="todo", label="Todo list"),
    SelectOptionDict(value="chart", label="History chart"),
    SelectOptionDict(value="gauge", label="Gauge"),
    SelectOptionDict(value="progress", label="Progress bar"),
    SelectOptionDict(value="image", label="Image / camera"),
]
_DAY_OPTIONS = [
    SelectOptionDict(value=day, label=label)
    for day, label in zip(
        DAYS, ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
    )
]


def _select(options: list[SelectOptionDict], multiple: bool = False) -> SelectSelector:
    return SelectSelector(
        SelectSelectorConfig(
            options=options, multiple=multiple, mode=SelectSelectorMode.DROPDOWN
        )
    )


def _simple_select(*values: str) -> SelectSelector:
    return _select([SelectOptionDict(value=v, label=v.replace("_", " ")) for v in values])


def _number(minimum: float, maximum: float, step: float = 1) -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=minimum, max=maximum, step=step, mode=NumberSelectorMode.BOX
        )
    )


# Per-widget-type option forms. Field names match the (flat) widget schema in
# render/schema.py, so the collected input IS the stored widget dict.
WIDGET_FORMS: dict[str, vol.Schema] = {
    "clock": vol.Schema({vol.Optional("format"): TextSelector()}),
    "date": vol.Schema({vol.Optional("format"): TextSelector()}),
    "stat": vol.Schema(
        {
            vol.Required("entity"): EntitySelector(),
            vol.Optional("name"): TextSelector(),
            vol.Optional("icon"): IconSelector(),
            vol.Optional("unit"): TextSelector(),
            vol.Optional("precision"): _number(0, 3),
            vol.Optional("trend", default=False): BooleanSelector(),
            vol.Optional("trend_hours"): _number(1, 48),
            vol.Optional("color"): _select(_COLOR_OPTIONS),
        }
    ),
    "entities": vol.Schema(
        {
            vol.Required("entities"): EntitySelector(EntitySelectorConfig(multiple=True)),
            vol.Optional("max_rows"): _number(1, 30),
        }
    ),
    "template": vol.Schema(
        {
            vol.Required("template"): TemplateSelector(),
            vol.Optional("align"): _simple_select("left", "center"),
            vol.Optional("size"): _simple_select("s", "m", "l"),
        }
    ),
    "weather_current": vol.Schema(
        {
            vol.Required("entity"): EntitySelector(EntitySelectorConfig(domain="weather")),
            vol.Optional("name"): TextSelector(),
        }
    ),
    "weather_forecast": vol.Schema(
        {
            vol.Required("entity"): EntitySelector(EntitySelectorConfig(domain="weather")),
            vol.Optional("mode"): _simple_select("daily", "hourly"),
            vol.Optional("count"): _number(1, 8),
        }
    ),
    "calendar": vol.Schema(
        {
            vol.Required("entities"): EntitySelector(
                EntitySelectorConfig(domain="calendar", multiple=True)
            ),
            vol.Optional("days"): _number(1, 14),
            vol.Optional("max_events"): _number(1, 20),
        }
    ),
    "todo": vol.Schema(
        {
            vol.Required("entity"): EntitySelector(EntitySelectorConfig(domain="todo")),
            vol.Optional("max_items"): _number(1, 20),
            vol.Optional("show_completed", default=False): BooleanSelector(),
        }
    ),
    "chart": vol.Schema(
        {
            vol.Required("entities"): EntitySelector(EntitySelectorConfig(multiple=True)),
            vol.Optional("hours"): _number(1, 168),
            vol.Optional("style"): _simple_select("line", "area", "bar"),
            vol.Optional("min"): _number(-100000, 100000, 0.1),
            vol.Optional("max"): _number(-100000, 100000, 0.1),
            vol.Optional("name"): TextSelector(),
        }
    ),
    # Thresholds are YAML/service-only for now — a list-of-objects field has
    # no good selector; the service payload supports them fully.
    "gauge": vol.Schema(
        {
            vol.Required("entity"): EntitySelector(),
            vol.Optional("min"): _number(-100000, 100000, 0.1),
            vol.Optional("max"): _number(-100000, 100000, 0.1),
            vol.Optional("name"): TextSelector(),
            vol.Optional("unit"): TextSelector(),
            vol.Optional("color"): _select(_COLOR_OPTIONS),
        }
    ),
    "progress": vol.Schema(
        {
            vol.Required("entity"): EntitySelector(),
            vol.Optional("min"): _number(-100000, 100000, 0.1),
            vol.Optional("max"): _number(-100000, 100000, 0.1),
            vol.Optional("name"): TextSelector(),
            vol.Optional("color"): _select(_COLOR_OPTIONS),
        }
    ),
    "image": vol.Schema(
        {
            vol.Optional("url"): TextSelector(),
            vol.Optional("entity"): EntitySelector(
                EntitySelectorConfig(domain=["camera", "image"])
            ),
            vol.Optional("fit"): _simple_select("cover", "contain"),
        }
    ),
}

_BASICS_SCHEMA = vol.Schema(
    {
        vol.Required("name"): TextSelector(),
        vol.Required("layout", default="quadrant"): _select(_LAYOUT_OPTIONS),
        vol.Required("background", default="white"): _select(_COLOR_OPTIONS),
        vol.Required("accent", default="red"): _select(_COLOR_OPTIONS),
        vol.Required("show_header", default=True): BooleanSelector(),
        vol.Required("interval", default=DEFAULT_SCREEN_INTERVAL): _number(
            MIN_SCREEN_INTERVAL, 86400, 60
        ),
        vol.Optional("window_after"): TimeSelector(),
        vol.Optional("window_before"): TimeSelector(),
        vol.Optional("window_days", default=[]): _select(_DAY_OPTIONS, multiple=True),
        vol.Required("enabled", default=True): BooleanSelector(),
    }
)

_PROVIDER_OPTIONS = [
    SelectOptionDict(value=PROVIDER_SHUFFLE, label="Surprise me — random museum art"),
    *(
        SelectOptionDict(value=provider.key, label=provider.name)
        for provider in PROVIDERS.values()
    ),
]

_PICTURE_SCHEMA = vol.Schema(
    {
        vol.Optional("provider"): _select(_PROVIDER_OPTIONS),
        vol.Optional("query"): TextSelector(),
        vol.Optional("caption", default=False): BooleanSelector(),
        vol.Optional("url"): TextSelector(),
        vol.Optional("entity"): EntitySelector(
            EntitySelectorConfig(domain=["camera", "image"])
        ),
        vol.Optional("fit"): _simple_select(*FIT_MODES),
        vol.Optional("mode"): _simple_select(*DITHER_MODES),
    }
)


def _clean(user_input: dict[str, Any]) -> dict[str, Any]:
    """Drop empty values and collapse selector floats to ints where whole."""
    cleaned: dict[str, Any] = {}
    for key, value in user_input.items():
        if value in (None, "", []):
            continue
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        cleaned[key] = value
    return cleaned


def _hhmm(value: str) -> str:
    """TimeSelector emits HH:MM:SS; the screen schema wants HH:MM."""
    return value[:5]


def _schema_errors(err: vol.Invalid) -> dict[str, str]:
    """Map shared screen-schema failures back onto the current HA form."""
    field = str(err.path[-1]) if err.path else "base"
    if field in {"url", "format"}:
        return {field: "invalid_screen"}
    return {"base": "invalid_screen"}


class ScreenSubentryFlowHandler(ConfigSubentryFlow):
    """Create / reconfigure one dashboard screen."""

    def __init__(self) -> None:
        self._basics: dict[str, Any] = {}
        self._slots: list[str] = []
        self._slot_index = 0
        self._widgets: list[dict[str, Any]] = []
        self._current_type: str | None = None
        self._existing: dict[str, Any] = {}  # reconfigure: previous flat data

    # -- creation ---------------------------------------------------------

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        return await self._async_step_basics(user_input)

    # -- reconfigure ------------------------------------------------------

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        subentry = self._get_reconfigure_subentry()
        self._existing = dict(subentry.data)
        self._existing.setdefault("name", subentry.title)
        return await self._async_step_basics(user_input)

    # -- shared steps -----------------------------------------------------

    async def _async_step_basics(
        self, user_input: dict[str, Any] | None
    ) -> SubentryFlowResult:
        if user_input is not None:
            self._basics = _clean(user_input)
            if self._basics["layout"] == PICTURE:
                return await self.async_step_picture()
            self._slots = list(LAYOUT_SLOTS[self._basics["layout"]])
            self._slot_index = 0
            self._widgets = []
            return await self.async_step_widget()

        suggested = dict(self._existing)
        if suggested.get("kind") == "picture":
            suggested["layout"] = PICTURE
        for window in suggested.get("windows", [])[:1]:
            suggested["window_after"] = window.get("after")
            suggested["window_before"] = window.get("before")
            suggested["window_days"] = window.get("days", [])
        return self.async_show_form(
            step_id="user" if not self._existing else "reconfigure",
            data_schema=self.add_suggested_values_to_schema(_BASICS_SCHEMA, suggested),
        )

    async def async_step_picture(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            source = _clean(user_input)
            if len([k for k in ("url", "entity", "provider") if source.get(k)]) != 1:
                errors["base"] = "picture_source"
            elif (source.get("query") or source.get("caption")) and not source.get(
                "provider"
            ):
                errors["base"] = "provider_only_fields"
            else:
                return self._finish({"kind": "picture", **source})

        return self.async_show_form(
            step_id="picture",
            data_schema=self.add_suggested_values_to_schema(
                _PICTURE_SCHEMA, self._existing
            ),
            errors=errors,
        )

    async def async_step_widget(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if user_input is not None:
            wtype = user_input["type"]
            if wtype == WIDGET_NONE:
                return await self._advance_slot()
            self._current_type = wtype
            return await self.async_step_widget_options()

        slot = self._slots[self._slot_index]
        existing_widget = self._existing_widget(slot)
        return self.async_show_form(
            step_id="widget",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema({vol.Required("type", default=WIDGET_NONE): _select(_WIDGET_OPTIONS)}),
                {"type": existing_widget["type"]} if existing_widget else None,
            ),
            description_placeholders={
                "slot": slot.replace("_", " "),
                "position": f"{self._slot_index + 1}/{len(self._slots)}",
            },
        )

    async def async_step_widget_options(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        assert self._current_type is not None
        errors: dict[str, str] = {}
        slot = self._slots[self._slot_index]
        if user_input is not None:
            options = _clean(user_input)
            entities = options.get("entities")
            if self._current_type == "chart" and entities and len(entities) > 3:
                errors["entities"] = "too_many_series"
            elif self._current_type == "image" and (
                len([k for k in ("url", "entity") if options.get(k)]) != 1
            ):
                errors["base"] = "picture_source"
            else:
                self._widgets.append(
                    {"type": self._current_type, "slot": slot, **options}
                )
                return await self._advance_slot()

        existing_widget = self._existing_widget(slot)
        suggested = (
            {k: v for k, v in existing_widget.items() if k not in ("type", "slot")}
            if existing_widget and existing_widget["type"] == self._current_type
            else None
        )
        return self.async_show_form(
            step_id="widget_options",
            data_schema=self.add_suggested_values_to_schema(
                WIDGET_FORMS[self._current_type], suggested
            ),
            errors=errors,
            description_placeholders={
                "widget": self._current_type.replace("_", " "),
                "slot": slot.replace("_", " "),
            },
        )

    async def _advance_slot(self) -> SubentryFlowResult:
        next_index = self._slot_index + 1
        if next_index < len(self._slots):
            self._slot_index = next_index
            self._current_type = None
            return await self.async_step_widget()
        if not self._widgets:
            # Every slot left empty — go back to the first slot with an error.
            self._slot_index = 0
            return self.async_show_form(
                step_id="widget",
                data_schema=vol.Schema(
                    {vol.Required("type", default=WIDGET_NONE): _select(_WIDGET_OPTIONS)}
                ),
                errors={"base": "no_widgets"},
                description_placeholders={
                    "slot": self._slots[0].replace("_", " "),
                    "position": f"1/{len(self._slots)}",
                },
            )
        return self._finish(
            {"layout": self._basics["layout"], "widgets": self._widgets}
        )

    def _finish(self, body: dict[str, Any]) -> SubentryFlowResult:
        """Assemble, validate, and store the flat screen dict."""
        basics = self._basics
        data: dict[str, Any] = {
            "name": basics["name"],
            "background": basics.get("background", "white"),
            "accent": basics.get("accent", "red"),
            "show_header": basics.get("show_header", True),
            "interval": basics.get("interval", DEFAULT_SCREEN_INTERVAL),
            "enabled": basics.get("enabled", True),
            **body,
        }
        window: dict[str, Any] = {}
        if after := basics.get("window_after"):
            window["after"] = _hhmm(after)
        if before := basics.get("window_before"):
            window["before"] = _hhmm(before)
        if days := basics.get("window_days"):
            window["days"] = days
        if window:
            data["windows"] = [window]

        # Same validation as the service payload; by construction this passes,
        # but free-form URL/format fields can still fail the shared schema.
        try:
            SCREEN_SCHEMA(dict(data))
        except vol.Invalid as err:
            return self._show_schema_error(body, err)

        if self._existing:
            result = self.async_update_and_abort(
                self._get_entry(),
                self._get_reconfigure_subentry(),
                title=data["name"],
                data=data,
            )
            self._schedule_entry_reload()
            return result
        result = self.async_create_entry(title=data["name"], data=data)
        self._schedule_entry_reload()
        return result

    def _schedule_entry_reload(self) -> None:
        self.hass.config_entries.async_schedule_reload(self.handler[0])

    def _show_schema_error(
        self, body: dict[str, Any], err: vol.Invalid
    ) -> SubentryFlowResult:
        errors = _schema_errors(err)
        if body.get("kind") == PICTURE:
            return self.async_show_form(
                step_id="picture",
                data_schema=self.add_suggested_values_to_schema(
                    _PICTURE_SCHEMA,
                    {
                        key: body[key]
                        for key in ("url", "entity", "fit", "mode")
                        if key in body
                    },
                ),
                errors=errors,
            )
        if self._current_type is not None and self._slot_index < len(self._slots):
            slot = self._slots[self._slot_index]
            existing_widget = self._existing_widget(slot)
            current_widget = next(
                (
                    widget
                    for widget in reversed(self._widgets)
                    if widget.get("slot") == slot
                    and widget.get("type") == self._current_type
                ),
                None,
            )
            source_widget = current_widget or existing_widget
            suggested = (
                {k: v for k, v in source_widget.items() if k not in ("type", "slot")}
                if source_widget and source_widget["type"] == self._current_type
                else None
            )
            return self.async_show_form(
                step_id="widget_options",
                data_schema=self.add_suggested_values_to_schema(
                    WIDGET_FORMS[self._current_type], suggested
                ),
                errors=errors,
                description_placeholders={
                    "widget": self._current_type.replace("_", " "),
                    "slot": slot.replace("_", " "),
                },
            )
        return self.async_show_form(
            step_id="user" if not self._existing else "reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                _BASICS_SCHEMA, self._basics
            ),
            errors=errors,
        )

    def _existing_widget(self, slot: str) -> dict[str, Any] | None:
        for widget in self._existing.get("widgets", []):
            if isinstance(widget, dict) and widget.get("slot") == slot:
                return widget
        return None
