"""Diagnostics from a fully loaded entry must not leak network identifiers."""

from __future__ import annotations

import json
import re

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fraimic.diagnostics import async_get_config_entry_diagnostics

from .conftest import DEVICE_KEY, HOST

MAC_RE = re.compile(r"(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}")


async def test_diagnostics_redact_network_identifiers(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    assert loaded_entry.state is ConfigEntryState.LOADED

    result = await async_get_config_entry_diagnostics(hass, loaded_entry)
    dumped = json.dumps(result)

    assert not MAC_RE.search(dumped)
    assert HOST not in dumped
    assert "HomeNet" not in dumped
    assert DEVICE_KEY not in dumped
    wifi = result["data"]["wifi"]
    assert wifi["ssid"] == wifi["ip"] == wifi["mac"] == "**REDACTED**"
    # Non-identifying data survives redaction.
    assert result["data"]["battery"]["percent"] == 81
    assert result["entry"]["resolution"] == [1600, 1200]
    assert result["logs"]["current"] == [
        "wifi: connected to **REDACTED**, ip **REDACTED**, mac **REDACTED**"
    ]
