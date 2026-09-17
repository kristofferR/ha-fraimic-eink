"""Verify diagnostics redact cloud and network identifiers."""

import asyncio
import json
import re
import sys
import types
from unittest.mock import AsyncMock

import pytest

from conftest import load
from test_services import _load_services


def test_cloud_identifiers_pass_through_redaction(monkeypatch):
    _load_services(monkeypatch)
    redactions = []

    def redact(data, keys):
        redactions.append((data, keys))
        return {"redacted": True}

    ha_diagnostics = types.ModuleType("homeassistant.components.diagnostics")
    ha_diagnostics.async_redact_data = redact
    monkeypatch.setitem(sys.modules, "homeassistant.components.diagnostics", ha_diagnostics)
    sys.modules.pop("fraimic.diagnostics", None)
    diagnostics = load("diagnostics")
    monkeypatch.setattr(diagnostics, "_async_logs", AsyncMock(return_value={}))
    cloud_data = {"album_id": "album", "upload_id": "upload", "album_device_id": "canvas"}
    entry = types.SimpleNamespace(
        data={}, options={"cloud_device_id": "canvas"},
        runtime_data=types.SimpleNamespace(
            coordinator=types.SimpleNamespace(
                async_refresh_info_page=AsyncMock(), data={}, info_page={},
            ),
            power=types.SimpleNamespace(diagnostics=lambda: {}),
            cloud=types.SimpleNamespace(diagnostics=lambda: cloud_data),
        ),
    )
    result = asyncio.run(diagnostics.async_get_config_entry_diagnostics(None, entry))
    assert result["cloud"] == {"redacted": True}
    sensitive = {"album_id", "upload_id", "album_device_id", "cloud_device_id", "device_key"}
    assert any(data is cloud_data and sensitive <= keys for data, keys in redactions)


@pytest.mark.parametrize("nested", [True, False], ids=["nested", "flat"])
def test_network_identifiers_are_redacted_in_structured_data_and_logs(monkeypatch, nested):
    _load_services(monkeypatch)

    class GenericStub:
        def __class_getitem__(cls, _item):
            return cls

    stubs = {
        "homeassistant.config_entries": {"ConfigEntry": GenericStub},
        "homeassistant.const": {"CONF_HOST": "host"},
        "homeassistant.core": {"HomeAssistant": object, "callback": lambda fn: fn},
        "homeassistant.helpers.aiohttp_client": {"async_get_clientsession": object},
        "homeassistant.helpers.storage": {"Store": GenericStub},
        "homeassistant.helpers.update_coordinator": {
            "DataUpdateCoordinator": GenericStub, "UpdateFailed": RuntimeError,
        },
    }
    for name, attributes in stubs.items():
        module = types.ModuleType(name)
        module.__dict__.update(attributes)
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.delitem(sys.modules, "fraimic.coordinator")
    normalize_info = load("coordinator").normalize_info

    def redact(data, keys):
        # Stand in for HA's recursive redaction in this HA-free test suite.
        if isinstance(data, dict):
            return {
                key: "**REDACTED**" if key in keys else redact(value, keys)
                for key, value in data.items()
            }
        if isinstance(data, list):
            return [redact(value, keys) for value in data]
        return data

    ha_diagnostics = types.ModuleType("homeassistant.components.diagnostics")
    ha_diagnostics.async_redact_data = redact
    monkeypatch.setitem(sys.modules, "homeassistant.components.diagnostics", ha_diagnostics)
    sys.modules.pop("fraimic.diagnostics", None)
    diagnostics = load("diagnostics")
    wifi = {
        "mac": "02:11:22:33:44:55",
        "bssid": "02:AA:BB:CC:DD:EE",
        "wifi_mac": "02:66:77:88:99:AA",
    }
    raw = {"wifi": wifi} if nested else {
        "mac_address": wifi["mac"],
        "bssid": wifi["bssid"],
        "wifi_mac": wifi["wifi_mac"],
    }
    data = normalize_info({**raw, "battery_pct": 80})
    logs = (
        "<div class='log-area' id='logOutput'>Connected "
        + " ".join(wifi.values()) + "</div>"
    )
    entry = types.SimpleNamespace(
        data={}, options={},
        runtime_data=types.SimpleNamespace(
            coordinator=types.SimpleNamespace(
                async_refresh_info_page=AsyncMock(), data=data, info_page={},
                client=types.SimpleNamespace(get_logs=AsyncMock(return_value=logs)),
            ),
            power=types.SimpleNamespace(diagnostics=lambda: {}), cloud=None,
        ),
    )

    result = asyncio.run(diagnostics.async_get_config_entry_diagnostics(None, entry))

    assert not re.search(r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", json.dumps(result))
    assert result["data"]["battery"]["percent"] == 80
    assert result["logs"]["current"] == ["Connected **REDACTED** **REDACTED** **REDACTED**"]
    assert data["wifi"]["mac"] == "02:11:22:33:44:55"
