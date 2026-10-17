"""Auto mode through Home Assistant: the End of queue select and the action."""

from __future__ import annotations

from collections.abc import Generator
from datetime import time
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fraimic.const import DOMAIN
from custom_components.fraimic.render.schema import SCREEN_SCHEMA, screen_from_dict


@pytest.fixture(autouse=True)
def no_art_downloads() -> Generator[AsyncMock]:
    """Auto mode resolves picks in the background; keep it off the network."""
    with patch(
        "custom_components.fraimic.auto_sources.async_resolve_pick",
        AsyncMock(return_value=None),
    ) as resolve:
        yield resolve


async def test_end_of_queue_select_switches_to_auto_mode(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    entity_id = er.async_get(hass).async_get_entity_id(
        "select", DOMAIN, f"{loaded_entry.entry_id}_end_of_queue"
    )
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "stop"
    assert state.attributes["options"] == ["stop", "repeat", "auto"]

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": entity_id, "option": "auto"},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert loaded_entry.runtime_data.scheduler.auto_enabled
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "auto"


async def test_set_auto_mode_action_updates_only_given_fields(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    await hass.services.async_call(
        DOMAIN,
        "set_auto_mode",
        {
            "end_of_queue": "auto",
            "sources": [
                {"kind": "gallery", "source": "saved", "browse_id": "favorites",
                 "label": "Favorites", "weight": 2},
            ],
            "cadence": "times",
            "times": ["07:00:00", "17:30:00"],
            "fit": "default",
        },
        blocking=True,
    )
    scheduler = loaded_entry.runtime_data.scheduler
    assert scheduler.auto_enabled
    assert [source.label for source in scheduler.auto.sources] == ["Favorites"]
    assert scheduler.auto.times == (time(7), time(17, 30))
    assert scheduler.auto.fit is None
    assert scheduler.auto.avoid_repeats_days == 30

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "set_auto_mode", {"avoid_repeats_days": 999}, blocking=True
        )


@pytest.mark.parametrize("patch", [
    {"cadence": "times"},
    {"sources": [{"kind": "shuffle"}, {"kind": "shuffle"}]},
])
async def test_set_auto_mode_reports_cross_field_errors_as_invalid_input(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, patch: dict
) -> None:
    scheduler = loaded_entry.runtime_data.scheduler
    before = scheduler.auto
    with pytest.raises(ServiceValidationError, match="Invalid auto mode settings"):
        await hass.services.async_call(
            DOMAIN, "set_auto_mode", patch, blocking=True
        )
    assert scheduler.auto == before


@pytest.mark.parametrize("settings", [{}, {"caption": True}])
async def test_new_picks_records_skipped_art_with_settings_update(
    hass: HomeAssistant, loaded_entry: MockConfigEntry, settings: dict
) -> None:
    scheduler = loaded_entry.runtime_data.scheduler
    for image_id in ("first", "second", "third"):
        slide = screen_from_dict(SCREEN_SCHEMA({
            "kind": "picture", "library_image": image_id,
        }))
        scheduler.queue.add_auto(slide, "Favorites")

    await hass.services.async_call(
        DOMAIN, "set_auto_mode", {**settings, "new_picks": True}, blocking=True
    )

    assert set(scheduler.auto_history.entries) == {
        "library:first", "library:second", "library:third",
    }
    assert not scheduler.queue.items
    assert scheduler.auto.caption == settings.get("caption", False)
