"""Smithsonian Open Access — CC0 artworks via the api.data.gov EDAN search.

Works keyless through the shared ``DEMO_KEY`` (≈30 requests/hour per IP, so
demo results are cached hard, like APOD); a free api.data.gov key raises the
limit and can be set in the options. Zero-query default: American Art Museum
paintings. A ``query`` searches the whole image collection instead. Delivery
is the IDS service, which resizes via ``max=`` (verified live).
"""

from __future__ import annotations

import random
import re
from typing import Any
from urllib.parse import quote

from .base import ArtCandidate, ArtFetchError, ArtProvider, FetchRequest, api_headers
from .engine import async_fetch_json

SEARCH_URL = "https://api.si.edu/openaccess/api/v1.0/search"
CONTENT_URL = "https://api.si.edu/openaccess/api/v1.0/content/{id}"
IDS_URL = "https://ids.si.edu/ids/deliveryService?id={id}&max={size}"
FULL_SIZE = 3000
THUMB_SIZE = 640
DEFAULT_FILTER = 'unit_code:SAAM AND object_type:"Paintings" AND online_media_type:"Images"'
API_TIMEOUT = 20.0
COUNT_TTL = 24 * 3600
DEMO_KEY = "DEMO_KEY"
DEMO_CACHE_TTL = 30 * 60

# freetext names carry biography suffixes: "Spencer Nichols, born … 1875-died … 1950"
_NAME_SUFFIX = re.compile(r",\s*(?:born|died|active|ca\.|c\.)\b.*", re.IGNORECASE)


def parse_smithsonian_row(row: dict) -> ArtCandidate | None:
    content = row.get("content") or {}
    dnr = content.get("descriptiveNonRepeating") or {}
    record_id = dnr.get("record_ID")
    if not record_id:
        return None
    # The content endpoint resolves the EDAN url ("edanmdm:saam_1970.355.22"),
    # NOT the bare record_ID (404s, verified live). Rows carry it as "url".
    item_id = row.get("url") or f"edanmdm:{record_id}"
    ids_id = None
    for media in (dnr.get("online_media") or {}).get("media") or []:
        media = media or {}
        if (
            media.get("type") == "Images"
            and (media.get("usage") or {}).get("access") == "CC0"
            and media.get("idsId")
        ):
            ids_id = media["idsId"]
            break
    if not ids_id:
        return None
    title = (dnr.get("title") or {}).get("content") or row.get("title") or "Untitled"
    artist = None
    for name in (content.get("freetext") or {}).get("name") or []:
        raw = ((name or {}).get("content") or "").strip()
        if raw:
            artist = _NAME_SUFFIX.sub("", raw).strip() or None
            break
    source = dnr.get("data_source") or "Smithsonian"
    attribution = f"{title} — {artist}, {source}" if artist else f"{title}, {source}"
    encoded = quote(ids_id, safe="")
    return ArtCandidate(
        provider="smithsonian",
        item_id=str(item_id),
        image_url=IDS_URL.format(id=encoded, size=FULL_SIZE),
        thumb_url=IDS_URL.format(id=encoded, size=THUMB_SIZE),
        title=title,
        artist=artist,
        license="CC0",
        attribution=attribution,
    )


class SmithsonianProvider(ArtProvider):
    key = "smithsonian"
    name = "Smithsonian Open Access"
    key_option = "smithsonian_api_key"  # optional - DEMO_KEY works without it
    min_interval = 5.0

    @staticmethod
    def _query(request: FetchRequest) -> str:
        if request.query:
            return f'{request.query} AND online_media_type:"Images"'
        return DEFAULT_FILTER

    async def _search(
        self, session: Any, cache: Any, api_key: str, q: str, start: int, rows: int
    ) -> dict:
        payload = await async_fetch_json(
            session,
            cache,
            key=self.key,
            min_interval=self.min_interval,
            url=SEARCH_URL,
            error_label="Smithsonian search",
            params={"api_key": api_key, "q": q, "start": start, "rows": rows},
            headers=api_headers(),
            timeout=API_TIMEOUT,
        )
        return payload.get("response") or {}

    async def async_candidates(
        self, session: Any, cache: Any, request: FetchRequest, count: int
    ) -> list[ArtCandidate]:
        api_key = request.api_key or DEMO_KEY
        q = self._query(request)
        demo_cache_key = f"smithsonian_demo_{q}"
        if not request.api_key and (cached := cache.get(demo_cache_key, DEMO_CACHE_TTL)):
            return cached[:count]

        total_key = f"smithsonian_total_{q}"
        total = cache.get(total_key, COUNT_TTL)
        if total is None:
            response = await self._search(session, cache, api_key, q, 0, 1)
            total = response.get("rowCount") or 0
            if not total:
                raise ArtFetchError("Smithsonian search found no artworks")
            cache.set(total_key, total)

        rows = count * 2  # not every row carries a CC0 image
        start = random.randrange(max(1, total - rows + 1))
        response = await self._search(session, cache, api_key, q, start, rows)
        candidates = [
            candidate
            for row in response.get("rows", [])
            if (candidate := parse_smithsonian_row(row)) is not None
        ]
        random.shuffle(candidates)
        if not request.api_key and candidates:
            cache.set(demo_cache_key, candidates)
        return candidates[:count]

    async def async_by_id(
        self, session: Any, cache: Any, item_id: str, request: FetchRequest
    ) -> ArtCandidate:
        payload = await async_fetch_json(
            session,
            cache,
            key=self.key,
            min_interval=self.min_interval,
            url=CONTENT_URL.format(id=quote(item_id, safe="")),
            error_label=f"Smithsonian object {item_id}",
            params={"api_key": request.api_key or DEMO_KEY},
            headers=api_headers(),
            timeout=API_TIMEOUT,
        )
        candidate = parse_smithsonian_row(payload.get("response") or {})
        if candidate is None:
            raise ArtFetchError(f"Smithsonian object {item_id} has no CC0 image")
        return candidate
