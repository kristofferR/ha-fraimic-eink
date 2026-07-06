"""Tests for the screen definition schema (pure, no Home Assistant).

Run:  uv run --with pillow --with numpy --with voluptuous --with resvg-py --with pytest pytest
"""

from __future__ import annotations

import pytest
import voluptuous as vol
from conftest import load

schema = load("render.schema")


def _minimal(**overrides) -> dict:
    data = {
        "layout": "full",
        "widgets": [{"type": "clock", "slot": "main"}],
    }
    data.update(overrides)
    return data


def test_minimal_screen_normalises_with_defaults() -> None:
    result = schema.SCREEN_SCHEMA(_minimal())
    assert result["name"] == "Dashboard"
    assert result["background"] == "white"
    assert result["accent"] == "red"
    assert result["interval"] == 1800
    widget = result["widgets"][0]
    assert widget == {"type": "clock", "slot": "main", "options": {"format": "%H:%M"}}


def test_widget_options_are_split_and_validated() -> None:
    result = schema.SCREEN_SCHEMA(
        _minimal(
            widgets=[
                {
                    "type": "stat",
                    "slot": "main",
                    "entity": "sensor.outdoor_temperature",
                    "trend": True,
                }
            ]
        )
    )
    options = result["widgets"][0]["options"]
    assert options["entity"] == "sensor.outdoor_temperature"
    assert options["trend"] is True
    assert options["trend_hours"] == 1  # default applied


def test_slot_must_match_layout() -> None:
    with pytest.raises(vol.Invalid, match="not valid for layout"):
        schema.SCREEN_SCHEMA(
            _minimal(widgets=[{"type": "clock", "slot": "top_left"}])
        )


def test_duplicate_slot_rejected() -> None:
    with pytest.raises(vol.Invalid, match="more than one widget"):
        schema.SCREEN_SCHEMA(
            _minimal(
                layout="half_vertical",
                widgets=[
                    {"type": "clock", "slot": "left"},
                    {"type": "date", "slot": "left"},
                ],
            )
        )


def test_unknown_widget_type_rejected() -> None:
    with pytest.raises(vol.Invalid, match="unknown widget type"):
        schema.SCREEN_SCHEMA(_minimal(widgets=[{"type": "sparkline", "slot": "main"}]))


def test_seconds_in_clock_format_rejected() -> None:
    with pytest.raises(vol.Invalid, match="%S"):
        schema.SCREEN_SCHEMA(
            _minimal(widgets=[{"type": "clock", "slot": "main", "format": "%H:%M:%S"}])
        )


def test_bad_entity_id_rejected() -> None:
    with pytest.raises(vol.Invalid):
        schema.SCREEN_SCHEMA(
            _minimal(widgets=[{"type": "stat", "slot": "main", "entity": "not an id"}])
        )


def test_interval_floor_enforced() -> None:
    with pytest.raises(vol.Invalid):
        schema.SCREEN_SCHEMA(_minimal(interval=60))


def test_screen_from_dict_parses_windows() -> None:
    data = schema.SCREEN_SCHEMA(
        _minimal(windows=[{"after": "07:30", "before": "22:00", "days": ["mon", "sun"]}])
    )
    screen = schema.screen_from_dict(data, "test")
    assert screen.screen_id == "test"
    window = screen.windows[0]
    assert (window.after.hour, window.after.minute) == (7, 30)
    assert window.days == frozenset({0, 6})
    assert screen.widgets[0].type == "clock"


def test_bad_window_time_rejected() -> None:
    with pytest.raises(vol.Invalid):
        schema.SCREEN_SCHEMA(_minimal(windows=[{"after": "25:00"}]))
