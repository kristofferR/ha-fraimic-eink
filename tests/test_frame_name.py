"""Tests for panel frame-name resolution."""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace

from conftest import load


def _module(monkeypatch, device):
    homeassistant = types.ModuleType("homeassistant")
    helpers = types.ModuleType("homeassistant.helpers")
    device_registry = types.ModuleType("homeassistant.helpers.device_registry")
    registry = SimpleNamespace(async_get_device=lambda **_kwargs: device)
    device_registry.async_get = lambda _hass: registry
    helpers.device_registry = device_registry
    homeassistant.helpers = helpers
    monkeypatch.setitem(sys.modules, "homeassistant", homeassistant)
    monkeypatch.setitem(sys.modules, "homeassistant.helpers", helpers)
    monkeypatch.setitem(
        sys.modules, "homeassistant.helpers.device_registry", device_registry
    )
    sys.modules.pop("fraimic.frame_name", None)
    return load("frame_name")


def test_user_renamed_device_wins_over_original_entry_title(monkeypatch) -> None:
    module = _module(
        monkeypatch,
        SimpleNamespace(name_by_user="Hallway", name="Fraimic E-Ink Canvas"),
    )
    entry = SimpleNamespace(
        entry_id="entry", unique_id="frame-key", title="Fraimic E-Ink Canvas (host)"
    )

    assert module.frame_display_name(SimpleNamespace(), entry) == "Hallway"


def test_entry_title_is_used_when_device_is_missing(monkeypatch) -> None:
    module = _module(monkeypatch, None)
    entry = SimpleNamespace(entry_id="entry", unique_id=None, title="Original")

    assert module.frame_display_name(SimpleNamespace(), entry) == "Original"
