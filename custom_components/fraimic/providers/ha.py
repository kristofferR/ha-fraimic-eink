"""Home Assistant wiring for the providers package.

The only provider module allowed to import Home Assistant. Wraps every
provider failure in an ``ArtFetchError(HomeAssistantError)`` so callers (the
playlist scheduler in particular) can distinguish "the online source is
having a moment" from "the frame is asleep".
"""

from __future__ import annotations

import asyncio
import io
import logging
import random
from dataclasses import replace

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from ..const import DOMAIN, PROVIDER_SHUFFLE
from . import MUSEUM_KEYS, available_provider_keys, get_provider
from .base import ArtFetchError as _BaseArtFetchError
from .base import ArtImage, BrowsePage, FetchRequest
from .cache import ProviderCache
from .engine import async_download_candidate, async_pick_and_download

_LOGGER = logging.getLogger(__name__)

BROWSE_STASH_TTL = 3600.0
BROWSE_STASH_LIMIT = 256
BROWSE_STASH_CACHE_LIMIT = 32
GALLERY_CACHE_TTL = 10 * 60.0
GALLERY_CACHE_LIMIT = 128
PROVIDER_CACHE_LIMIT = 128


class ArtFetchError(HomeAssistantError):
    """An online image source failed — the frame itself is fine."""


def _decode_dims(data: bytes) -> tuple[int, int]:
    from PIL import Image

    with Image.open(io.BytesIO(data)) as img:
        return img.size


def _cache(hass: HomeAssistant) -> ProviderCache:
    domain_data = hass.data.setdefault(DOMAIN, {})
    cache = domain_data.get("art_cache")
    if cache is None:
        cache = ProviderCache(max_entries=PROVIDER_CACHE_LIMIT)
        domain_data["art_cache"] = cache
    return cache


def _browse_cache(hass: HomeAssistant) -> ProviderCache:
    """Return the bounded cache for media-browser selections."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    cache = domain_data.get("art_browse_cache")
    if cache is None:
        cache = ProviderCache(max_entries=BROWSE_STASH_CACHE_LIMIT)
        domain_data["art_browse_cache"] = cache
    return cache


def _gallery_cache(hass: HomeAssistant) -> ProviderCache:
    """Short-lived result cache for the progressively loaded gallery."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    cache = domain_data.get("art_gallery_cache")
    if cache is None:
        cache = ProviderCache(max_entries=GALLERY_CACHE_LIMIT)
        domain_data["art_gallery_cache"] = cache
    return cache


def resolve_provider_key(entry, provider_key: str) -> str:
    """Resolve ``shuffle`` to a concrete available provider."""
    if provider_key != PROVIDER_SHUFFLE:
        return provider_key
    available = available_provider_keys(entry)
    if not available:
        raise ArtFetchError("No image providers are available")
    # Shuffle means "surprise me with art": prefer the museum pool; fall
    # back to anything available.
    museums = [key for key in available if key in MUSEUM_KEYS]
    return random.choice(museums or available)


async def async_fetch_art(
    hass: HomeAssistant,
    entry,
    provider_key: str,
    *,
    query: str | None = None,
    item_id: str | None = None,
    fit: str | None = None,
) -> ArtImage:
    """Fetch one curated online image for ``entry``'s frame."""
    from ..render.display import viewed_size

    key = resolve_provider_key(entry, provider_key)
    provider = get_provider(key)
    if provider is None:
        raise ArtFetchError(f"Unknown image provider: {key}")
    if provider.requires_key and not entry.options.get(provider.key_option or ""):
        raise ArtFetchError(f"{provider.name} needs an API key (see frame options)")

    session = async_get_clientsession(hass)
    cache = _cache(hass)
    width, height = viewed_size(entry)
    request = FetchRequest(
        target_width=width,
        target_height=height,
        query=query,
        api_key=entry.options.get(provider.key_option) if provider.key_option else None,
        fit=fit or "cover",
    )

    async def dims_of(data: bytes) -> tuple[int, int]:
        return await hass.async_add_executor_job(_decode_dims, data)

    try:
        if item_id is not None:
            candidate = await provider.async_by_id(session, cache, item_id, request)
            image = await async_download_candidate(provider, session, candidate)
        else:
            image = await async_pick_and_download(
                provider, session, cache, request, dims_of=dims_of
            )
    except _BaseArtFetchError as err:
        raise ArtFetchError(f"{provider.name}: {err}") from err
    except (aiohttp.ClientError, asyncio.TimeoutError) as err:
        raise ArtFetchError(f"{provider.name} is unreachable: {err}") from err
    except Exception as err:  # noqa: BLE001 - provider parser/decoder failures vary
        raise ArtFetchError(f"{provider.name}: {err}") from err
    return image


