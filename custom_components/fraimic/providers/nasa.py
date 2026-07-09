"""NASA Image and Video Library — open access, no key.

Search-driven (``query`` supported); without one, a random pick from a
curated space-theme pool keeps playlist rotation varied. Each search hit
lists its actually-available renditions with dims — pick the largest JPEG
from those. Rendition names are NOT uniform across assets (many lack
``~large``; guessing URLs 403s, verified live).
"""

from __future__ import annotations

import random
from typing import Any

from ..const import MAX_SOURCE_BYTES, MAX_SOURCE_PIXELS
from .base import ArtCandidate, ArtFetchError, ArtProvider, FetchRequest, api_headers
from .engine import async_fetch_json

SEARCH_URL = "https://images-api.nasa.gov/search"
API_TIMEOUT = 20.0
TOTAL_TTL = 24 * 3600
MAX_RESULT_WINDOW = 10_000  # the API errors on pages past 10k results

DEFAULT_QUERIES = (
    "nebula",
    "galaxy",
    "aurora borealis",
    "earth from space",
    "hubble telescope",
    "mars surface",
    "saturn",
    "jupiter",
    "apollo mission",
    "spacewalk",
    "milky way",
)

# Unknown-dims tie-break: NASA's conventional rendition ladder.
_RENDITION_RANK = {"orig": 4, "large": 3, "medium": 2, "small": 1}


def _rendition_rank(href: str) -> int:
    stem = href.rsplit("~", 1)[-1].rsplit(".", 1)[0].lower()
    return _RENDITION_RANK.get(stem, 0)


def parse_nasa_item(item: dict) -> ArtCandidate | None:
    data = (item.get("data") or [{}])[0] or {}
    nasa_id = data.get("nasa_id")
    if not nasa_id:
        return None
    best: tuple[tuple[int, int], dict] | None = None
    thumb_url = None
    for link in item.get("links") or []:
        href = (link.get("href") or "").strip()
        if not href.lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        if link.get("rel") == "preview":
            thumb_url = href
            continue
        width, height = link.get("width"), link.get("height")
        pixels = width * height if width and height else 0
        if pixels > MAX_SOURCE_PIXELS or (link.get("size") or 0) > MAX_SOURCE_BYTES:
            continue
        score = (pixels, _rendition_rank(href))
        if best is None or score > best[0]:
            best = (score, link)
    if best is None:
        return None
    link = best[1]
    title = data.get("title") or "NASA image"
    creator = data.get("secondary_creator") or data.get("photographer") or "NASA"
    return ArtCandidate(
        provider="nasa",
        item_id=str(nasa_id),
        image_url=link["href"],
        thumb_url=thumb_url,
        title=title,
        artist=creator,
        license="Public domain",
        attribution=f"{title} — NASA",
        width=link.get("width"),
        height=link.get("height"),
    )


class NasaImagesProvider(ArtProvider):
    key = "nasa"
    name = "NASA Image Library"
    min_interval = 1.0

    async def _search(
        self, session: Any, cache: Any, query: str, page: int, page_size: int
    ) -> dict:
        payload = await async_fetch_json(
            session,
            cache,
            key=self.key,
            min_interval=self.min_interval,
            url=SEARCH_URL,
            error_label="NASA image search",
            params={
                "q": query,
                "media_type": "image",
                "page": page,
                "page_size": page_size,
            },
            headers=api_headers(),
            timeout=API_TIMEOUT,
        )
        return payload.get("collection") or {}

    async def _total(self, session: Any, cache: Any, query: str) -> int:
        cache_key = f"nasa_total_{query}"
        total = cache.get(cache_key, TOTAL_TTL)
        if total is None:
            collection = await self._search(session, cache, query, 1, 1)
            total = (collection.get("metadata") or {}).get("total_hits") or 0
            if not total:
                raise ArtFetchError(f"NASA image search found nothing for {query!r}")
            cache.set(cache_key, total)
        return total

    async def async_candidates(
        self, session: Any, cache: Any, request: FetchRequest, count: int
    ) -> list[ArtCandidate]:
        query = request.query or random.choice(DEFAULT_QUERIES)
        total = await self._total(session, cache, query)
        page_size = min(max(count, 10), 100)
        max_page = max(1, min(total, MAX_RESULT_WINDOW) // page_size)
        collection = await self._search(
            session, cache, query, random.randint(1, max_page), page_size
        )
        candidates = [
            candidate
            for item in collection.get("items", [])
            if (candidate := parse_nasa_item(item)) is not None
        ]
        random.shuffle(candidates)
        return candidates[:count]

    async def async_by_id(
        self, session: Any, cache: Any, item_id: str, request: FetchRequest
    ) -> ArtCandidate:
        payload = await async_fetch_json(
            session,
            cache,
            key=self.key,
            min_interval=self.min_interval,
            url=SEARCH_URL,
            error_label=f"NASA image {item_id}",
            params={"nasa_id": item_id},
            headers=api_headers(),
            timeout=API_TIMEOUT,
        )
        items = (payload.get("collection") or {}).get("items") or []
        candidate = parse_nasa_item(items[0]) if items else None
        if candidate is None:
            raise ArtFetchError(f"NASA image {item_id} has no usable rendition")
        return candidate
