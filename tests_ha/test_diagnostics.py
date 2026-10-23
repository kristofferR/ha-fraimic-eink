"""Diagnostics from a fully loaded entry must not leak network identifiers."""

from __future__ import annotations

import json
import re
from unittest.mock import AsyncMock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fraimic.const import CONF_CLOUD_EMAIL
from custom_components.fraimic.diagnostics import async_get_config_entry_diagnostics

from .conftest import DEVICE_KEY, HOST, setup_entry

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


async def test_diagnostics_scrub_credentials_from_frame_logs(
    hass: HomeAssistant,
    frame_client: dict[str, AsyncMock],
    config_entry: MockConfigEntry,
) -> None:
    """The album proxy logs its upstream path, which embeds the device key."""
    email = "owner@example.com"
    frame_client["get_logs"].return_value = (
        "<div class='log-area' id='logOutput'>"
        f"albums: GET /api/v1/albums/{DEVICE_KEY} -> 200\n"
        f"cloud: signed in as {email.upper()}</div>"
    )
    entry = MockConfigEntry(
        domain=config_entry.domain,
        version=config_entry.version,
        unique_id=DEVICE_KEY,
        data=dict(config_entry.data),
        options={**config_entry.options, CONF_CLOUD_EMAIL: email},
    )
    await setup_entry(hass, entry)

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["logs"]["current"] == [
        "albums: GET /api/v1/albums/**REDACTED** -> 200",
        "cloud: signed in as **REDACTED**",
    ]
