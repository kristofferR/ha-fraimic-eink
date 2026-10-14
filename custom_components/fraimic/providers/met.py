"""The Metropolitan Museum of Art — open access, no key, CC0.

Highlights pool (isHighlight + hasImages) is cached 24 h; random object ids
are then fetched individually (many objects lack a usable primaryImage, so
the engine's retry budget matters here).

Search uses ``/public/collection/v1.1/search``. ``/v1/search`` was retired on
2026-10-01 and now returns HTTP 410. v1.1 keeps the same filters and returns
one page (``offset``/``limit``; default 100, maximum 500). The first page is
the pool random picks are drawn from.
"""

from __future__ import annotations

import random
from typing import Any
from urllib.parse import quote_plus

from .base import ArtCandidate, ArtFetchError, ArtProvider, FetchRequest, api_headers
from .engine import async_fetch_json

SEARCH_URL = "https://collectionapi.metmuseum.org/public/collection/v1.1/search"
OBJECT_URL = "https://collectionapi.metmuseum.org/public/collection/v1/objects/{id}"
# Largest page v1.1 will return. One page replaces the retired v1 response,
# which listed every matching id.
PAGE_LIMIT = 500
POOL_TTL = 24 * 3600
API_TIMEOUT = 20.0


def _search_url(term: str, *, offset: int = 0, limit: int = PAGE_LIMIT) -> str:
    """One page of highlight object ids that have images."""
    return (
        f"{SEARCH_URL}?hasImages=true&isHighlight=true"
        f"&q={quote_plus(term)}&offset={offset}&limit={limit}"
    )


def parse_met_object(payload: dict[str, Any]) -> ArtCandidate | None:
    """Build a candidate from a /objects/{id} payload, or None if unusable."""
    if not payload.get("isPublicDomain"):
        return None
    image_url = payload.get("primaryImage") or ""
    if not image_url:
        return None
    title = payload.get("title") or "Untitled"
    artist = payload.get("artistDisplayName") or None
    attribution = f"{title} — {artist}, The Met" if artist else f"{title}, The Met"
    return ArtCandidate(
        provider="met",
        item_id=str(payload.get("objectID", "")),
        image_url=image_url,
        thumb_url=payload.get("primaryImageSmall") or None,
        title=title,
        artist=artist,
        license="CC0",
        attribution=attribution,
    )


class MetProvider(ArtProvider):
    key = "met"
    name = "The Met"
    supports_query = True
    min_interval = 0.5

    async def _pool(
        self, session: Any, cache: Any, query: str | None = None
    ) -> list[int]:
        term = (query or "*").strip() or "*"
        cache_key = f"met_ids_{term.casefold()}"
        pool: list[int] | None = cache.get(cache_key, POOL_TTL)
        if pool is None:
            payload = await async_fetch_json(
                session,
                cache,
                key=self.key,
                min_interval=self.min_interval,
                url=_search_url(term),
                error_label="Met search",
                headers=api_headers(),
                timeout=API_TIMEOUT,
            )
            # v1.1 returns the requested page only; ``total`` is the full count.
            pool = payload.get("objectIDs") or []
            if not pool and not query:
                raise ArtFetchError("Met search returned no objects")
            cache.set(cache_key, pool)
        return pool

    async def async_candidates(
        self, session: Any, cache: Any, request: FetchRequest, count: int
    ) -> list[ArtCandidate]:
        pool = await self._pool(session, cache, request.query)
        candidates: list[ArtCandidate] = []
        # Object lookups are individually cheap but many lack images; probe
        # up to 2x count random ids.
        for object_id in random.sample(pool, min(len(pool), count * 2)):
            if len(candidates) >= count:
                break
            candidate = await self._object(session, cache, object_id)
            if candidate is not None:
                candidates.append(candidate)
        return candidates

    async def _object(
        self, session: Any, cache: Any, object_id: int
    ) -> ArtCandidate | None:
        await cache.async_throttle(self.key, self.min_interval)
        resp = await session.get(
            OBJECT_URL.format(id=object_id), headers=api_headers(), timeout=API_TIMEOUT
        )
        async with resp:
            if resp.status != 200:
                return None
            return parse_met_object(await resp.json())

    async def async_by_id(
        self, session: Any, cache: Any, item_id: str, request: FetchRequest
    ) -> ArtCandidate:
        candidate = await self._object(session, cache, int(item_id))
        if candidate is None:
            raise ArtFetchError(f"Met object {item_id} has no usable image")
        return candidate
