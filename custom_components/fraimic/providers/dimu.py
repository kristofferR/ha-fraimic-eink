"""Nasjonalmuseet via DigitaltMuseum — CC0 metadata, no key.

Nasjonalmuseet retired their own Collection API in January 2025; their
official guidance is the DigitaltMuseum (KulturIT) Solr API, which carries
the museum's collection (owner ``NMK-B``, ~5000 paintings with images) plus
250+ other Norwegian/Swedish museums. The documented test key ``demo``
works; it caps ``rows`` at 10 per request — plenty for the engine's
candidate budget.

Zero-query default: Nasjonalmuseet paintings, randomised server-side via
Solr's ``random_<seed>`` sort. A ``query`` searches fine art across all of
DigitaltMuseum instead (e.g. ``Munch``, ``Sohlberg``, ``vinter``).

Image delivery (verified live): ``dimension=max`` caps at 1200 px and is
served at a much lower bitrate than an explicit ``dimension=1200x1200`` —
request the latter for the best source quality at the cap. Candidates carry
no dimension metadata, so the engine decides suitability after download;
most landscape scans sit a little under the e-ink curation floor and are
displayed via its best-aspect fallback (a ~1.3x upscale the dither absorbs).
"""

from __future__ import annotations

import random
import re
from typing import Any

from .base import ArtCandidate, ArtFetchError, ArtProvider, FetchRequest, api_headers
from .engine import async_fetch_json

SEARCH_URL = "https://api.dimu.org/api/solr/select"
IMAGE_URL = "https://dms01.dimu.org/image/{id}?dimension={size}"
FULL_SIZE = "1200x1200"  # delivery cap; higher values fall back to a low-bitrate encode
THUMB_SIZE = "600x600"
API_TIMEOUT = 20.0
DEMO_KEY = "demo"  # documented public test key; KulturIT issues real keys on request

# Nasjonalmuseet's fine-art collection, paintings only.
DEFAULT_FILTERS = (
    "identifier.owner:NMK-B",
    "artifact.ingress.names:Maleri",
    "artifact.hasPictures:true",
)
QUERY_FILTERS = ("artifact.type:Fineart", "artifact.hasPictures:true")

_BRACKET_SUFFIX = re.compile(r"\s*\[[^\]]*\]\s*$")  # "Kyss [Maleri]" -> "Kyss"


def _flip_name(name: str) -> str:
    """DiMu producers are surname-first ("Munch, Edvard") — flip for captions."""
    surname, sep, forename = name.partition(", ")
    return f"{forename} {surname}" if sep else name


def parse_dimu_doc(doc: dict) -> ArtCandidate | None:
    media_id = doc.get("artifact.defaultMediaIdentifier")
    uuid = doc.get("artifact.uuid")
    if not media_id or not uuid:
        return None
    title = _BRACKET_SUFFIX.sub("", doc.get("artifact.ingress.title") or "") or "Untitled"
    producer = (doc.get("artifact.ingress.producer") or "").strip()
    artist = _flip_name(producer) if producer else None
    owner = doc.get("identifier.owner") or ""
    museum = "Nasjonalmuseet" if owner.startswith("NMK") else "DigitaltMuseum"
    attribution = f"{title} — {artist}, {museum}" if artist else f"{title}, {museum}"
    return ArtCandidate(
        provider="dimu",
        item_id=str(uuid),
        image_url=IMAGE_URL.format(id=media_id, size=FULL_SIZE),
        thumb_url=IMAGE_URL.format(id=media_id, size=THUMB_SIZE),
        title=title,
        artist=artist,
        attribution=attribution,
    )


class DimuProvider(ArtProvider):
    key = "dimu"
    name = "Nasjonalmuseet (DigitaltMuseum)"
    min_interval = 2.0  # shared demo key — be polite

    async def _select(
        self, session: Any, cache: Any, params: dict, error_label: str
    ) -> list[dict]:
        payload = await async_fetch_json(
            session,
            cache,
            key=self.key,
            min_interval=self.min_interval,
            url=SEARCH_URL,
            error_label=error_label,
            params={**params, "wt": "json", "api.key": DEMO_KEY},
            headers=api_headers(),
            timeout=API_TIMEOUT,
        )
        return (payload.get("response") or {}).get("docs") or []

    async def async_candidates(
        self, session: Any, cache: Any, request: FetchRequest, count: int
    ) -> list[ArtCandidate]:
        if request.query:
            q, filters = request.query, QUERY_FILTERS
        else:
            q, filters = "*:*", DEFAULT_FILTERS
        docs = await self._select(
            session,
            cache,
            {
                "q": q,
                "fq": list(filters),
                "rows": count,
                # Server-side random ordering — no offset bookkeeping needed.
                "sort": f"random_{random.randrange(1_000_000)} asc",
            },
            "DigitaltMuseum search",
        )
        candidates = [
            candidate for doc in docs if (candidate := parse_dimu_doc(doc)) is not None
        ]
        if not candidates and request.query:
            raise ArtFetchError(
                f"DigitaltMuseum found no fine art for {request.query!r}"
            )
        return candidates

    async def async_by_id(
        self, session: Any, cache: Any, item_id: str, request: FetchRequest
    ) -> ArtCandidate:
        docs = await self._select(
            session,
            cache,
            {"q": "*:*", "fq": f'artifact.uuid:"{item_id}"', "rows": 1},
            f"DigitaltMuseum object {item_id}",
        )
        candidate = parse_dimu_doc(docs[0]) if docs else None
        if candidate is None:
            raise ArtFetchError(f"DigitaltMuseum object {item_id} has no image")
        return candidate
