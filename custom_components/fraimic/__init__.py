"""The Fraimic E-Ink Canvas integration."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import FraimicClient
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN
from .coordinator import (
    FraimicConfigEntry,
    FraimicDataUpdateCoordinator,
    FraimicRuntimeData,
)
from .helpers import loaded_fraimic_entries
from .http_api import async_register_views
from .library import DATA_LIBRARY, FraimicLibrary
from .scenes import DATA_SCENES, SceneManager
from .scheduler import FraimicScheduler
from .services import async_setup_services

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.IMAGE,
    Platform.MEDIA_PLAYER,
    Platform.SCENE,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: FraimicConfigEntry) -> bool:
    """Set up Fraimic from a config entry."""
    # Domain-wide singletons (shared by every frame): the media library and the
    # HTTP API. Created by whichever entry loads first.
    domain_data = hass.data.setdefault(DOMAIN, {})
    if DATA_LIBRARY not in domain_data:
        library = FraimicLibrary(hass)
        await library.async_setup()
        domain_data[DATA_LIBRARY] = library
    if DATA_SCENES not in domain_data:
        scenes = SceneManager(hass, domain_data[DATA_LIBRARY])
        await scenes.async_setup()
        domain_data[DATA_SCENES] = scenes
    async_register_views(hass)

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
    # Pre-render the library's default variants for this frame in the background.
    domain_data[DATA_LIBRARY].schedule_full_backfill()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: FraimicConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok and not loaded_fraimic_entries(hass):
        # Last frame gone: stop the library's background worker. The HTTP views
        # stay registered (aiohttp routes can't be removed) and answer 503.
        domain_data = hass.data.get(DOMAIN, {})
        domain_data.pop(DATA_SCENES, None)
        library = domain_data.pop(DATA_LIBRARY, None)
        if library is not None:
            await library.async_shutdown()
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: FraimicConfigEntry) -> None:
    """Reload the entry when options (e.g. poll interval) change."""
    await hass.config_entries.async_reload(entry.entry_id)
