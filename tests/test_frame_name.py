"""Tests for panel frame-name resolution."""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from conftest import load


def _module(monkeypatch, device, modern=True):
    homeassistant = types.ModuleType("homeassistant")
    helpers = types.ModuleType("homeassistant.helpers")
    device_registry = types.ModuleType("homeassistant.helpers.device_registry")
    legacy = Mock(return_value=device)
    registry = SimpleNamespace(async_get_device=legacy)
    if modern:
        registry.async_get_device_by_identifier = Mock(return_value=device)
    device_registry.async_get = lambda _hass: registry
    helpers.device_registry = device_registry
    homeassistant.helpers = helpers
    monkeypatch.setitem(sys.modules, "homeassistant", homeassistant)
    monkeypatch.setitem(sys.modules, "homeassistant.helpers", helpers)
    monkeypatch.setitem(
        sys.modules, "homeassistant.helpers.device_registry", device_registry
    )
    sys.modules.pop("fraimic.frame_name", None)
    return load("frame_name"), registry


@pytest.mark.parametrize("modern", [True, False], ids=["scoped", "legacy"])
def test_user_renamed_device_wins_over_original_entry_title(monkeypatch, modern) -> None:
    module, registry = _module(
        monkeypatch,
        SimpleNamespace(name_by_user="Hallway", name="Fraimic E-Ink Canvas"),
        modern=modern,
    )
    entry = SimpleNamespace(
        entry_id="entry", unique_id="frame-key", title="Fraimic E-Ink Canvas (host)"
    )

    assert module.frame_display_name(SimpleNamespace(), entry) == "Hallway"
    if modern:
        registry.async_get_device_by_identifier.assert_called_once_with(
            ("fraimic", "frame-key"), "entry"
        )
        registry.async_get_device.assert_not_called()
    else:
        registry.async_get_device.assert_called_once_with(
            identifiers={("fraimic", "frame-key")}
        )


def test_entry_title_is_used_when_device_is_missing(monkeypatch) -> None:
    module, registry = _module(monkeypatch, None)
    entry = SimpleNamespace(entry_id="entry", unique_id=None, title="Original")

    assert module.frame_display_name(SimpleNamespace(), entry) == "Original"
    registry.async_get_device_by_identifier.assert_called_once_with(
        ("fraimic", "entry"), "entry"
    )
    registry.async_get_device.assert_not_called()
