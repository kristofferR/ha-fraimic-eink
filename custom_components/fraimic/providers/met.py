"""The Metropolitan Museum of Art — open access, no key, CC0.

Highlights pool (isHighlight + hasImages) is cached 24 h; random object ids
are then fetched individually (many objects lack a usable primaryImage, so
the engine's retry budget matters here).
"""

from __future__ import annotations

import random
from typing import Any

from .base import ArtCandidate, ArtFetchError, ArtProvider, FetchRequest, api_headers

SEARCH_URL = (
    "https://collectionapi.metmuseum.org/public/collection/v1/search"
    "?hasImages=true&isHighlight=true&q=*"
)
OBJECT_URL = "https://collectionapi.metmuseum.org/public/collection/v1/objects/{id}"
POOL_TTL = 24 * 3600
API_TIMEOUT = 20.0


def parse_met_object(payload: dict) -> ArtCandidate | None:
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
    min_interval = 0.5

    async def _pool(self, session: Any, cache: Any) -> list[int]:
        pool = cache.get("met_ids", POOL_TTL)
        if pool is None:
            await cache.async_throttle(self.key, self.min_interval)
            resp = await session.get(
                SEARCH_URL, headers=api_headers(), timeout=API_TIMEOUT
            )
            async with resp:
                if resp.status != 200:
                    raise ArtFetchError(f"Met search returned HTTP {resp.status}")
                payload = await resp.json()
            pool = payload.get("objectIDs") or []
            if not pool:
                raise ArtFetchError("Met search returned no objects")
            cache.set("met_ids", pool)
        return pool

    async def async_candidates(
        self, session: Any, cache: Any, request: FetchRequest, count: int
    ) -> list[ArtCandidate]:
        pool = await self._pool(session, cache)
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

    async def _object(self, session: Any, cache: Any, object_id: int) -> ArtCandidate | None:
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
