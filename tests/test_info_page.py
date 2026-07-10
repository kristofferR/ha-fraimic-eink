"""Tests for the /info HTML admin-page parser (pure module, no HA)."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "fraimic"


def _load():
    if "fraimic" not in sys.modules:
        pkg = types.ModuleType("fraimic")
        pkg.__path__ = [str(PKG_DIR)]
        sys.modules["fraimic"] = pkg
    name = "fraimic.info_page"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, PKG_DIR / "info_page.py")
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


info_page = _load()


def _row(label: str, value: str) -> str:
    return (
        f"<div class='info-row'><span class='info-label'>{label}</span>"
        f"<span class='info-value'>{value}</span></div>"
    )


# Structure copied from a real 13.3" frame on firmware 0.2.28.
REAL_SHAPE = (
    "<!DOCTYPE html><html><body><div class='container'>"
    "<div class='section'><div class='section-title'>Device</div>"
    + _row("Device Type", '13.3" E-Ink')
    + _row("MAC Address", "AA:BB:CC:DD:EE:FF")
    + _row("Firmware Version", "v0.2.28")
    + "</div><div class='section'><div class='section-title'>Power</div>"
    + _row("Voltage", "3.96 V")
    + _row("Percentage", "35%")
    + _row("Status", "<span class='status-badge status-green'>Charging</span>")
    + _row("Current", "2090 mA")
    + _row("Temperature", "25&deg;C")
    + _row("Cycles", "0")
    + _row("Health (SOH)", "100%")
    + _row("Data Source", "Fuel Gauge")
    + "</div><div class='section'><div class='section-title'>Network</div>"
    + _row("Status", "<span class='status-badge status-green'>Connected</span>")
    + _row("Signal (RSSI)", " -87 dBm")
    + "</div></div></body></html>"
)


def test_parses_real_page_shape():
    parsed = info_page.parse_info_page(REAL_SHAPE)
    assert parsed == {
        "panel_size_in": 13.3,
        "battery_cycles": 0,
        "battery_soh": 100.0,
        "battery_current_ma": 2090,
        "battery_temperature_c": 25.0,
    }


def test_large_panel_and_negative_current():
    page = (
        _row("Device Type", '31.5" E-Ink')
        + _row("Current", "-120 mA")
        + _row("Cycles", "42")
        + _row("Health (SOH)", "97%")
    )
    parsed = info_page.parse_info_page(page)
    assert parsed["panel_size_in"] == 31.5
    assert parsed["battery_current_ma"] == -120
    assert parsed["battery_cycles"] == 42
    assert parsed["battery_soh"] == 97.0


def test_every_field_optional():
    assert info_page.parse_info_page(_row("Device Type", '13.3" E-Ink')) == {
        "panel_size_in": 13.3
    }
    assert info_page.parse_info_page(_row("Cycles", "7")) == {"battery_cycles": 7}


def test_garbage_inputs():
    assert info_page.parse_info_page("") == {}
    assert info_page.parse_info_page("<html>nothing here</html>") == {}
    assert info_page.parse_info_page(None) == {}  # type: ignore[arg-type]
    # Unparsable values are dropped, not errors.
    assert info_page.parse_info_page(_row("Cycles", "many")) == {}


def test_duplicate_labels_are_dropped():
    # "Status" appears in both the Power and Network sections with different
    # values; anything ambiguous must not be guessed at.
    page = _row("Status", "Charging") + _row("Status", "Connected") + _row("Cycles", "3")
    parsed = info_page.parse_info_page(page)
    assert parsed == {"battery_cycles": 3}
