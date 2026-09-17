"""Verify diagnostics redact cloud and network identifiers."""

import asyncio
import json
import re
import sys
import types
from unittest.mock import AsyncMock

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


def test_network_identifiers_are_redacted_in_structured_data_and_logs(monkeypatch):
    _load_services(monkeypatch)

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
    wifi = {"mac": "02:11:22:33:44:55", "bssid": "02:AA:BB:CC:DD:EE"}
    raw = {"wifi": {**wifi, "wifi_mac": "02:66:77:88:99:AA"}}
    data = {"wifi": wifi, "raw": raw, "battery": {"percent": 80}}
    logs = "<div class='log-area' id='logOutput'>Connected " + " ".join(wifi.values()) + "</div>"
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
    assert result["logs"]["current"] == ["Connected **REDACTED** **REDACTED**"]
    assert data["wifi"]["mac"] == "02:11:22:33:44:55"
