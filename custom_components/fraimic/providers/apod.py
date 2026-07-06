"""NASA Astronomy Picture of the Day.

Works keyless via DEMO_KEY (50 requests/day — plenty for a frame); a free
api.nasa.gov key raises the limit and can be set in the options. ``count=N``
returns random archive picks, which suits art rotation better than strictly
"today" (and many days are videos, which are filtered out).
"""

from __future__ import annotations

from typing import Any

from .base import ArtCandidate, ArtFetchError, ArtProvider, FetchRequest, api_headers

APOD_URL = "https://api.nasa.gov/planetary/apod"
API_TIMEOUT = 20.0
DEMO_KEY = "DEMO_KEY"


def parse_apod_items(payload: list | dict) -> list[ArtCandidate]:
    items = payload if isinstance(payload, list) else [payload]
    candidates = []
    for item in items:
        if item.get("media_type") != "image":
            continue
        image_url = item.get("hdurl") or item.get("url")
        if not image_url:
            continue
        title = item.get("title") or "Astronomy Picture of the Day"
        copyright_text = (item.get("copyright") or "").strip()
        attribution = f"{title} — NASA APOD" + (
            f" © {copyright_text}" if copyright_text else ""
        )
        candidates.append(
            ArtCandidate(
                provider="apod",
                item_id=item.get("date") or title,
                image_url=image_url,
                thumb_url=item.get("url"),
                title=title,
                artist=copyright_text or "NASA",
                license="Public domain" if not copyright_text else "©",
                attribution=attribution,
            )
        )
    return candidates


class ApodProvider(ArtProvider):
    key = "apod"
    name = "NASA APOD"
    key_option = "nasa_api_key"  # optional - DEMO_KEY works without it
    min_interval = 2.0  # DEMO_KEY: 30/hr - stay well under

    async def async_candidates(
        self, session: Any, cache: Any, request: FetchRequest, count: int
    ) -> list[ArtCandidate]:
        api_key = request.api_key or DEMO_KEY
        await cache.async_throttle(self.key, self.min_interval)
        resp = await session.get(
            f"{APOD_URL}?api_key={api_key}&count={max(count, 4)}",
            headers=api_headers(),
            timeout=API_TIMEOUT,
        )
        async with resp:
            if resp.status != 200:
                raise ArtFetchError(f"NASA APOD returned HTTP {resp.status}")
            payload = await resp.json()
        candidates = parse_apod_items(payload)
        if not candidates:
            raise ArtFetchError("NASA APOD returned only non-image entries")
        return candidates[:count]