def _request_for(
    hass: HomeAssistant,
    entry,
    provider,
    *,
    query: str | None = None,
) -> FetchRequest:
    from ..render.display import viewed_size

    width, height = viewed_size(entry)
    return FetchRequest(
        target_width=width,
        target_height=height,
        query=query,
        api_key=entry.options.get(provider.key_option) if provider.key_option else None,
    )


def _browse_stash_key(entry, provider_key: str) -> str:
    return f"browse_{entry.entry_id}_{provider_key}"


def _stash_candidates(hass, entry, provider_key: str, candidates) -> None:
    cache = _browse_cache(hass)
    stash = cache.get(_browse_stash_key(entry, provider_key), BROWSE_STASH_TTL) or {}
    for candidate in candidates:
        # Refreshing an existing id should make it one of the newest entries.
        stash.pop(candidate.item_id, None)
        stash[candidate.item_id] = candidate
    if len(stash) > BROWSE_STASH_LIMIT:
        stash = dict(list(stash.items())[-BROWSE_STASH_LIMIT:])
    cache.set(_browse_stash_key(entry, provider_key), stash)


async def async_browse_candidates(
    hass: HomeAssistant,
    entry,
    provider_key: str,
    count: int = 20,
    *,
    query: str | None = None,
) -> list:
    """Fresh candidates for the media browser; stashed for later play-by-id."""
    provider = get_provider(provider_key)
    if provider is None:
        raise ArtFetchError(f"Unknown image provider: {provider_key}")
    normalized_query = (query or "").strip()
    result_key = (
        f"gallery_{entry.entry_id}_{provider_key}_{normalized_query.casefold()}"
    )
    result_cache = _gallery_cache(hass)
    cached_result = result_cache.get(result_key, GALLERY_CACHE_TTL)
    if isinstance(cached_result, dict):
        candidates = cached_result["candidates"]
        exhausted = cached_result["exhausted"]
    else:
        candidates = cached_result or []
        exhausted = False
    if len(candidates) < count and not exhausted:
        session = async_get_clientsession(hass)
        cache = _cache(hass)
        locks = hass.data.setdefault(DOMAIN, {}).setdefault("art_gallery_locks", {})
        lock_key = (entry.entry_id, provider_key)
        lock = locks.get(lock_key)
        if lock is None:
            lock = asyncio.Lock()
            locks[lock_key] = lock
        async with lock:
            cached_result = result_cache.get(result_key, GALLERY_CACHE_TTL)
            if isinstance(cached_result, dict):
                candidates = cached_result["candidates"]
                exhausted = cached_result["exhausted"]
            else:
                candidates = cached_result or []
                exhausted = False
            if len(candidates) < count and not exhausted:
                try:
                    fetched = await provider.async_candidates(
                        session,
                        cache,
                        _request_for(
                            hass, entry, provider, query=normalized_query or None
                        ),
                        count,
                    )
                except _BaseArtFetchError as err:
                    raise ArtFetchError(f"{provider.name}: {err}") from err
                except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                    raise ArtFetchError(
                        f"{provider.name} is unreachable: {err}"
                    ) from err
                except Exception as err:  # noqa: BLE001 - provider parser failures vary
                    raise ArtFetchError(f"{provider.name}: {err}") from err
                if normalized_query and not provider.supports_query:
                    needle = normalized_query.casefold()
                    fetched = [
                        candidate
                        for candidate in fetched
                        if needle
                        in " ".join(
                            filter(None, (candidate.title, candidate.artist))
                        ).casefold()
                    ]
                by_id = {candidate.item_id: candidate for candidate in candidates}
                for candidate in fetched:
                    by_id.setdefault(candidate.item_id, candidate)
                candidates = list(by_id.values())
                exhausted = not fetched
                result_cache.set(
                    result_key,
                    {"candidates": candidates, "exhausted": exhausted},
                )
    # Daily providers have no by-id lookup; the browse stash covers the gap
    # between browsing and clicking.
    _stash_candidates(hass, entry, provider_key, candidates)
    return candidates[:count]


