"""Unsplash — high-quality photography by keyword. Requires a free API key.

Compliance per the Unsplash API guidelines: hotlink the returned ``urls``
(with imgix sizing params), fire the ``download_location`` ping when a photo
is actually displayed, and attribute "Photo by X on Unsplash".
source.unsplash.com is dead — never build URLs by hand.
"""

from __future__ import annotations

import logging
from typing import Any

from .base import ArtCandidate, ArtFetchError, ArtProvider, FetchRequest, api_headers

RANDOM_URL = "https://api.unsplash.com/photos/random"
API_TIMEOUT = 20.0

_LOGGER = logging.getLogger(__name__)


def parse_unsplash_photo(item: dict, target_width: int) -> ArtCandidate | None:
    urls = item.get("urls") or {}
    raw = urls.get("raw")
    if not raw:
        return None
    user = (item.get("user") or {}).get("name") or "Unknown"
    description = (
        item.get("description") or item.get("alt_description") or "Photo"
    ).strip().capitalize()
    separator = "&" if "?" in raw else "?"
    return ArtCandidate(
        provider="unsplash",
        item_id=item.get("id") or "",
        image_url=f"{raw}{separator}w={target_width}&fm=jpg&q=85",
        thumb_url=urls.get("small"),
        title=description,
        artist=user,
        license="Unsplash License",
        attribution=f"Photo by {user} on Unsplash",
        width=item.get("width"),
        height=item.get("height"),
        extra={"download_location": (item.get("links") or {}).get("download_location")},
    )


class UnsplashProvider(ArtProvider):
    key = "unsplash"
    name = "Unsplash"
    requires_key = True
    key_option = "unsplash_access_key"
    min_interval = 2.0  # demo tier: 50 req/hr

    def _headers(self, request: FetchRequest) -> dict[str, str]:
        return api_headers({"Authorization": f"Client-ID {request.api_key}"})

    async def async_candidates(
        self, session: Any, cache: Any, request: FetchRequest, count: int
    ) -> list[ArtCandidate]:
        if not request.api_key:
            raise ArtFetchError("Unsplash needs an API key (frame options)")
        orientation = (
            "landscape" if request.target_width >= request.target_height else "portrait"
        )
        params = {"count": count, "orientation": orientation}
        if request.query:
            params["query"] = request.query
        await cache.async_throttle(self.key, self.min_interval)
        resp = await session.get(
            RANDOM_URL,
            params=params,
            headers=self._headers(request),
            timeout=API_TIMEOUT,
        )
        async with resp:
            if resp.status != 200:
                raise ArtFetchError(f"Unsplash returned HTTP {resp.status}")
            payload = await resp.json()
        items = payload if isinstance(payload, list) else [payload]
        return [
            candidate
            for item in items
            if (candidate := parse_unsplash_photo(item, request.target_width * 2))
        ]

    async def async_on_display(
        self, session: Any, candidate: ArtCandidate, request: FetchRequest
    ) -> None:
        """Guideline-mandated download ping; failures only logged."""
        location = (candidate.extra or {}).get("download_location")
        if not location:
            return
        try:
            headers = api_headers(
                {"Authorization": f"Client-ID {request.api_key}"}
                if request.api_key
                else None
            )
            resp = await session.get(location, headers=headers, timeout=10)
            async with resp:
                await resp.read()
        except Exception as err:  # noqa: BLE001 - best-effort compliance ping
            _LOGGER.debug("Unsplash download ping failed: %s", err)
