"""Bing image of the day (unofficial endpoint; personal use only).

Stable for over a decade but undocumented by Microsoft — failures degrade
gracefully like any other provider. The returned 1920x1080 URL is rewritten
to the UHD (3840x2160) variant.
"""

from __future__ import annotations

from typing import Any

from .base import ArtCandidate, ArtFetchError, ArtProvider, FetchRequest, api_headers

ARCHIVE_URL = "https://www.bing.com/HPImageArchive.aspx?format=js&idx=0&n=8&mkt=en-US"
BASE = "https://www.bing.com"
ARCHIVE_TTL = 6 * 3600
API_TIMEOUT = 20.0


def parse_bing_archive(payload: dict) -> list[ArtCandidate]:
    candidates = []
    for image in payload.get("images", []):
        urlbase = image.get("urlbase")
        if not urlbase:
            continue
        title = image.get("title") or "Bing image of the day"
        copyright_text = image.get("copyright") or ""
        candidates.append(
            ArtCandidate(
                provider="bing",
                item_id=image.get("startdate") or urlbase,
                image_url=f"{BASE}{urlbase}_UHD.jpg",
                thumb_url=f"{BASE}{urlbase}_1280x720.jpg",
                title=title,
                license="Personal use",
                attribution=copyright_text or title,
                width=3840,
                height=2160,
            )
        )
    return candidates


class BingProvider(ArtProvider):
    key = "bing"
    name = "Bing image of the day"
    min_interval = 1.0

    async def async_candidates(
        self, session: Any, cache: Any, request: FetchRequest, count: int
    ) -> list[ArtCandidate]:
        candidates = cache.get("bing_archive", ARCHIVE_TTL)
        if candidates is None:
            await cache.async_throttle(self.key, self.min_interval)
            resp = await session.get(
                ARCHIVE_URL, headers=api_headers(), timeout=API_TIMEOUT
            )
            async with resp:
                if resp.status != 200:
                    raise ArtFetchError(f"Bing archive returned HTTP {resp.status}")
                payload = await resp.json(content_type=None)
            candidates = parse_bing_archive(payload)
            cache.set("bing_archive", candidates)
        return candidates[:count]
