"""Config and options flows: setup, discovery, reconfigure, and validation."""

from __future__ import annotations

from collections.abc import Generator
from ipaddress import ip_address
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import (
    SOURCE_DHCP,
    SOURCE_INTEGRATION_DISCOVERY,
    SOURCE_USER,
    SOURCE_ZEROCONF,
)
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fraimic.api import FraimicConnectionError
from custom_components.fraimic.cloud import FraimicCloudAuthError, FraimicCloudClient
from custom_components.fraimic.const import (
    CONF_CAMERA_INTERVAL,
    CONF_CLOUD_EMAIL,
    CONF_CLOUD_PASSWORD,
    CONF_DEFAULT_PROVIDER,
    CONF_DELIVERY_MODE,
    CONF_FRAME_MODEL,
    CONF_HEIGHT,
    CONF_ROTATION,
    CONF_WIDTH,
    DELIVERY_CLOUD,
    DELIVERY_LOCAL,
    DOMAIN,
    MIN_CAMERA_INTERVAL,
    MODEL_CUSTOM,
)

from .conftest import DEVICE_KEY, FRAME_INFO, HOST

NEW_HOST = "192.168.1.77"


@pytest.fixture(autouse=True)
def no_entry_setup() -> Generator[AsyncMock]:
    """Created entries must not start the whole integration."""
    with patch(
        "custom_components.fraimic.async_setup_entry", return_value=True
    ) as setup_entry:
        yield setup_entry


def _zeroconf(host: str) -> ZeroconfServiceInfo:
    return ZeroconfServiceInfo(
        ip_address=ip_address(host),
        ip_addresses=[ip_address(host)],
        port=80,
        hostname="fraimic.local.",
        type="_http._tcp.local.",
        name="fraimic._http._tcp.local.",
        properties={},
    )


async def test_user_step_creates_entry_keyed_by_device_key(
    hass: HomeAssistant, frame_client: dict[str, AsyncMock]
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: f" http://{HOST}/ "}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == f"Fraimic E-Ink Canvas ({HOST})"
    assert result["data"] == {CONF_HOST: HOST, CONF_WIDTH: 1600, CONF_HEIGHT: 1200}
    assert result["result"].unique_id == DEVICE_KEY


async def test_user_step_reports_unreachable_frame(
    hass: HomeAssistant, frame_client: dict[str, AsyncMock]
) -> None:
    frame_client["get_info"].side_effect = FraimicConnectionError("asleep")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: HOST}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_unknown_resolution_asks_for_model(
    hass: HomeAssistant, frame_client: dict[str, AsyncMock]
) -> None:
    frame_client["get_info"].return_value = {"device_key": DEVICE_KEY}
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: HOST}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "resolution"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_FRAME_MODEL: MODEL_CUSTOM, CONF_WIDTH: 800, CONF_HEIGHT: 602}
    )
    assert result["errors"] == {"base": "odd_resolution"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_FRAME_MODEL: "large"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_HOST: HOST, CONF_WIDTH: 1440, CONF_HEIGHT: 2560}


async def test_user_step_aborts_for_configured_frame(
    hass: HomeAssistant,
    frame_client: dict[str, AsyncMock],
    config_entry: MockConfigEntry,
) -> None:
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: NEW_HOST}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    # Same device_key at a new address: the stored host follows the frame.
    assert config_entry.data[CONF_HOST] == NEW_HOST


async def test_zeroconf_discovery_creates_entry(
    hass: HomeAssistant, frame_client: dict[str, AsyncMock]
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=_zeroconf(HOST)
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_HOST] == HOST
    assert result["result"].unique_id == DEVICE_KEY


async def test_zeroconf_discovery_aborts_when_frame_unreachable(
    hass: HomeAssistant, frame_client: dict[str, AsyncMock]
) -> None:
    frame_client["get_info"].side_effect = FraimicConnectionError("asleep")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=_zeroconf(HOST)
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


async def test_swept_frame_waits_for_confirmation(
    hass: HomeAssistant, frame_client: dict[str, AsyncMock]
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_INTEGRATION_DISCOVERY},
        data={CONF_HOST: HOST, "device_key": DEVICE_KEY},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "discovery_confirm"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_HOST] == HOST
    assert result["result"].unique_id == DEVICE_KEY


async def test_dhcp_discovery_updates_known_frame_host(
    hass: HomeAssistant,
    frame_client: dict[str, AsyncMock],
    config_entry: MockConfigEntry,
) -> None:
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_DHCP},
        data=DhcpServiceInfo(
            ip=NEW_HOST, hostname="fraimic", macaddress="1cdbd4123456"
        ),
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert config_entry.data[CONF_HOST] == NEW_HOST


async def test_reconfigure_moves_entry_to_new_host(
    hass: HomeAssistant,
    frame_client: dict[str, AsyncMock],
    config_entry: MockConfigEntry,
) -> None:
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: NEW_HOST}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert config_entry.data[CONF_HOST] == NEW_HOST
    assert config_entry.unique_id == DEVICE_KEY


async def test_reconfigure_rejects_a_different_frame(
    hass: HomeAssistant,
    frame_client: dict[str, AsyncMock],
    config_entry: MockConfigEntry,
) -> None:
    config_entry.add_to_hass(hass)
    frame_client["get_info"].return_value = {**FRAME_INFO, "device_key": "fk_other"}
    result = await config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: NEW_HOST}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_same_device"
    assert config_entry.data[CONF_HOST] == HOST


async def test_options_flow_stores_rotation_as_int(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM

    # Some frontends submit select values as strings.
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_ROTATION: "90", CONF_DELIVERY_MODE: DELIVERY_LOCAL}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options[CONF_ROTATION] == 90
    assert config_entry.options[CONF_DELIVERY_MODE] == DELIVERY_LOCAL


async def test_options_flow_rejects_invalid_combinations(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(config_entry.entry_id)

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_ROTATION: "0",
            CONF_CAMERA_INTERVAL: MIN_CAMERA_INTERVAL - 1,
            CONF_DEFAULT_PROVIDER: "unsplash",
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {
        CONF_CAMERA_INTERVAL: "camera_interval_too_low",
        CONF_DEFAULT_PROVIDER: "provider_key_required",
    }


async def test_options_cloud_step_reports_bad_login(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_ROTATION: "0", CONF_DELIVERY_MODE: DELIVERY_CLOUD}
    )
    assert result["step_id"] == "cloud"

    with patch.object(
        FraimicCloudClient,
        "async_login",
        AsyncMock(side_effect=FraimicCloudAuthError("bad password")),
    ):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_CLOUD_EMAIL: "owner@example.com", CONF_CLOUD_PASSWORD: "wrong"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    assert CONF_CLOUD_EMAIL not in config_entry.options
