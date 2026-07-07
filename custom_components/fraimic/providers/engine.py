"""Candidate/retry/download loop shared by every provider. HA-free.

``session`` needs aiohttp's ``get(url, headers=, timeout=)`` async-context
surface; ``dims_of`` is an async callable decoding image dimensions (the HA
layer runs PIL in an executor; tests pass a plain coroutine). This is where
curation gets enforced and where flaky metadata (empty image URLs, tiny
scans, decode failures) is retried within a bounded budget.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from ..const import MAX_SOURCE_BYTES, MAX_SOURCE_PIXELS
from .base import ArtCandidate, ArtFetchError, ArtImage, ArtProvider, FetchRequest
from .curation import acceptable_for_fit, aspect_score

_LOGGER = logging.getLogger(__name__)

MAX_CANDIDATE_ATTEMPTS = 8
MAX_DOWNLOAD_ATTEMPTS = 3
DOWNLOAD_TIMEOUT = 45.0

DimsOf = Callable[[bytes], Awaitable[tuple[int, int]]]


async def async_fetch_json(
    session: Any,
    cache: Any,
    *,
    key: str,
    min_interval: float,
    url: str,
    error_label: str,
    timeout: float,
    method: str = "get",
    headers: dict[str, str] | None = None,
    json_kwargs: dict[str, Any] | None = None,
    **request_kwargs: Any,
) -> Any:
    """Fetch and parse one throttled provider JSON endpoint."""
    await cache.async_throttle(key, min_interval)
    request = getattr(session, method)
    resp = await request(
        url,
        headers=headers or {},
        timeout=timeout,
        **request_kwargs,
    )
    async with resp:
        if resp.status != 200:
            raise ArtFetchError(f"{error_label} returned HTTP {resp.status}")
        try:
            return await resp.json(**(json_kwargs or {}))
        except Exception as err:  # noqa: BLE001 - JSON parser errors vary
            raise ArtFetchError(f"{error_label} returned invalid JSON: {err}") from err


async def read_capped(content: Any, limit: int = MAX_SOURCE_BYTES) -> bytes:
    """Read a response body fully, raising past ``limit`` bytes.

    A single ``content.read(n)`` returns whatever happens to be buffered on
    chunked responses (no Content-Length) — verified against the AIC IIIF
    server, which returned 30 KB of a 900 KB JPEG that way. Loop until EOF.
    """
    data = bytearray()
    while True:
        chunk = await content.read(65536)
        if not chunk:
            return bytes(data)
        data.extend(chunk)
        if len(data) > limit:
            raise ValueError("response body exceeds the size cap")


async def async_download(session: Any, url: str, headers: dict[str, str]) -> bytes:
    """Download one image with the shared size cap."""
    try:
        resp = await session.get(url, headers=headers, timeout=DOWNLOAD_TIMEOUT)
    except Exception as err:  # noqa: BLE001 - network layer varies
        raise ArtFetchError(f"Could not download {url}: {err}") from err
    async with resp:
        if resp.status != 200:
            raise ArtFetchError(f"Downloading {url} returned HTTP {resp.status}")
        try:
            return await read_capped(resp.content)
        except ValueError as err:
            raise ArtFetchError(f"Image at {url} exceeds the size cap") from err
        except Exception as err:  # noqa: BLE001 - response stream errors vary
            raise ArtFetchError(f"Could not download {url}: {err}") from err


async def async_download_candidate(
    provider: ArtProvider, session: Any, candidate: ArtCandidate
) -> ArtImage:
    """Download a specific candidate without curation (user picked it)."""
    data = await async_download(
        session, candidate.image_url, provider.image_headers(candidate)
    )
    return ArtImage(data=data, candidate=candidate)


async def async_pick_and_download(
    provider: ArtProvider,
    session: Any,
    cache: Any,
    request: FetchRequest,
    *,
    dims_of: DimsOf,
    max_candidates: int = MAX_CANDIDATE_ATTEMPTS,
    max_downloads: int = MAX_DOWNLOAD_ATTEMPTS,
) -> ArtImage:
    """Pick a curated random image from ``provider`` and download it.

    Metadata dims (when the API reports them) reject candidates for free;
    the rest are checked after download by decoding the header. After the
    retry budget, the best-scoring downloaded image wins (better a slightly
    off-aspect Van Gogh than an error screen); with nothing downloadable at
    all, ArtFetchError.
    """
    tw, th = request.target_width, request.target_height
    candidates = await provider.async_candidates(session, cache, request, max_candidates)
    if not candidates:
        raise ArtFetchError(f"{provider.name} returned no candidates")

    best: tuple[float, ArtImage] | None = None
    downloads = 0
    last_error: Exception | None = None
    for candidate in candidates[:max_candidates]:
        if (
            candidate.width
            and candidate.height
            and not acceptable_for_fit(
                candidate.width, candidate.height, tw, th, request.fit
            )
        ):
            _LOGGER.debug(
                "%s: skipping %s (%sx%s metadata dims unsuitable)",
                provider.key,
                candidate.item_id,
                candidate.width,
                candidate.height,
            )
            continue
        if downloads >= max_downloads:
            break
        downloads += 1
        try:
            data = await async_download(
                session, candidate.image_url, provider.image_headers(candidate)
            )
        except (ArtFetchError, OSError) as err:
            last_error = err
            _LOGGER.debug("%s: candidate %s failed: %s", provider.key, candidate.item_id, err)
            continue
        try:
            width, height = await dims_of(data)
        except Exception as err:  # noqa: BLE001 - image decoders fail broadly
            last_error = err
            _LOGGER.debug("%s: candidate %s failed: %s", provider.key, candidate.item_id, err)
            continue
        if width * height > MAX_SOURCE_PIXELS:
            last_error = ArtFetchError(f"image is too large ({width}x{height})")
            _LOGGER.debug(
                "%s: candidate %s failed: %s",
                provider.key,
                candidate.item_id,
                last_error,
            )
            continue
        image = ArtImage(data=data, candidate=candidate)
        if acceptable_for_fit(width, height, tw, th, request.fit):
            return image
        score = aspect_score(width, height, tw, th)
        _LOGGER.debug(
            "%s: %s is %sx%s (unsuitable, score %.2f) — keeping as fallback",
            provider.key,
            candidate.item_id,
            width,
            height,
            score,
        )
        if best is None or score > best[0]:
            best = (score, image)

    if best is not None:
        return best[1]
    raise ArtFetchError(
        f"{provider.name} produced no usable image"
        + (f" (last error: {last_error})" if last_error else "")
    )
