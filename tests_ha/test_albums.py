"""fraimic.update_album through the frame's thin cloud proxy."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fraimic.api import FraimicConnectionError, FraimicError
from custom_components.fraimic.const import DOMAIN

ALBUM = {"id": "album-1", "name": "Art", "active": True, "schedule": None}


async def _deactivate(hass: HomeAssistant) -> dict[str, Any] | None:
    return await hass.services.async_call(
        DOMAIN,
        "update_album",
        {"album_id": "album-1", "active": False},
        blocking=True,
        return_response=True,
    )


@pytest.mark.parametrize(
    "reply_error",
    [
        FraimicError("PUT /api/albums/album-1 did not return the album"),
        FraimicConnectionError("reply lost"),
    ],
    ids=["status-ok-body", "lost-reply"],
)
async def test_unclear_put_reply_is_confirmed_by_rereading(
    hass: HomeAssistant,
    loaded_entry: MockConfigEntry,
    frame_client: dict[str, AsyncMock],
    monkeypatch: pytest.MonkeyPatch,
    reply_error: FraimicError,
) -> None:
    client = loaded_entry.runtime_data.client
    monkeypatch.setattr(client, "update_album", AsyncMock(side_effect=reply_error))
    frame_client["get_albums"].side_effect = [[ALBUM], [{**ALBUM, "active": False}]]

    result = await _deactivate(hass)

    assert result == {"album": {"id": "album-1", "name": "Art", "active": False}}


async def test_unclear_put_reply_with_unchanged_album_fails(
    hass: HomeAssistant,
    loaded_entry: MockConfigEntry,
    frame_client: dict[str, AsyncMock],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = loaded_entry.runtime_data.client
    monkeypatch.setattr(
        client, "update_album", AsyncMock(side_effect=FraimicConnectionError("lost"))
    )
    frame_client["get_albums"].return_value = [ALBUM]

    with pytest.raises(HomeAssistantError, match="album is unchanged"):
        await _deactivate(hass)
