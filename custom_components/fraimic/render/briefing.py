"""Bounded, display-neutral briefing snapshots supplied by ordinary HA entities."""

from __future__ import annotations

import math
from datetime import datetime

import voluptuous as vol


def _text(value):
    if not isinstance(value, str) or len(value) > 240:
        raise vol.Invalid("Expected text of at most 240 characters")
    return value.strip()


def _finite(value):
    number = float(value)
    if not math.isfinite(number):
        raise vol.Invalid("Expected a finite number")
    return number


_ICON = vol.All(str, vol.Length(max=80))
_COLOR = vol.In(("blue", "green", "yellow", "red"))
_ITEM = vol.Schema(
    {
        vol.Required("title"): _text,
        vol.Optional("icon", default="mdi:checkbox-blank-outline"): _ICON,
    }
)
_AGENDA = vol.Schema(
    {
        vol.Required("title"): _text,
        vol.Optional("time", default=""): _text,
        vol.Optional("all_day", default=False): bool,
        vol.Optional("icon", default="mdi:calendar-outline"): _ICON,
    }
)
_COUNT = vol.All(int, vol.Range(min=0, max=10000))
_SCHEMA = vol.Schema(
    {
        vol.Required("generated_at"): str,
        vol.Required("valid_until"): str,
        vol.Required("date_label"): _text,
        vol.Required("greeting"): _text,
        vol.Optional("locale", default="en"): vol.In(("en", "nb")),
        vol.Optional("agenda", default=list): vol.All([_AGENDA], vol.Length(max=3)),
        vol.Optional("tasks", default=list): vol.All([_ITEM], vol.Length(max=3)),
        vol.Optional("routine"): vol.Schema(
            {
                vol.Required("label"): _text,
                vol.Required("completed"): _COUNT,
                vol.Required("total"): vol.All(int, vol.Range(min=1, max=10000)),
                vol.Optional("skipped", default=0): _COUNT,
                vol.Optional("next_step", default=""): _text,
                vol.Optional("icon", default="mdi:format-list-checks"): _ICON,
            }
        ),
        vol.Optional("focus"): vol.Schema(
            {
                vol.Required("title"): _text,
                vol.Optional("label", default=""): _text,
                vol.Optional("detail", default=""): _text,
                vol.Optional("icon", default="mdi:bullseye-arrow"): _ICON,
                vol.Optional("color", default="blue"): _COLOR,
            }
        ),
        vol.Optional("progress", default=list): vol.All(
            [
                vol.Schema(
                    {
                        vol.Required("label"): _text,
                        vol.Required("value"): vol.All(
                            _finite, vol.Range(min=0, max=1000000)
                        ),
                        vol.Required("max"): vol.All(
                            _finite, vol.Range(min=0.001, max=1000000)
                        ),
                        vol.Optional("unit", default=""): _text,
                        vol.Optional("icon", default="mdi:check"): _ICON,
                        vol.Optional("color", default="green"): _COLOR,
                    }
                )
            ],
            vol.Length(max=3),
        ),
        vol.Optional("weather"): vol.Schema(
            {
                vol.Required("temperature"): vol.All(
                    _finite, vol.Range(min=-100, max=100)
                ),
                vol.Optional("unit", default="°C"): vol.In(("°C", "°F")),
                vol.Optional("icon", default="mdi:weather-partly-cloudy"): _ICON,
            }
        ),
    }
)


def validate_briefing(raw, now: datetime):
    """Omit expired/malformed snapshots, never render their content as current."""
    try:
        data = _SCHEMA(raw)
        generated = datetime.fromisoformat(data["generated_at"])
        expires = datetime.fromisoformat(data["valid_until"])
        if generated.tzinfo is None or expires.tzinfo is None:
            return None
        if not generated.timestamp() - 30 <= now.timestamp() < expires.timestamp():
            return None
        if not 0 < (expires - generated).total_seconds() <= 300:
            return None
        routine = data.get("routine")
        if routine and routine["completed"] + routine["skipped"] > routine["total"]:
            return None
        if not any(
            data.get(k)
            for k in ("agenda", "tasks", "routine", "focus", "progress", "weather")
        ):
            return None
        return data
    except (vol.Invalid, TypeError, ValueError, OverflowError):
        return None
