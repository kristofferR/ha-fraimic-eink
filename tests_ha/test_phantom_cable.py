"""A reported charging cable while the battery keeps falling raises a repair."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fraimic.const import DOMAIN

from .conftest import FRAME_INFO


async def _poll(
    entry: MockConfigEntry,
    frame_client: dict[str, AsyncMock],
    freezer: FrozenDateTimeFactory,
    percent: int,
    *,
    cable: bool = True,
    hours: float = 0,
) -> bool:
    """Poll after ``hours``; return whether the repair is raised."""
    freezer.tick(timedelta(hours=hours))
    frame_client["get_info"].return_value = {
        **FRAME_INFO, "battery_pct": percent, "cable_connected": cable,
    }
    await entry.runtime_data.coordinator.async_refresh()
    issue_id = f"phantom_cable_{entry.entry_id}"
    return ir.async_get(entry.runtime_data.coordinator.hass).async_get_issue(
        DOMAIN, issue_id
    ) is not None


async def test_sustained_drain_with_cable_raises_then_clears(
    loaded_entry: MockConfigEntry,
    frame_client: dict[str, AsyncMock],
    freezer: FrozenDateTimeFactory,
) -> None:
    # The full-charge plateau doesn't count; the stretch starts at 94 %.
    assert not await _poll(loaded_entry, frame_client, freezer, 100)
    assert not await _poll(loaded_entry, frame_client, freezer, 94, hours=1)
    # 5 points, but not yet 6 hours.
    assert not await _poll(loaded_entry, frame_client, freezer, 89, hours=5)
    assert await _poll(loaded_entry, frame_client, freezer, 88, hours=1)
    # Unplugging (or the frame dropping the phantom cable) clears it.
    assert not await _poll(loaded_entry, frame_client, freezer, 88, cable=False)


@pytest.mark.parametrize("percents", [(60, 61, 62, 63), (60, 59, 60, 58)])
async def test_charging_frame_raises_nothing(
    loaded_entry: MockConfigEntry,
    frame_client: dict[str, AsyncMock],
    freezer: FrozenDateTimeFactory,
    percents: tuple[int, ...],
) -> None:
    for percent in percents:
        assert not await _poll(loaded_entry, frame_client, freezer, percent, hours=3)
