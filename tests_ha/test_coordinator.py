"""Coordinator polling: payload normalization, failures, and self-healing."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import aiohttp
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fraimic.api import FraimicApiError, FraimicConnectionError
from custom_components.fraimic.const import (
    CONF_HEIGHT,
    CONF_POWER_MODE,
    CONF_WIDTH,
    DOMAIN,
    POWER_MODE_RESPONSIVE,
)
from custom_components.fraimic.coordinator import (
    REDISCOVERY_FAIL_THRESHOLD,
    FraimicDataUpdateCoordinator,
)

from .conftest import DEVICE_KEY, FRAME_INFO, HOST, setup_entry

NESTED_INFO = {
    "device": {"firmware_version": "0.2.21", "device_key": DEVICE_KEY},
    "battery": {"percent": 42, "charging": True},
    "wifi": {"ssid": "HomeNet", "rssi": -61},
    "display": {"width": 1600, "height": 1200},
}


def _coordinator(entry: MockConfigEntry) -> FraimicDataUpdateCoordinator:
    return entry.runtime_data.coordinator


async def test_setup_polls_and_exposes_frame_state(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    coordinator = _coordinator(loaded_entry)

    assert loaded_entry.state is ConfigEntryState.LOADED
    assert coordinator.frame_online
    assert coordinator.client.prefer_api_image  # firmware 0.2.28
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{loaded_entry.entry_id}_battery_percent"
    )
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "81"


async def test_nested_payload_is_normalized(
    loaded_entry: MockConfigEntry, frame_client: dict[str, AsyncMock]
) -> None:
    coordinator = _coordinator(loaded_entry)
    frame_client["get_info"].return_value = NESTED_INFO

    await coordinator.async_refresh()

    assert coordinator.data["firmware_version"] == "0.2.21"
    assert coordinator.data["battery"]["percent"] == 42
    assert coordinator.data["battery"]["charging"] is True
    assert coordinator.data["wifi"]["rssi"] == -61
    assert coordinator.data["raw"] == NESTED_INFO
    # Older firmware stays on the multipart upload path.
    assert not coordinator.client.prefer_api_image


async def test_connection_failures_count_until_frame_answers(
    loaded_entry: MockConfigEntry, frame_client: dict[str, AsyncMock]
) -> None:
    coordinator = _coordinator(loaded_entry)
    frame_client["get_info"].side_effect = FraimicConnectionError("asleep")

    await coordinator.async_refresh()
    await coordinator.async_refresh()

    assert not coordinator.last_update_success
    assert not coordinator.frame_online
    assert coordinator.consecutive_failures == 2

    frame_client["get_info"].side_effect = None
    await coordinator.async_refresh()

    assert coordinator.last_update_success
    assert coordinator.frame_online
    assert coordinator.consecutive_failures == 0


async def test_api_error_fails_the_update(
    loaded_entry: MockConfigEntry, frame_client: dict[str, AsyncMock]
) -> None:
    coordinator = _coordinator(loaded_entry)
    frame_client["get_info"].side_effect = FraimicApiError("busy", status=503)

    await coordinator.async_refresh()

    assert not coordinator.last_update_success
    assert not coordinator.frame_online


async def test_missing_frame_triggers_one_rate_limited_rescan(
    loaded_entry: MockConfigEntry, frame_client: dict[str, AsyncMock]
) -> None:
    coordinator = _coordinator(loaded_entry)
    frame_client["get_info"].side_effect = FraimicConnectionError("gone")

    with patch.object(
        FraimicDataUpdateCoordinator, "_async_rediscover", AsyncMock()
    ) as rediscover:
        for _ in range(REDISCOVERY_FAIL_THRESHOLD + 2):
            await coordinator.async_refresh()

    rediscover.assert_awaited_once_with(HOST, DEVICE_KEY)


async def test_rescan_rewrites_host_when_frame_moved(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    coordinator = _coordinator(loaded_entry)
    moved = "192.168.1.77"

    class Response:
        status = 200

        async def __aenter__(self) -> Response:
            return self

        async def __aexit__(self, *_exc: object) -> None:
            return None

        async def json(self, **_kwargs: object) -> dict[str, object]:
            return dict(FRAME_INFO)

    def get(url: str, **_kwargs: object) -> Response:
        if url != f"http://{moved}/api/info":
            raise aiohttp.ClientConnectionError(url)
        return Response()

    session = Mock(get=get)
    with (
        patch(
            "custom_components.fraimic.discovery.async_get_clientsession",
            return_value=session,
        ),
        # The entry update listener would reload onto the new host.
        patch.object(hass.config_entries, "async_reload", AsyncMock()) as reload,
    ):
        await coordinator._async_rediscover(HOST, DEVICE_KEY)
        await hass.async_block_till_done()

    assert loaded_entry.data[CONF_HOST] == moved
    reload.assert_awaited_once_with(loaded_entry.entry_id)


async def test_first_poll_backfills_device_key_unique_id(
    hass: HomeAssistant, frame_client: dict[str, AsyncMock]
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=3,
        unique_id=HOST,
        data={CONF_HOST: HOST, CONF_WIDTH: 1600, CONF_HEIGHT: 1200},
        options={CONF_POWER_MODE: POWER_MODE_RESPONSIVE},
    )
    await setup_entry(hass, entry)

    assert entry.unique_id == DEVICE_KEY
