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

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from ..const import DOMAIN, PROVIDER_SHUFFLE
from . import MUSEUM_KEYS, available_provider_keys, get_provider
from .base import ArtImage, FetchRequest
from .base import ArtFetchError as _BaseArtFetchError
from .cache import ProviderCache
from .engine import async_download_candidate, async_pick_and_download

_LOGGER = logging.getLogger(__name__)


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
        cache = ProviderCache()
        domain_data["art_cache"] = cache
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
            return await async_download_candidate(provider, session, candidate)
        return await async_pick_and_download(
            provider, session, cache, request, dims_of=dims_of
        )
    except _BaseArtFetchError as err:
        raise ArtFetchError(f"{provider.name}: {err}") from err
    except (aiohttp.ClientError, asyncio.TimeoutError) as err:
        raise ArtFetchError(f"{provider.name} is unreachable: {err}") from err
