"""The Fraimic E-Ink Canvas integration."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import FraimicClient
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
from .coordinator import (
    FraimicConfigEntry,
    FraimicDataUpdateCoordinator,
    FraimicRuntimeData,
)
from .scheduler import FraimicScheduler
from .services import async_setup_services

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.IMAGE,
    Platform.MEDIA_PLAYER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: FraimicConfigEntry) -> bool:
    """Set up Fraimic from a config entry."""
    client = FraimicClient(entry.data[CONF_HOST], async_get_clientsession(hass))
    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    coordinator = FraimicDataUpdateCoordinator(hass, entry, client, scan_interval)
    # Do NOT use async_config_entry_first_refresh here: it raises
    # ConfigEntryNotReady on a failed first poll, which would abort setup whenever
    # the (battery-powered) frame is in deep sleep on restart — the entities would
    # then never be created. Instead refresh non-fatally and set up regardless, so
    # entities exist and show unavailable until the frame next wakes.
    await coordinator.async_refresh()

    entry.runtime_data = FraimicRuntimeData(coordinator, client)

    # Playlist scheduler for stored screens; started before the platforms so
    # the switch/select/button entities can see it. Subentry changes reload
    # the entry, rebuilding it with the fresh screen list.
    scheduler = FraimicScheduler(hass, entry)
    entry.runtime_data.scheduler = scheduler
    await scheduler.async_start()
    entry.async_on_unload(scheduler.async_stop)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    async_setup_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: FraimicConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: FraimicConfigEntry) -> None:
    """Reload the entry when options (e.g. poll interval) change."""
    await hass.config_entries.async_reload(entry.entry_id)
