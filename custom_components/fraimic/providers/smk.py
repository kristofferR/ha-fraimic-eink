"""SMK — National Gallery of Denmark — open access, no key.

Public-domain paintings pool (~4600); random offset into the search list
(Cleveland-style). Images are IIIF JP2 masters whose natives run 100+ MB —
always request a sized JPEG tier, never ``image_native``.
"""

from __future__ import annotations

import random
from typing import Any

from .base import ArtCandidate, ArtFetchError, ArtProvider, FetchRequest, api_headers
from .engine import async_fetch_json

SEARCH_URL = (
    "https://api.smk.dk/api/v1/art/search/?keys=*"
    "&filters=[has_image:true],[public_domain:true],[object_names:maleri]"
)
ITEM_URL = "https://api.smk.dk/api/v1/art?object_number={id}"
FULL_SIZE = 2400  # IIIF long-edge cap; the server never upscales past native
COUNT_TTL = 24 * 3600
API_TIMEOUT = 20.0


def parse_smk_item(item: dict) -> ArtCandidate | None:
    iiif_id = item.get("image_iiif_id")
    object_number = item.get("object_number")
    if not iiif_id or not object_number:
        return None
    titles = item.get("titles") or []
    title = ((titles[0] or {}).get("title") if titles else None) or "Untitled"
    artist = None
    for production in item.get("production") or []:
        production = production or {}
        forename = production.get("creator_forename")
        surname = production.get("creator_surname")
        # "creator" is surname-first ("Ballin, Mogens") — prefer the parts.
        artist = (
            f"{forename} {surname}" if forename and surname else production.get("creator")
        )
        if artist:
            break
    width, height = item.get("image_width"), item.get("image_height")
    if width and height:
        scale = min(FULL_SIZE / width, FULL_SIZE / height, 1.0)
        width, height = round(width * scale), round(height * scale)
    else:
        width = height = None
    attribution = (
        f"{title} — {artist}, SMK Copenhagen"
        if artist
        else f"{title}, SMK Copenhagen"
    )
    return ArtCandidate(
        provider="smk",
        item_id=str(object_number),
        image_url=f"{iiif_id}/full/!{FULL_SIZE},{FULL_SIZE}/0/default.jpg",
        thumb_url=item.get("image_thumbnail"),
        title=title,
        artist=artist,
        license="Public domain",
        attribution=attribution,
        width=width,
        height=height,
    )


class SmkProvider(ArtProvider):
    key = "smk"
    name = "SMK (National Gallery of Denmark)"
    min_interval = 1.0

    async def _total(self, session: Any, cache: Any) -> int:
        total = cache.get("smk_total", COUNT_TTL)
        if total is None:
            payload = await async_fetch_json(
                session,
                cache,
                key=self.key,
                min_interval=self.min_interval,
                url=f"{SEARCH_URL}&offset=0&rows=1",
                error_label="SMK search",
                headers=api_headers(),
                timeout=API_TIMEOUT,
            )
            total = payload.get("found") or 0
            if not total:
                raise ArtFetchError("SMK returned an empty painting pool")
            cache.set("smk_total", total)
        return total

    async def async_candidates(
        self, session: Any, cache: Any, request: FetchRequest, count: int
    ) -> list[ArtCandidate]:
        total = await self._total(session, cache)
        offset = random.randrange(max(1, total - count + 1))
        payload = await async_fetch_json(
            session,
            cache,
            key=self.key,
            min_interval=self.min_interval,
            url=f"{SEARCH_URL}&offset={offset}&rows={count}",
            error_label="SMK search",
            headers=api_headers(),
            timeout=API_TIMEOUT,
        )
        candidates = [
            candidate
            for item in payload.get("items", [])
            if (candidate := parse_smk_item(item)) is not None
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
            error_label=f"SMK artwork {item_id}",
            headers=api_headers(),
            timeout=API_TIMEOUT,
        )
        items = payload.get("items") or []
        candidate = parse_smk_item(items[0]) if items else None
        if candidate is None:
            raise ArtFetchError(f"SMK artwork {item_id} has no usable image")
        return candidate
