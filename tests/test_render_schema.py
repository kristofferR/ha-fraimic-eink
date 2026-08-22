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
    assert result["interval"] == 6 * 3600
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
        schema.SCREEN_SCHEMA(_minimal(widgets=[{"type": "clock", "slot": "top_left"}]))


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


def test_picture_screen_accepts_official_mode() -> None:
    result = schema.SCREEN_SCHEMA(
        {"kind": "picture", "url": "https://example.com/art.jpg", "mode": "official"}
    )
    assert result["mode"] == "official"


def test_picture_slide_accepts_library_reference() -> None:
    data = schema.SCREEN_SCHEMA(
        {"kind": "picture", "library_image": "image-1", "fit": "contain"}
    )
    slide = schema.screen_from_dict(data, "slide-1")
    assert slide.source == {
        "library_image": "image-1",
        "fit": "contain",
        "caption": False,
    }


def test_library_reference_is_exclusive_to_picture_source() -> None:
    with pytest.raises(vol.Invalid, match="exactly one"):
        schema.SCREEN_SCHEMA(
            {
                "kind": "picture",
                "library_image": "image-1",
                "url": "https://example.com/art.jpg",
            }
        )
    with pytest.raises(vol.Invalid, match="only valid"):
        schema.SCREEN_SCHEMA(_minimal(library_image="image-1"))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider_item", "art-1"),
        ("query", "flowers"),
        ("caption", True),
        ("fit", "cover"),
        ("tone", "balanced"),
        ("crop", [0, 0, 1, 1]),
        ("mode", "auto"),
        ("metadata", {"title": "Art"}),
    ],
)
def test_dashboard_rejects_picture_only_fields(field: str, value: object) -> None:
    with pytest.raises(vol.Invalid, match="only valid"):
        schema.SCREEN_SCHEMA(_minimal(**{field: value}))


def test_provider_item_requires_a_specific_provider() -> None:
    with pytest.raises(vol.Invalid, match="specific provider"):
        schema.SCREEN_SCHEMA(
            {"kind": "picture", "provider": "shuffle", "provider_item": "art-1"}
        )


@pytest.mark.parametrize(
    "crop",
    ([0.8, 0.2, 0.4, 0.9], [0, 0, 0.001, 1], [-0.1, 0, 1, 1]),
)
def test_picture_crop_must_be_ordered_and_normalized(crop: list[float]) -> None:
    with pytest.raises((vol.Invalid, ValueError), match="crop"):
        schema.SCREEN_SCHEMA(
            {"kind": "picture", "library_image": "image-1", "crop": crop}
        )


def test_empty_query_still_requires_a_provider() -> None:
    with pytest.raises(vol.Invalid, match="provider source"):
        schema.SCREEN_SCHEMA(
            {"kind": "picture", "url": "https://example.com/a", "query": ""}
        )


def test_screen_from_dict_parses_windows() -> None:
    data = schema.SCREEN_SCHEMA(
        _minimal(
            windows=[{"after": "07:30", "before": "22:00", "days": ["mon", "sun"]}]
        )
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
