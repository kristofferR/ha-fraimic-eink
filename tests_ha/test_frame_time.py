"""Frame timestamps are frame-local time in the frame's own POSIX timezone."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, patch

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fraimic.api import FraimicConnectionError
from custom_components.fraimic.const import DOMAIN, POWER_MODE_MINIMUM
from custom_components.fraimic.power import queue_probe_delay

from .conftest import FRAME_INFO, setup_entry

# An EST5EDT frame (UTC-04:00 in October) polled at 21:32:10 UTC.
NOW = "2026-10-22T21:32:10+00:00"
EDT_FRAME = {
    **FRAME_INFO,
    "time_synced": True,
    "local_time": "2026-10-22T17:32:14",
    "last_refresh": "2026-09-15T02:59:59",
    "next_refresh": "2026-10-23T03:00:00",
}


def _state(hass: HomeAssistant, entry: MockConfigEntry, key: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_{key}"
    )
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    return state.state


async def test_est_frame_times_in_an_oslo_home(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    frame_client: dict[str, AsyncMock],
    config_entry: MockConfigEntry,
) -> None:
    await hass.config.async_set_time_zone("Europe/Oslo")
    freezer.move_to(NOW)
    frame_client["get_info"].return_value = dict(EDT_FRAME)
    await setup_entry(hass, config_entry)
    coordinator = config_entry.runtime_data.coordinator

    # 03:00 EDT is 07:00 UTC (09:00 in Oslo), not 03:00 UTC or Oslo time.
    assert _state(hass, config_entry, "next_refresh") == "2026-10-23T07:00:00+00:00"
    assert _state(hass, config_entry, "last_refresh") == "2026-09-15T06:59:59+00:00"
    assert _state(hass, config_entry, "utc_offset") == "UTC-04:00"
    # The queued-send probe targets that same instant (plus its 30 s margin).
    next_at = coordinator.data["display"]["next_refresh_at"]
    assert next_at == datetime.fromisoformat("2026-10-23T07:00:00+00:00").timestamp()
    now = datetime.fromisoformat(NOW).timestamp()
    assert queue_probe_delay(
        POWER_MODE_MINIMUM, 0, now=now, next_refresh=next_at
    ) == next_at - now + 30
    issue = ir.async_get(hass).async_get_issue(
        DOMAIN, f"frame_timezone_{config_entry.entry_id}"
    )
    assert issue is not None
    assert issue.translation_placeholders == {
        "frame": config_entry.title,
        "frame_offset": "UTC-04:00",
        "ha_offset": "UTC+02:00",
        "maintenance": "09:00",
    }

    # The offset survives a restart without a poll...
    frame_client["get_info"].side_effect = FraimicConnectionError("asleep")
    with (
        patch("custom_components.fraimic.async_register_panel"),
        patch("custom_components.fraimic._async_warm_catalogs"),
        patch("custom_components.fraimic.async_start_sweep", return_value=lambda: None),
    ):
        assert await hass.config_entries.async_reload(config_entry.entry_id)
        await hass.async_block_till_done()
    assert _state(hass, config_entry, "utc_offset") == "UTC-04:00"

    # ...and is unknown while the frame's clock isn't synced.
    frame_client["get_info"].side_effect = None
    frame_client["get_info"].return_value = {
        **EDT_FRAME, "time_synced": False, "local_time": None,
    }
    await config_entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert _state(hass, config_entry, "utc_offset") == "unknown"
