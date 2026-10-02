"""Tests for the shared subnet scan and the periodic discovery sweep."""

from __future__ import annotations

import asyncio
import ipaddress
import sys
import types
from types import SimpleNamespace

import pytest
from conftest import load


class _GenericStub:
    def __class_getitem__(cls, _item):
        return cls


class _ClientError(Exception):
    pass


class _Response:
    def __init__(self, status: int, body) -> None:
        self.status = status
        self._body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc) -> None:
        return None

    async def json(self, content_type=None):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


class _Session:
    """Answers ``/api/info`` per IP; unknown IPs fail like a closed port."""

    def __init__(self, responses: dict[str, tuple[int, object]]) -> None:
        self.responses = responses
        self.probed: list[str] = []

    def get(self, url: str, timeout=None):
        ip = url.removeprefix("http://").removesuffix("/api/info")
        self.probed.append(ip)
        if ip not in self.responses:
            raise _ClientError("connection refused")
        return _Response(*self.responses[ip])


@pytest.fixture
def discovery(monkeypatch):
    load("const")
    stubs = {
        "aiohttp": {"ClientError": _ClientError, "ClientTimeout": lambda total: total},
        "homeassistant.components.network": {"async_get_adapters": None},
        "homeassistant.config_entries": {
            "ConfigEntry": _GenericStub,
            "ConfigEntryState": SimpleNamespace(LOADED="loaded"),
            "SOURCE_INTEGRATION_DISCOVERY": "integration_discovery",
        },
        "homeassistant.const": {"CONF_HOST": "host"},
        "homeassistant.core": {
            "CALLBACK_TYPE": object,
            "HomeAssistant": object,
            "callback": lambda fn: fn,
        },
        "homeassistant.helpers.discovery_flow": {"async_create_flow": None},
        "homeassistant.helpers.aiohttp_client": {"async_get_clientsession": None},
        "homeassistant.helpers.event": {
            "async_call_later": None,
            "async_track_time_interval": None,
        },
        "homeassistant.helpers.start": {"async_at_started": None},
        "homeassistant.helpers.storage": {"Store": _GenericStub},
        "homeassistant.helpers.update_coordinator": {
            "DataUpdateCoordinator": _GenericStub,
            "UpdateFailed": RuntimeError,
        },
    }
    for name in ("homeassistant", "homeassistant.components", "homeassistant.helpers"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    for name, attributes in stubs.items():
        module = types.ModuleType(name)
        module.__dict__.update(attributes)
        monkeypatch.setitem(sys.modules, name, module)
        parent, _, child = name.rpartition(".")
        if parent in sys.modules:
            setattr(sys.modules[parent], child, module)
    for name in ("fraimic.api", "fraimic.coordinator", "fraimic.discovery"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    return load("discovery")


def _entry(unique_id=None, host=None, *, state="loaded", options=None):
    return SimpleNamespace(
        unique_id=unique_id,
        data={"host": host} if host else {},
        state=state,
        options=options or {},
    )


def test_local_subnets_caps_at_24_and_skips_non_lan(discovery):
    adapters = [
        {"enabled": True, "ipv4": [{"address": "192.168.1.20", "network_prefix": 16}]},
        # Same /24 again via a second address: deduplicated.
        {"enabled": True, "ipv4": [{"address": "192.168.1.21", "network_prefix": 24}]},
        {"enabled": True, "ipv4": [{"address": "10.0.30.5", "network_prefix": 26}]},
        {"enabled": False, "ipv4": [{"address": "172.17.0.1", "network_prefix": 16}]},
        {"enabled": True, "ipv4": [{"address": "127.0.0.1", "network_prefix": 8}]},
        {"enabled": True, "ipv4": [{"address": "169.254.3.4", "network_prefix": 16}]},
        {"enabled": True, "ipv4": [{"address": "100.101.5.6", "network_prefix": 32}]},
        {"enabled": True, "ipv4": [{"address": "8.8.8.8", "network_prefix": 24}]},
        {"enabled": True, "ipv4": []},
    ]

    assert discovery.local_subnets(adapters) == [
        ipaddress.IPv4Network("192.168.1.0/24"),
        ipaddress.IPv4Network("10.0.30.0/26"),
    ]


def test_scan_subnet_returns_only_frames_with_device_key(discovery, monkeypatch):
    session = _Session(
        {
            "10.0.0.1": (200, {"device_key": "flat", "battery_pct": 80}),
            "10.0.0.2": (200, {"device": {"device_key": "nested"}}),
            "10.0.0.3": (200, {"name": "some other gadget"}),
            "10.0.0.4": (404, {"device_key": "not-served"}),
            "10.0.0.5": (200, ["not", "a", "dict"]),
            "10.0.0.6": (200, ValueError("not json")),
        }
    )
    monkeypatch.setattr(discovery, "async_get_clientsession", lambda _hass: session)

    found = asyncio.run(
        discovery.async_scan_subnet(None, ipaddress.IPv4Network("10.0.0.0/29"))
    )

    assert {key: ip for key, (ip, _info) in found.items()} == {
        "flat": "10.0.0.1",
        "nested": "10.0.0.2",
    }
    assert found["flat"][1]["battery"]["percent"] == 80
    assert sorted(session.probed) == [f"10.0.0.{n}" for n in range(1, 7)]


def test_sweep_feeds_only_unknown_frames_into_discovery(discovery, monkeypatch):
    session = _Session(
        {
            "192.168.1.10": (200, {"device_key": "configured"}),
            "192.168.1.11": (200, {"device_key": "ignored"}),
            # Pre-device_key entry still keyed by host.
            "192.168.1.12": (200, {"device_key": "legacy"}),
            "192.168.1.13": (200, {"device_key": "new-frame"}),
            "192.168.1.14": (200, {"device_key": "by-hostname"}),
        }
    )
    entries = [
        _entry("configured", "192.168.1.40"),
        _entry("ignored", state="not_loaded"),
        _entry("192.168.1.12", "192.168.1.12"),
        # Legacy hostname entry; resolves to a scanned frame.
        _entry("fraimic.local", "fraimic.local"),
    ]
    flows = []

    async def adapters(_hass):
        return [
            {"enabled": True, "ipv4": [{"address": "192.168.1.2", "network_prefix": 24}]}
        ]

    hass = SimpleNamespace(
        data={},
        config_entries=SimpleNamespace(async_entries=lambda _domain: entries),
    )

    async def resolve(entries):
        assert any(e.data.get("host") == "fraimic.local" for e in entries)
        return {"192.168.1.14"}

    monkeypatch.setattr(discovery, "_async_resolve_hosts", resolve)
    monkeypatch.setattr(discovery, "async_get_clientsession", lambda _hass: session)
    monkeypatch.setattr(discovery.network, "async_get_adapters", adapters)
    monkeypatch.setattr(
        discovery.discovery_flow,
        "async_create_flow",
        lambda _hass, domain, *, context, data: flows.append((domain, context, data)),
    )

    asyncio.run(discovery._async_sweep(hass))
    # A restart of the sweep (entry reload) must not rescan right away.
    asyncio.run(discovery._async_sweep(hass))

    assert flows == [
        (
            "fraimic",
            {"source": "integration_discovery"},
            {"host": "192.168.1.13", "device_key": "new-frame"},
        )
    ]
    assert len(session.probed) == 254


@pytest.mark.parametrize(
    ("entries", "enabled"),
    [
        ([], False),
        ([_entry("a"), _entry("b", options={"network_scan": True})], True),
        ([_entry("a"), _entry("b", options={"network_scan": False})], False),
        # Ignored, disabled, and failed entries don't hold an opinion.
        ([_entry("a"), _entry("b", state="not_loaded", options={"network_scan": False})], True),
        ([_entry("a", state="setup_retry")], False),
    ],
)
def test_sweep_enabled_lets_any_frame_opt_out(discovery, entries, enabled):
    assert discovery.sweep_enabled(entries) is enabled
