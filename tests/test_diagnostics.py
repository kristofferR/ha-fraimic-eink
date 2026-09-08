"""Verify cloud diagnostics use Home Assistant's structured redaction."""

import asyncio
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
