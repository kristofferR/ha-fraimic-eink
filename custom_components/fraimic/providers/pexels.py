"""Pexels — free stock photography. Requires a free API key.

Search by keyword or pull from the hourly-refreshed curated feed.
Attribution ("Photo by X on Pexels") is required by their guidelines.
"""

from __future__ import annotations

import random
from typing import Any

from .base import ArtCandidate, ArtFetchError, ArtProvider, FetchRequest, api_headers

SEARCH_URL = "https://api.pexels.com/v1/search"
CURATED_URL = "https://api.pexels.com/v1/curated"
API_TIMEOUT = 20.0


def parse_pexels_photo(item: dict) -> ArtCandidate | None:
    src = item.get("src") or {}
    image_url = src.get("original") or src.get("large2x")
    if not image_url:
        return None
    photographer = item.get("photographer") or "Unknown"
    title = (item.get("alt") or "Photo").strip().capitalize() or "Photo"
    return ArtCandidate(
        provider="pexels",
        item_id=str(item.get("id", "")),
        image_url=image_url,
        thumb_url=src.get("medium"),
        title=title,
        artist=photographer,
        license="Pexels License",
        attribution=f"Photo by {photographer} on Pexels",
        width=item.get("width"),
        height=item.get("height"),
    )


class PexelsProvider(ArtProvider):
    key = "pexels"
    name = "Pexels"
    requires_key = True
    key_option = "pexels_api_key"
    min_interval = 18.0  # 200 req/hr

    async def async_candidates(
        self, session: Any, cache: Any, request: FetchRequest, count: int
    ) -> list[ArtCandidate]:
        if not request.api_key:
            raise ArtFetchError("Pexels needs an API key (frame options)")
        orientation = (
            "landscape" if request.target_width >= request.target_height else "portrait"
        )
        if request.query:
            url = SEARCH_URL
            params = {
                "query": request.query,
                "orientation": orientation,
                "per_page": count,
                "page": 1,
            }
        else:
            url = CURATED_URL
            page = random.randint(1, 20)
            params = {"per_page": count, "page": page}
        await cache.async_throttle(self.key, self.min_interval)
        resp = await session.get(
            url,
            params=params,
            headers=api_headers({"Authorization": request.api_key}),
            timeout=API_TIMEOUT,
        )
        async with resp:
            if resp.status != 200:
                raise ArtFetchError(f"Pexels returned HTTP {resp.status}")
            payload = await resp.json()
        # Metadata dims describe the original; the ratio is what matters for
        # the pre-download check (delivered `large2x` is ~1880 px wide and the
        # post-download decode verifies actual size).
        return [
            candidate
            for item in payload.get("photos", [])
            if (candidate := parse_pexels_photo(item)) is not None
        ]