async def async_browse_provider(
    hass: HomeAssistant, entry, provider_key: str, browse_id: str
) -> BrowsePage:
    """Browse one directory from a hierarchical provider and stash its art."""
    provider = get_provider(provider_key)
    if provider is None or not provider.hierarchical_browse:
        raise ArtFetchError(f"Unknown hierarchical image provider: {provider_key}")
    session = async_get_clientsession(hass)
    cache = _cache(hass)
    try:
        page = await provider.async_browse(
            session, cache, browse_id, _request_for(hass, entry, provider)
        )
    except _BaseArtFetchError as err:
        raise ArtFetchError(f"{provider.name}: {err}") from err
    except (aiohttp.ClientError, asyncio.TimeoutError) as err:
        raise ArtFetchError(f"{provider.name} is unreachable: {err}") from err
    except Exception as err:  # noqa: BLE001 - provider parser failures vary
        raise ArtFetchError(f"{provider.name}: {err}") from err
    _stash_candidates(hass, entry, provider_key, page.candidates)
    return page


async def async_candidate_by_media_id(
    hass: HomeAssistant, entry, provider_key: str, item_id: str
) -> object:
    """Resolve metadata for an item exposed by browse without downloading it."""
    provider = get_provider(provider_key)
    if provider is None:
        raise ArtFetchError(f"Unknown image provider: {provider_key}")
    session = async_get_clientsession(hass)
    cache = _cache(hass)
    stash = (
        _browse_cache(hass).get(
            _browse_stash_key(entry, provider_key), BROWSE_STASH_TTL
        )
        or {}
    )
    candidate = stash.get(item_id)
    try:
        if candidate is None:
            candidate = await provider.async_by_id(
                session, cache, item_id, _request_for(hass, entry, provider)
            )
    except _BaseArtFetchError as err:
        raise ArtFetchError(f"{provider.name}: {err}") from err
    except (aiohttp.ClientError, asyncio.TimeoutError) as err:
        raise ArtFetchError(f"{provider.name} is unreachable: {err}") from err
    except Exception as err:  # noqa: BLE001 - provider parser/decoder failures vary
        raise ArtFetchError(f"{provider.name}: {err}") from err
    _stash_candidates(hass, entry, provider_key, [candidate])
    return candidate


async def async_art_by_media_id(
    hass: HomeAssistant,
    entry,
    provider_key: str,
    item_id: str,
    *,
    thumbnail: bool = False,
) -> ArtImage:
    """Download the item a user clicked in the media browser."""
    provider = get_provider(provider_key)
    if provider is None:
        raise ArtFetchError(f"Unknown image provider: {provider_key}")
    candidate = await async_candidate_by_media_id(hass, entry, provider_key, item_id)
    download_candidate = (
        replace(candidate, image_url=candidate.thumb_url)
        if thumbnail and candidate.thumb_url
        else candidate
    )
    session = async_get_clientsession(hass)
    try:
        return await async_download_candidate(provider, session, download_candidate)
    except _BaseArtFetchError as err:
        raise ArtFetchError(f"{provider.name}: {err}") from err
    except (aiohttp.ClientError, asyncio.TimeoutError) as err:
        raise ArtFetchError(f"{provider.name} is unreachable: {err}") from err
    except Exception as err:  # noqa: BLE001 - provider decoder failures vary
        raise ArtFetchError(f"{provider.name}: {err}") from err


async def async_art_displayed(hass: HomeAssistant, entry, art: ArtImage) -> None:
    """Run provider display hooks after an image is actually uploaded."""
    provider = get_provider(art.candidate.provider)
    if provider is None:
        return
    session = async_get_clientsession(hass)
    await provider.async_on_display(
        session, art.candidate, _request_for(hass, entry, provider)
    )
