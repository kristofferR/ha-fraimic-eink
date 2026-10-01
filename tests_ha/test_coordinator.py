"""Coordinator polling: payload normalization, failures, and self-healing."""

from __future__ import annotations

import time
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import aiohttp
import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from freezegun.api import FrozenDateTimeFactory
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.fraimic.api import (
    FraimicApiError,
    FraimicClient,
    FraimicConnectionError,
)
from custom_components.fraimic.const import (
    CONF_HEIGHT,
    CONF_POWER_MODE,
    CONF_WIDTH,
    DOMAIN,
    POWER_MODE_MINIMUM,
    POWER_MODE_RESPONSIVE,
)
from custom_components.fraimic.coordinator import (
    REDISCOVERY_FAIL_THRESHOLD,
    UNAVAILABLE_AFTER,
    normalize_info,
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


async def test_sleeping_frame_keeps_last_known_state(
    hass: HomeAssistant,
    loaded_entry: MockConfigEntry,
    frame_client: dict[str, AsyncMock],
) -> None:
    registry = er.async_get(hass)

    def state(domain: str, key: str) -> str:
        entity_id = registry.async_get_entity_id(
            domain, DOMAIN, f"{loaded_entry.entry_id}_{key}"
        )
        assert entity_id is not None
        current = hass.states.get(entity_id)
        assert current is not None
        return current.state

    frame_client["get_info"].side_effect = FraimicConnectionError("asleep")
    await _coordinator(loaded_entry).async_refresh()
    await hass.async_block_till_done()

    assert state("sensor", "battery_percent") == "81"
    assert state("binary_sensor", "wifi_connected") == "off"
    assert state("sensor", "last_seen") not in ("unknown", "unavailable")


async def test_unpolled_frame_goes_unavailable_when_grace_expires(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    frame_client: dict[str, AsyncMock],
    freezer: FrozenDateTimeFactory,
) -> None:
    """Minimum power mode never polls; the expiry itself must update entities."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        version=3,
        unique_id=DEVICE_KEY,
        data={CONF_HOST: HOST, CONF_WIDTH: 1600, CONF_HEIGHT: 1200},
        options={CONF_POWER_MODE: POWER_MODE_MINIMUM},
    )
    hass_storage[f"{DOMAIN}_coordinator_{config_entry.entry_id}"] = {
        "version": 1,
        "key": f"{DOMAIN}_coordinator_{config_entry.entry_id}",
        "data": {
            "data": normalize_info(FRAME_INFO),
            "last_seen": time.time() - UNAVAILABLE_AFTER + 3600,
        },
    }
    await setup_entry(hass, config_entry)
    frame_client["get_info"].assert_not_awaited()
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{config_entry.entry_id}_battery_percent"
    )
    assert entity_id is not None

    def state() -> str | None:
        current = hass.states.get(entity_id)
        return current.state if current is not None else None

    assert state() == "81"
    # Data listeners (scheduler, send queue) must not mistake expiry for data.
    data_listener = Mock()
    config_entry.runtime_data.coordinator.async_add_listener(data_listener)

    freezer.tick(timedelta(hours=2))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert state() == "unavailable"
    data_listener.assert_not_called()


    # Any later frame response (any request path) restores availability.
    client = config_entry.runtime_data.coordinator.client
    client.last_response = time.time()
    assert client.on_response is not None
    client.on_response()
    await hass.async_block_till_done()

    assert state() == "81"
    connectivity = er.async_get(hass).async_get_entity_id(
        "binary_sensor", DOMAIN, f"{config_entry.entry_id}_wifi_connected"
    )
    assert connectivity is not None
    connected = hass.states.get(connectivity)
    assert connected is not None and connected.state == "on"
    data_listener.assert_not_called()


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
            "custom_components.fraimic.coordinator.async_get_clientsession",
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


async def test_error_response_still_counts_as_contact() -> None:
    """A 503 proves the frame is awake; a refused connection does not."""

    class Busy:
        status = 503

        async def __aenter__(self) -> Busy:
            return self

        async def __aexit__(self, *_exc: object) -> None:
            return None

        async def json(self, **_kwargs: object) -> dict[str, str]:
            return {"error": "busy"}

    session = Mock(request=AsyncMock(return_value=Busy()))
    client = FraimicClient(HOST, session)

    with pytest.raises(FraimicApiError):
        await client.get_info()
    assert client.last_response is not None

    session.request.side_effect = aiohttp.ClientConnectionError("refused")
    seen = client.last_response
    with pytest.raises(FraimicConnectionError):
        await client.get_info()
    assert client.last_response == seen
