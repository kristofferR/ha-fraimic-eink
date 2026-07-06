"""Lorem Picsum — random stock photos at the exact panel size. Demo tier.

No API call needed at all: the URL itself is the random pick (a seed keeps
each candidate distinct and the download deterministic per candidate).
"""

from __future__ import annotations

import random
from typing import Any

from .base import ArtCandidate, ArtProvider, FetchRequest


class PicsumProvider(ArtProvider):
    key = "picsum"
    name = "Lorem Picsum"
    min_interval = 0.5

    async def async_candidates(
        self, session: Any, cache: Any, request: FetchRequest, count: int
    ) -> list[ArtCandidate]:
        width, height = request.target_width, request.target_height
        candidates = []
        for _ in range(count):
            seed = random.randrange(1_000_000_000)
            candidates.append(
                ArtCandidate(
                    provider="picsum",
                    item_id=str(seed),
                    image_url=f"https://picsum.photos/seed/{seed}/{width}/{height}",
                    thumb_url=f"https://picsum.photos/seed/{seed}/400/300",
                    title="Random photo",
                    license="Unsplash-sourced",
                    attribution="Lorem Picsum",
                    width=width,
                    height=height,
                )
            )
        return candidates

    async def async_by_id(
        self, session: Any, cache: Any, item_id: str, request: FetchRequest
    ) -> ArtCandidate:
        width, height = request.target_width, request.target_height
        return ArtCandidate(
            provider="picsum",
            item_id=item_id,
            image_url=f"https://picsum.photos/seed/{item_id}/{width}/{height}",
            title="Random photo",
            license="Unsplash-sourced",
            attribution="Lorem Picsum",
            width=width,
            height=height,
        )
