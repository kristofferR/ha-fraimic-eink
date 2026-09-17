"""Legacy shared scene-device cleanup across HA registry versions."""

from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest

from conftest import load

registry_module = load("registry")


def test_scene_cleanup_includes_devices_owned_by_disabled_entries():
    devices = [
        SimpleNamespace(id="old-host", config_entry_id="disabled-entry"),
        SimpleNamespace(id="other-host", config_entry_id="other-entry"),
    ]
    registry = SimpleNamespace(
        async_get_devices=Mock(return_value=devices),
        async_get_device=Mock(side_effect=AssertionError("Deprecated lookup")),
        async_remove_device=Mock(),
    )

    registry_module.remove_legacy_scene_devices(registry)

    registry.async_get_devices.assert_called_once_with(
        identifiers={("fraimic", "fraimic_scenes")}
    )
    assert registry.async_remove_device.call_args_list == [call("old-host"), call("other-host")]


@pytest.mark.parametrize("present", [True, False])
def test_scene_cleanup_supports_legacy_registry(present):
    registry = SimpleNamespace(
        async_get_device=Mock(return_value=SimpleNamespace(id="old-host") if present else None),
        async_remove_device=Mock(),
    )

    registry_module.remove_legacy_scene_devices(registry)

    registry.async_get_device.assert_called_once_with(
        identifiers={("fraimic", "fraimic_scenes")}
    )
    assert registry.async_remove_device.call_args_list == ([call("old-host")] if present else [])
