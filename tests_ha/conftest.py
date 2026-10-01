"""Fixtures for tests that load the integration into a real Home Assistant.

The frame is mocked at the ``FraimicClient`` boundary. Entry setup also
registers the sidebar panel, which needs the ``frontend`` component and its
``hass_frontend`` asset package; neither is relevant here, so ``frontend`` is
marked loaded and panel registration is patched out. The background catalog
warm-up is patched too: it calls museum APIs through aiodns, which
pytest-socket cannot block.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fraimic.api import FraimicClient
from custom_components.fraimic.const import (
    CONF_HEIGHT,
    CONF_POWER_MODE,
    CONF_WIDTH,
    DOMAIN,
    POWER_MODE_RESPONSIVE,
)

HOST = "192.168.1.50"
DEVICE_KEY = "fk_0123456789abcdef"
MAC = "1C:DB:D4:12:34:56"

# Flat firmware 0.2.28 shape, including every network identifier diagnostics
# must redact.
FRAME_INFO: dict[str, Any] = {
    "firmware_version": "0.2.28",
    "device_id": "canvas-1",
    "device_key": DEVICE_KEY,
    "display_type": "13.3in",
    "display_width": 1600,
    "display_height": 1200,
    "battery_pct": 81,
    "battery_voltage_mv": 3980,
    "charging": False,
    "wifi_connected": True,
    "wifi_ssid": "HomeNet",
    "wifi_rssi": -58,
    "ip_address": HOST,
    "mac_address": MAC,
    "bssid": "02:AA:BB:CC:DD:EE",
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """Let Home Assistant load custom_components/fraimic without a frontend."""
    hass.config.components.add("frontend")


@pytest.fixture
def frame_client() -> Generator[dict[str, AsyncMock]]:
    """Answer every read the integration makes of the frame."""
    mocks = {
        "get_info": AsyncMock(return_value=dict(FRAME_INFO)),
        "get_battery": AsyncMock(return_value={"battery_pct": 81}),
        "get_info_page": AsyncMock(return_value="<html></html>"),
        "get_logs": AsyncMock(
            return_value=(
                "<div class='log-area' id='logOutput'>"
                f"wifi: connected to HomeNet, ip {HOST}, mac {MAC}</div>"
            )
        ),
        "get_albums": AsyncMock(return_value=[]),
    }
    with patch.multiple(FraimicClient, **mocks):
        yield mocks


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """A configured 13.3-inch frame that polls on startup."""
    return MockConfigEntry(
        domain=DOMAIN,
        version=3,
        title=f"Fraimic E-Ink Canvas ({HOST})",
        unique_id=DEVICE_KEY,
        data={CONF_HOST: HOST, CONF_WIDTH: 1600, CONF_HEIGHT: 1200},
        options={CONF_POWER_MODE: POWER_MODE_RESPONSIVE},
    )


async def setup_entry(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Set an entry up through Home Assistant's real config-entry flow."""
    entry.add_to_hass(hass)
    with (
        patch("custom_components.fraimic.async_register_panel"),
        patch("custom_components.fraimic._async_warm_catalogs"),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


@pytest.fixture
async def loaded_entry(
    hass: HomeAssistant,
    frame_client: dict[str, AsyncMock],
    config_entry: MockConfigEntry,
) -> MockConfigEntry:
    """The default frame, fully set up."""
    await setup_entry(hass, config_entry)
    return config_entry
