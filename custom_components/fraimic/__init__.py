"""The Fraimic E-Ink Canvas integration."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import FraimicClient
from .art_packs import DATA_PACKS, ArtPackManager
from .artwork_cache import DATA_ARTWORK_CACHE, ArtworkCache
from .cloud import FraimicCloudClient
from .cloud_delivery import FraimicCloudDelivery
from .const import (
    CONF_CAMERA_INTERVAL,
    CONF_CLOUD_DEVICE_ID,
    CONF_CLOUD_EMAIL,
    CONF_CLOUD_PASSWORD,
    CONF_DELIVERY_MODE,
    CONF_HEIGHT,
    CONF_POWER_MODE,
    CONF_ROTATION,
    CONF_SCAN_INTERVAL,
    CONF_WIDTH,
    DEFAULT_ROTATION,
    DELIVERY_CLOUD,
    DOMAIN,
    POWER_MODE_RESPONSIVE,
    ROTATION_OPTIONS,
    canonical_frame_settings,
)
from .coordinator import (
    FraimicConfigEntry,
    FraimicDataUpdateCoordinator,
    FraimicRuntimeData,
)
from .helpers import loaded_fraimic_entries
from .http_api import async_register_views
from .library import DATA_LIBRARY, FraimicLibrary
from .overlays import DATA_OVERLAYS, OverlayManager
from .panel import async_register_panel, async_unregister_panel
from .playlists import DATA_PLAYLISTS, PlaylistManager
from .power import FraimicPowerManager, effective_scan_interval
from .scenes import DATA_SCENES, SceneManager
from .scheduled_events import DATA_SCHEDULED_EVENTS, ScheduledEventManager
from .scheduler import FraimicScheduler
from .send_queue import FraimicSendQueue
from .services import async_setup_services

_LOGGER = logging.getLogger(__name__)

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
    # Domain-wide singletons (shared by every frame): the media library and the
    # HTTP API. Created by whichever entry loads first.
    domain_data = hass.data.setdefault(DOMAIN, {})
    domain_lock = domain_data.setdefault("domain_setup_lock", asyncio.Lock())
    async with domain_lock:
        if DATA_ARTWORK_CACHE not in domain_data:
            artwork_cache = ArtworkCache(hass)
            await artwork_cache.async_setup()
            domain_data[DATA_ARTWORK_CACHE] = artwork_cache
        artwork_cache = domain_data[DATA_ARTWORK_CACHE]
        artwork_cache.schedule_cleanup(entry)
        if DATA_LIBRARY not in domain_data:
            library = FraimicLibrary(hass)
            await library.async_setup()
            domain_data[DATA_LIBRARY] = library
        library = domain_data[DATA_LIBRARY]
        if DATA_SCENES not in domain_data:
            scenes = SceneManager(hass, library)
            await scenes.async_setup()
            domain_data[DATA_SCENES] = scenes
        scenes = domain_data[DATA_SCENES]
        if DATA_PACKS not in domain_data:
            packs = ArtPackManager(hass, library, scenes)
            await packs.async_setup()
            domain_data[DATA_PACKS] = packs
        if DATA_SCHEDULED_EVENTS not in domain_data:
            scheduled = ScheduledEventManager(hass)
            await scheduled.async_setup()
            domain_data[DATA_SCHEDULED_EVENTS] = scheduled
        if DATA_PLAYLISTS not in domain_data:
            playlists = PlaylistManager(hass)
            await playlists.async_setup()
            domain_data[DATA_PLAYLISTS] = playlists
        playlists = domain_data[DATA_PLAYLISTS]
        if DATA_OVERLAYS not in domain_data:
            overlays = OverlayManager(hass)
            await overlays.async_setup()
            domain_data[DATA_OVERLAYS] = overlays
        await playlists.async_migrate_entry(entry)
        # The scene entity platform was removed (the panel replaced it); drop
        # the leftover virtual "Fraimic Scenes" device from older installs.
        device_registry = dr.async_get(hass)
        if stale := device_registry.async_get_device(
            identifiers={(DOMAIN, "fraimic_scenes")}
        ):
            device_registry.async_remove_device(stale.id)
    async_register_views(hass)
    await async_register_panel(hass)

    client = FraimicClient(entry.data[CONF_HOST], async_get_clientsession(hass))
    scan_interval = effective_scan_interval(dict(entry.options))

    coordinator = FraimicDataUpdateCoordinator(hass, entry, client, scan_interval)
    entry.runtime_data = FraimicRuntimeData(coordinator, client)
    power = FraimicPowerManager(hass, entry)
    entry.runtime_data.power = power
    await power.async_setup()
    entry.async_on_unload(power.shutdown)
    await coordinator.async_restore()
    # Cloud delivery (album schedule wakes the sleeping frame) when selected;
    # must exist before the scheduler starts so it can sync the album cadence.
    entry.runtime_data.cloud = await _async_setup_cloud(hass, entry)
    # Do NOT use async_config_entry_first_refresh here: it raises
    # ConfigEntryNotReady on a failed first poll, which would abort setup whenever
    # the (battery-powered) frame is in deep sleep on restart — the entities would
    # then never be created. Instead refresh non-fatally and set up regardless, so
    # entities exist and show unavailable until the frame next wakes.
    if power.startup_poll:
        await coordinator.async_refresh()

    # Queued delivery for sends that target a sleeping frame; resumes any
    # payload persisted before a restart.
    send_queue = FraimicSendQueue(hass, entry)
    entry.runtime_data.send_queue = send_queue
    await send_queue.async_setup()
    entry.async_on_unload(send_queue.shutdown)

    # Playlist scheduler for stored screens; started before the platforms so
    # the switch/select/button entities can see it. Subentry changes reload
    # the entry, rebuilding it with the fresh screen list.
    scheduler = FraimicScheduler(hass, entry, playlists)
    entry.runtime_data.scheduler = scheduler
    await scheduler.async_start()
    entry.async_on_unload(scheduler.async_stop)
    cloud = entry.runtime_data.cloud
    if cloud is not None and not cloud.has_image:
        # Nothing on the album yet, so the frame has no wake slot. Forget the
        # displayed hash so the next tick re-sends the current slide.
        scheduler.displayed_hash = None
    # Provider catalogs are cached in memory, so the first dashboard open after
    # a restart used to wait ~10 s for the slowest museum API. Warm them once.
    entry.async_create_background_task(
        hass, _async_warm_catalogs(hass, entry), "fraimic-warm-catalogs"
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    async_setup_services(hass)
    # The scheduler pre-renders only upcoming playlist pictures. A full library
    # sweep here used to compete with dashboard requests after every reload.
    return True


async def async_unload_entry(hass: HomeAssistant, entry: FraimicConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok and not loaded_fraimic_entries(hass):
        # Last frame gone: stop the library's background worker. The HTTP views
        # stay registered (aiohttp routes can't be removed) and answer 503.
        domain_data = hass.data.get(DOMAIN, {})
        scheduled = domain_data.pop(DATA_SCHEDULED_EVENTS, None)
        if scheduled is not None:
            scheduled.shutdown()
        domain_data.pop(DATA_PACKS, None)
        domain_data.pop(DATA_SCENES, None)
        domain_data.pop(DATA_PLAYLISTS, None)
        domain_data.pop(DATA_OVERLAYS, None)
        artwork_cache = domain_data.pop(DATA_ARTWORK_CACHE, None)
        if artwork_cache is not None:
            artwork_cache.shutdown()
        library = domain_data.pop(DATA_LIBRARY, None)
        if library is not None:
            await library.async_shutdown()
        async_unregister_panel(hass)
    return unload_ok


async def async_migrate_entry(hass: HomeAssistant, entry: FraimicConfigEntry) -> bool:
    """Keep existing installations responsive while new entries save battery."""
    options = dict(entry.options)
    if entry.version < 2:
        options.setdefault(CONF_POWER_MODE, POWER_MODE_RESPONSIVE)
        options.setdefault(CONF_SCAN_INTERVAL, 300)
        options.setdefault(CONF_CAMERA_INTERVAL, 1800)
        hass.config_entries.async_update_entry(entry, options=options, version=2)
    if entry.version < 3:
        data = dict(entry.data)
        width, height = data.get(CONF_WIDTH), data.get(CONF_HEIGHT)
        if isinstance(width, int) and isinstance(height, int):
            stored_rotation = options.get(CONF_ROTATION, DEFAULT_ROTATION)
            valid_rotation = (
                type(stored_rotation) is int and stored_rotation in ROTATION_OPTIONS
            )
            rotation = stored_rotation if valid_rotation else DEFAULT_ROTATION
            canonical_width, canonical_height, canonical_rotation = (
                canonical_frame_settings(width, height, rotation)
            )
            data[CONF_WIDTH], data[CONF_HEIGHT] = canonical_width, canonical_height
            if not valid_rotation or canonical_rotation != stored_rotation:
                options[CONF_ROTATION] = canonical_rotation
        hass.config_entries.async_update_entry(
            entry, data=data, options=options, version=3
        )
    return True


async def _async_setup_cloud(
    hass: HomeAssistant, entry: FraimicConfigEntry
) -> FraimicCloudDelivery | None:
    """Build cloud delivery for ``cloud`` mode; hand the frame back otherwise."""
    options = entry.options
    email = options.get(CONF_CLOUD_EMAIL)
    password = options.get(CONF_CLOUD_PASSWORD)
    device_id = options.get(CONF_CLOUD_DEVICE_ID)
    if not (email and password and device_id):
        if options.get(CONF_DELIVERY_MODE) == DELIVERY_CLOUD:
            _LOGGER.warning(
                "Cloud delivery is selected for %s but the account is incomplete; "
                "falling back to local delivery. Reconfigure the frame to sign in.",
                entry.title,
            )
        return None
    client = FraimicCloudClient(async_get_clientsession(hass), email, password)
    delivery = FraimicCloudDelivery(hass, entry, client, device_id)
    await delivery.async_setup()
    if options.get(CONF_DELIVERY_MODE) == DELIVERY_CLOUD:
        return delivery
    if delivery.album_id is not None or delivery.keep_awake_released:
        # Switched back to local delivery: stop the album and let the frame
        # keep awake again so LAN uploads reach it.
        if await delivery.async_release():
            await delivery.async_forget_album()
    return None


async def _async_update_listener(
    hass: HomeAssistant, entry: FraimicConfigEntry
) -> None:
    """Reload the entry when options (e.g. poll interval) change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_warm_catalogs(hass: HomeAssistant, entry: FraimicConfigEntry) -> None:
    """Fetch each online source's first gallery page into the shared caches."""
    from .providers import available_provider_keys
    from .providers.ha import async_browse_candidates

    for key in available_provider_keys(entry):
        try:
            await async_browse_candidates(hass, entry, key, 8)
        except Exception:
            _LOGGER.debug("Catalog warm-up for %s failed", key, exc_info=True)
