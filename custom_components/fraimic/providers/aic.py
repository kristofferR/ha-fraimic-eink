"""Art Institute of Chicago — open access, no key, CC0 for public domain.

The boosted public-domain paintings pool (~120 certified masterpieces) is
queried with a fresh random seed per call via Elasticsearch function_score.
Image delivery: IIIF at 1686 px (the public-domain maximum). The image CDN
requires a Referer header (hotlink protection) — verified live.
"""

from __future__ import annotations

import random
from typing import Any

from .base import ArtCandidate, ArtFetchError, ArtProvider, FetchRequest, api_headers

SEARCH_URL = "https://api.artic.edu/api/v1/artworks/search"
IIIF_URL = "https://www.artic.edu/iiif/2/{image_id}/full/{size},/0/default.jpg"
FULL_SIZE = 1686  # public-domain maximum
THUMB_SIZE = 843
API_TIMEOUT = 20.0


def _search_body(seed: int, limit: int) -> dict:
    return {
        "query": {
            "function_score": {
                "query": {
                    "bool": {
                        "filter": [
                            {"term": {"is_public_domain": True}},
                            {"term": {"is_boosted": True}},
                            {"term": {"artwork_type_title.keyword": "Painting"}},
                        ]
                    }
                },
                "boost_mode": "replace",
                # NOTE: must not be an empty object — the API's PHP layer
                # turns {} into [] and Elasticsearch rejects it.
                "random_score": {"seed": seed, "field": "id"},
            }
        },
        "fields": "id,title,image_id,artist_display,thumbnail",
        "limit": limit,
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

    async def async_candidates(
        self, session: Any, cache: Any, request: FetchRequest, count: int
    ) -> list[ArtCandidate]:
        await cache.async_throttle(self.key, self.min_interval)
        resp = await session.post(
            SEARCH_URL,
            json=_search_body(random.randrange(1_000_000), count * 2),
            headers=api_headers({"AIC-User-Agent": api_headers()["User-Agent"]}),
            timeout=API_TIMEOUT,
        )
        async with resp:
            if resp.status != 200:
                raise ArtFetchError(f"AIC search returned HTTP {resp.status}")
            payload = await resp.json()
        candidates = [
            candidate
            for item in payload.get("data", [])
            if (candidate := parse_aic_item(item)) is not None
        ]
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
