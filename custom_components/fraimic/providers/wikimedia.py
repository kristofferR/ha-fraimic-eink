"""Wikimedia Commons picture of the day (via the Wikipedia featured feed).

Originals can exceed 50 MB, so a sized thumbnail URL is derived from the
standard Commons thumb path. Licenses vary (often CC BY-SA) — attribution is
carried on every candidate and rendered when captions are on.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from .base import ArtCandidate, ArtProvider, FetchRequest, api_headers

FEED_URL = "https://api.wikimedia.org/feed/v1/wikipedia/en/featured/{y}/{m:02d}/{d:02d}"
FEED_TTL = 6 * 3600
API_TIMEOUT = 20.0
DAYS_BACK = 4  # today + previous days as retry material
STANDARD_THUMB_WIDTHS = (20, 40, 60, 120, 250, 330, 500, 960, 1280, 1920, 3840)

_THUMB_WIDTH_RE = re.compile(r"/(\d+)px-")


def standard_thumb_width(width: int) -> int:
    """Smallest Wikimedia standard thumbnail width that covers ``width``."""
    for standard in STANDARD_THUMB_WIDTHS:
        if standard >= width:
            return standard
    return STANDARD_THUMB_WIDTHS[-1]


def sized_thumb(thumb_url: str, width: int) -> str:
    """Rewrite a Commons thumb URL (`.../960px-Foo.jpg`) to another width."""
    return _THUMB_WIDTH_RE.sub(
        f"/{standard_thumb_width(width)}px-", thumb_url, count=1
    )


def parse_potd(payload: dict, date_key: str, target_width: int) -> ArtCandidate | None:
    image = payload.get("image") or {}
    thumb = (image.get("thumbnail") or {}).get("source")
    original = image.get("image") or {}
    if not thumb and not original.get("source"):
        return None
    # Prefer a ~1.5x-target-width thumbnail over the (possibly enormous)
    # original; fall back to the original when the URL shape is unexpected.
    if thumb and "px-" in thumb:
        image_url = sized_thumb(thumb, round(target_width * 1.5))
    else:
        image_url = original.get("source") or thumb
    artist = ((image.get("artist") or {}).get("text") or "").strip() or None
    license_type = (image.get("license") or {}).get("type")
    description = ((image.get("description") or {}).get("text") or "").strip()
    title = description or (image.get("title") or "Picture of the day").replace(
        "File:", ""
    )
    parts = [title]
    if artist:
        parts.append(artist)
    attribution = " — ".join(parts)
    if license_type:
        attribution += f" ({license_type})"
    return ArtCandidate(
        provider="wikimedia",
        item_id=date_key,
        image_url=image_url,
        thumb_url=thumb,
        title=title,
        artist=artist,
        license=license_type,
        attribution=attribution,
    )


class WikimediaProvider(ArtProvider):
    key = "wikimedia"
    name = "Wikimedia picture of the day"
    min_interval = 2.0

    async def _potd(
        self, session: Any, cache: Any, day: datetime, target_width: int
    ) -> ArtCandidate | None:
        date_key = day.strftime("%Y-%m-%d")
        cached = cache.get(f"wikimedia_{date_key}_{target_width}", FEED_TTL)
        if cached is not None:
            return cached or None  # cached "" means known-absent
        await cache.async_throttle(self.key, self.min_interval)
        resp = await session.get(
            FEED_URL.format(y=day.year, m=day.month, d=day.day),
            headers=api_headers(),
            timeout=API_TIMEOUT,
        )
        async with resp:
            if resp.status != 200:
                return None
            payload = await resp.json()
        candidate = parse_potd(payload, date_key, target_width)
        cache.set(f"wikimedia_{date_key}_{target_width}", candidate or "")
        return candidate

    async def async_candidates(
        self, session: Any, cache: Any, request: FetchRequest, count: int
    ) -> list[ArtCandidate]:
        now = datetime.now(timezone.utc)
        candidates = []
        for back in range(DAYS_BACK):
            candidate = await self._potd(
                session, cache, now - timedelta(days=back), request.target_width
            )
            if candidate is not None:
                candidates.append(candidate)
            if len(candidates) >= count:
                break
        return candidates
