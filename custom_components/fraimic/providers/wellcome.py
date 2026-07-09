"""Wellcome Collection — open access, no key, CC-BY/CC0 images via IIIF.

Art, botanical/natural-history illustration, anatomical drawings, maps —
strong on exactly the flat, graphic material the Spectra 6 palette renders
well. The catalogue images API is keyless and query-driven; random picks
come from a random page of the result set. ``query`` supported.
"""

from __future__ import annotations

import random
from typing import Any

from .base import ArtCandidate, ArtFetchError, ArtProvider, FetchRequest, api_headers
from .engine import async_fetch_json

SEARCH_URL = "https://api.wellcomecollection.org/catalogue/v2/images"
ITEM_URL = "https://api.wellcomecollection.org/catalogue/v2/images/{id}"
IIIF_SUFFIX = "/full/!2400,2400/0/default.jpg"
API_TIMEOUT = 20.0
TOTAL_TTL = 24 * 3600
MAX_RESULT_WINDOW = 10_000  # the API rejects pages past 10k results

DEFAULT_QUERIES = (
    "painting",
    "botanical illustration",
    "watercolour landscape",
    "natural history illustration",
    "astronomy",
    "japanese print",
    "anatomical drawing",
    "portrait oil",
)


def parse_wellcome_image(item: dict) -> ArtCandidate | None:
    image_id = item.get("id")
    locations = item.get("locations") or []
    info_url = (locations[0] or {}).get("url") if locations else None
    if not image_id or not info_url or not info_url.endswith("/info.json"):
        return None
    iiif_base = info_url.removesuffix("/info.json")
    source = item.get("source") or {}
    # Titles are often "M0001404: Botanical illustration of ..." — drop the ref.
    title = (source.get("title") or "Untitled").split(": ", 1)[-1].strip() or "Untitled"
    artist = None
    for contributor in source.get("contributors") or []:
        label = ((contributor or {}).get("agent") or {}).get("label")
        if label:
            artist = label
            break
    license_label = ((locations[0] or {}).get("license") or {}).get("label")
    attribution = (
        f"{title} — {artist}, Wellcome Collection"
        if artist
        else f"{title} — Wellcome Collection"
    )
    if license_label:
        attribution += f" ({license_label.split(' (')[0]})"
    return ArtCandidate(
        provider="wellcome",
        item_id=str(image_id),
        image_url=f"{iiif_base}{IIIF_SUFFIX}",
        thumb_url=f"{iiif_base}/full/!600,600/0/default.jpg",
        title=title,
        artist=artist,
        license=license_label,
        attribution=attribution,
    )


class WellcomeProvider(ArtProvider):
    key = "wellcome"
    name = "Wellcome Collection"
    min_interval = 1.0

    async def _search(
        self, session: Any, cache: Any, query: str, page: int, page_size: int
    ) -> dict:
        return await async_fetch_json(
            session,
            cache,
            key=self.key,
            min_interval=self.min_interval,
            url=SEARCH_URL,
            error_label="Wellcome search",
            params={
                "query": query,
                "page": page,
                "pageSize": page_size,
                "include": "source.contributors",
            },
            headers=api_headers(),
            timeout=API_TIMEOUT,
        )

    async def _total(self, session: Any, cache: Any, query: str) -> int:
        cache_key = f"wellcome_total_{query}"
        total = cache.get(cache_key, TOTAL_TTL)
        if total is None:
            payload = await self._search(session, cache, query, 1, 1)
            total = payload.get("totalResults") or 0
            if not total:
                raise ArtFetchError(f"Wellcome found no images for {query!r}")
            cache.set(cache_key, total)
        return total

    async def async_candidates(
        self, session: Any, cache: Any, request: FetchRequest, count: int
    ) -> list[ArtCandidate]:
        query = request.query or random.choice(DEFAULT_QUERIES)
        total = await self._total(session, cache, query)
        page_size = min(max(count, 10), 100)
        max_page = max(1, min(total, MAX_RESULT_WINDOW) // page_size)
        payload = await self._search(
            session, cache, query, random.randint(1, max_page), page_size
        )
        candidates = [
            candidate
            for item in payload.get("results", [])
            if (candidate := parse_wellcome_image(item)) is not None
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
            url=ITEM_URL.format(id=item_id),
            error_label=f"Wellcome image {item_id}",
            params={"include": "source.contributors"},
            headers=api_headers(),
            timeout=API_TIMEOUT,
        )
        candidate = parse_wellcome_image(payload)
        if candidate is None:
            raise ArtFetchError(f"Wellcome image {item_id} has no IIIF location")
        return candidate
