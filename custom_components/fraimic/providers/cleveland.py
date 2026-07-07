"""Cleveland Museum of Art — open access, no key, CC0.

Small highlight pool (~60 CC0 paintings); random offset into the list.
``images.print`` is the 3400 px tier (``full`` is TIFF — never use it).
"""

from __future__ import annotations

import random
from typing import Any

from .base import ArtCandidate, ArtFetchError, ArtProvider, FetchRequest, api_headers
from .engine import async_fetch_json

LIST_URL = (
    "https://openaccess-api.clevelandart.org/api/artworks/"
    "?cc0=1&has_image=1&highlight=1&type=Painting"
)
ITEM_URL = "https://openaccess-api.clevelandart.org/api/artworks/{id}"
COUNT_TTL = 24 * 3600
API_TIMEOUT = 20.0


def parse_cleveland_item(item: dict) -> ArtCandidate | None:
    images = item.get("images") or {}
    print_tier = images.get("print") or {}
    image_url = print_tier.get("url")
    if not image_url:
        return None
    title = item.get("title") or "Untitled"
    artist = None
    for creator in item.get("creators") or []:
        description = (creator or {}).get("description") or ""
        if description:
            # "Vincent van Gogh (Dutch, 1853–1890)" -> name only.
            artist = description.split(" (")[0].strip()
            break

    def _dim(value) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    attribution = (
        f"{title} — {artist}, Cleveland Museum of Art"
        if artist
        else f"{title}, Cleveland Museum of Art"
    )
    return ArtCandidate(
        provider="cleveland",
        item_id=str(item.get("id", "")),
        image_url=image_url,
        thumb_url=(images.get("web") or {}).get("url"),
        title=title,
        artist=artist,
        license="CC0",
        attribution=attribution,
        width=_dim(print_tier.get("width")),
        height=_dim(print_tier.get("height")),
    )


class ClevelandProvider(ArtProvider):
    key = "cleveland"
    name = "Cleveland Museum of Art"
    min_interval = 1.0

    async def _total(self, session: Any, cache: Any) -> int:
        total = cache.get("cleveland_total", COUNT_TTL)
        if total is None:
            payload = await async_fetch_json(
                session,
                cache,
                key=self.key,
                min_interval=self.min_interval,
                url=f"{LIST_URL}&limit=1",
                error_label="Cleveland list",
                headers=api_headers(),
                timeout=API_TIMEOUT,
            )
            total = (payload.get("info") or {}).get("total") or 0
            if not total:
                raise ArtFetchError("Cleveland returned an empty highlight pool")
            cache.set("cleveland_total", total)
        return total

    async def async_candidates(
        self, session: Any, cache: Any, request: FetchRequest, count: int
    ) -> list[ArtCandidate]:
        total = await self._total(session, cache)
        skip = random.randrange(max(1, total - count + 1))
        await cache.async_throttle(self.key, self.min_interval)
        resp = await session.get(
            f"{LIST_URL}&limit={count}&skip={skip}",
            headers=api_headers(),
            timeout=API_TIMEOUT,
        )
        async with resp:
            if resp.status != 200:
                raise ArtFetchError(f"Cleveland list returned HTTP {resp.status}")
            payload = await resp.json()
        candidates = [
            candidate
            for item in payload.get("data", [])
            if (candidate := parse_cleveland_item(item)) is not None
        ]
        random.shuffle(candidates)
        return candidates

    async def async_by_id(
        self, session: Any, cache: Any, item_id: str, request: FetchRequest
    ) -> ArtCandidate:
        payload = await async_fetch_json(
            session,
            cache,
            key=self.key,
            min_interval=self.min_interval,
            url=ITEM_URL.format(id=item_id),
            error_label=f"Cleveland artwork {item_id}",
            headers=api_headers(),
            timeout=API_TIMEOUT,
        )
        candidate = parse_cleveland_item(payload.get("data") or {})
        if candidate is None:
            raise ArtFetchError(f"Cleveland artwork {item_id} has no print image")
        return candidate
