"""Art Institute of Chicago — open access, no key, CC0 for public domain.

The boosted public-domain paintings pool (~120 certified masterpieces) is
sampled via a random page offset (the pool total is cached 24 h). The API
silently ignores Elasticsearch ``function_score``/``random_score`` — verified
live: three different seeds returned the identical order, so seed-based
randomisation always served the same painting.
Image delivery: IIIF at 1686 px (the public-domain maximum). The image CDN
requires a Referer header (hotlink protection) — verified live.
"""

from __future__ import annotations

import random
from typing import Any

from .base import ArtCandidate, ArtFetchError, ArtProvider, FetchRequest, api_headers
from .engine import async_fetch_json

SEARCH_URL = "https://api.artic.edu/api/v1/artworks/search"
IIIF_URL = "https://www.artic.edu/iiif/2/{image_id}/full/{size},/0/default.jpg"
FULL_SIZE = 1686  # public-domain maximum
THUMB_SIZE = 843
API_TIMEOUT = 20.0
POOL_TTL = 24 * 3600


def _search_body(limit: int, page: int = 1) -> dict:
    return {
        "query": {
            "bool": {
                "filter": [
                    {"term": {"is_public_domain": True}},
                    {"term": {"is_boosted": True}},
                    {"term": {"artwork_type_title.keyword": "Painting"}},
                ]
            }
        },
        "fields": "id,title,image_id,artist_display,thumbnail",
        "limit": limit,
        "page": page,
    }


def parse_aic_item(item: dict) -> ArtCandidate | None:
    image_id = item.get("image_id")
    if not image_id:
        return None
    title = item.get("title") or "Untitled"
    # artist_display is e.g. "Vincent van Gogh (Dutch, 1853–1890)\nSaint-Rémy"
    # — keep just the name for captions.
    artist = (
        (item.get("artist_display") or "").split("\n")[0].split(" (")[0].strip() or None
    )
    thumbnail = item.get("thumbnail") or {}
    width, height = thumbnail.get("width"), thumbnail.get("height")
    # Metadata dims are the master scan; scale to what IIIF will deliver.
    if width and height:
        scale = FULL_SIZE / width
        width, height = FULL_SIZE, round(height * scale)
    attribution = (
        f"{title} — {artist}, Art Institute of Chicago"
        if artist
        else f"{title}, Art Institute of Chicago"
    )
    return ArtCandidate(
        provider="aic",
        item_id=str(item.get("id", "")),
        image_url=IIIF_URL.format(image_id=image_id, size=FULL_SIZE),
        thumb_url=IIIF_URL.format(image_id=image_id, size=THUMB_SIZE),
        title=title,
        artist=artist,
        license="CC0",
        attribution=attribution,
        width=width,
        height=height,
    )


class AicProvider(ArtProvider):
    key = "aic"
    name = "Art Institute of Chicago"
    min_interval = 2.0  # 60 req/min anonymous limit

    def image_headers(self, candidate: ArtCandidate) -> dict[str, str]:
        # The IIIF CDN 403s requests without a Referer (verified live).
        return {
            "User-Agent": "Mozilla/5.0 (compatible; ha-fraimic-eink)",
            "Referer": "https://www.artic.edu/",
        }

    async def _total(self, session: Any, cache: Any) -> int:
        total = cache.get("aic_total", POOL_TTL)
        if total is None:
            payload = await async_fetch_json(
                session,
                cache,
                key=self.key,
                min_interval=self.min_interval,
                url=SEARCH_URL,
                method="post",
                error_label="AIC search",
                json=_search_body(limit=1),
                headers=api_headers({"AIC-User-Agent": api_headers()["User-Agent"]}),
                timeout=API_TIMEOUT,
            )
            total = (payload.get("pagination") or {}).get("total") or 0
            if not total:
                raise ArtFetchError("AIC returned an empty boosted-paintings pool")
            cache.set("aic_total", total)
        return total

    async def async_candidates(
        self, session: Any, cache: Any, request: FetchRequest, count: int
    ) -> list[ArtCandidate]:
        total = await self._total(session, cache)
        limit = count * 2
        page = random.randrange(max(1, -(-total // limit))) + 1
        payload = await async_fetch_json(
            session,
            cache,
            key=self.key,
            min_interval=self.min_interval,
            url=SEARCH_URL,
            method="post",
            error_label="AIC search",
            json=_search_body(limit=limit, page=page),
            headers=api_headers({"AIC-User-Agent": api_headers()["User-Agent"]}),
            timeout=API_TIMEOUT,
        )
        candidates = [
            candidate
            for item in payload.get("data", [])
            if (candidate := parse_aic_item(item)) is not None
        ]
        random.shuffle(candidates)
        return candidates[:count]

    async def async_by_id(
        self, session: Any, cache: Any, item_id: str, request: FetchRequest
    ) -> ArtCandidate:
        await cache.async_throttle(self.key, self.min_interval)
        resp = await session.get(
            f"https://api.artic.edu/api/v1/artworks/{item_id}"
            "?fields=id,title,image_id,artist_display,thumbnail",
            headers=api_headers({"AIC-User-Agent": api_headers()["User-Agent"]}),
            timeout=API_TIMEOUT,
        )
        async with resp:
            if resp.status != 200:
                raise ArtFetchError(f"AIC artwork {item_id}: HTTP {resp.status}")
            payload = await resp.json()
        candidate = parse_aic_item(payload.get("data") or {})
        if candidate is None:
            raise ArtFetchError(f"AIC artwork {item_id} has no image")
        return candidate
