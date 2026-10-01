"""Entity availability rides out deep sleep without hiding failed polls."""

import asyncio
import sys
import time
import types
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest
from conftest import load
from test_api_firmware_gate import _load_api

HOUR = 3600


@pytest.fixture
def coordinator_module(monkeypatch):
    _load_api()  # stubs aiohttp when it is not installed
    class GenericStub:
        def __class_getitem__(cls, _item):
            return cls

    stubs = {
        "homeassistant.config_entries": {"ConfigEntry": GenericStub},
        "homeassistant.const": {"CONF_HOST": "host"},
        "homeassistant.core": {"HomeAssistant": object, "callback": lambda fn: fn},
        "homeassistant.helpers.aiohttp_client": {"async_get_clientsession": Mock()},
        "homeassistant.helpers.storage": {"Store": GenericStub},
        "homeassistant.helpers.update_coordinator": {
            "DataUpdateCoordinator": GenericStub, "UpdateFailed": RuntimeError,
        },
    }
    for name, attributes in stubs.items():
        module = types.ModuleType(name)
        module.__dict__.update(attributes)
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.delitem(sys.modules, "fraimic.coordinator", raising=False)
    return load("coordinator")


def _coordinator(module, *, data, success, seen_hours_ago):
    coordinator = object.__new__(module.FraimicDataUpdateCoordinator)
    coordinator.data = data
    coordinator.last_update_success = success
    coordinator._last_seen = (
        None if seen_hours_ago is None else time.time() - seen_hours_ago * HOUR
    )
    return coordinator


def _cloud(hours_ago):
    seen = time.time() - hours_ago * HOUR
    return {"device": {"cloud_last_seen": datetime.fromtimestamp(seen, UTC).isoformat()}}


@pytest.mark.parametrize(
    ("data", "success", "seen_hours_ago", "reachable"),
    [
        (None, True, 0, False),
        ({}, True, 0, True),
        ({}, False, 71, True),
        ({}, False, 73, False),
        ({}, False, None, False),
        # Restored caches report success without proving recent contact.
        ({}, True, 73, False),
        ({}, True, None, False),
        # Cloud-delivered frames stay asleep on the LAN by design.
        (_cloud(1), True, None, True),
        (_cloud(73), True, 1, True),
        (_cloud(73), True, None, False),
    ],
    ids=[
        "no-data", "poll-ok", "asleep-in-grace", "grace-expired", "never-seen",
        "stale-restore", "legacy-restore", "cloud-check-in", "lan-newer-than-cloud",
        "cloud-stale",
    ],
)
def test_device_reachable_verdict(coordinator_module, data, success, seen_hours_ago, reachable):
    assert coordinator_module.UNAVAILABLE_AFTER == 72 * HOUR
    coordinator = _coordinator(
        coordinator_module, data=data, success=success, seen_hours_ago=seen_hours_ago
    )
    assert coordinator.device_reachable is reachable


def test_sleeping_frame_still_fails_poll_but_stays_available(coordinator_module):
    coordinator = _coordinator(coordinator_module, data={}, success=True, seen_hours_ago=1)
    coordinator.config_entry = types.SimpleNamespace(runtime_data=None)
    coordinator.client = types.SimpleNamespace(
        get_info=AsyncMock(side_effect=coordinator_module.FraimicConnectionError("asleep"))
    )
    coordinator.frame_online = True
    coordinator._consecutive_failures = 0

    with pytest.raises(RuntimeError):
        asyncio.run(coordinator._async_update_data())
    coordinator.last_update_success = False  # what DataUpdateCoordinator records

    assert coordinator.consecutive_failures == 1
    assert coordinator.frame_online is False
    assert coordinator.device_reachable is True
