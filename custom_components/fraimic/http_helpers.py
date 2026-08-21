"""Shared HTTP helpers for Fraimic panel views."""

from __future__ import annotations

from typing import Any

from aiohttp import web
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .helpers import loaded_fraimic_entries


def require_loaded_entry(hass: HomeAssistant, entry_id: Any) -> ConfigEntry:
    """Resolve one loaded Fraimic entry or reject the HTTP request."""
    entry = next(
        (
            candidate
            for candidate in loaded_fraimic_entries(hass)
            if candidate.entry_id == entry_id
        ),
        None,
    )
    if entry is None:
        raise web.HTTPBadRequest(text="Unknown or unloaded entry_id")
    return entry
