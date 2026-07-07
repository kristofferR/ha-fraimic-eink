"""Provider base types. HA-free.

A provider turns "give me something nice for a W x H e-ink frame" into
concrete image candidates. Everything network-shaped is duck-typed
(``session`` only needs aiohttp's ``get``/``post`` context-manager surface)
so the engine and providers run against a fake session in the headless test
suite.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Sent on every provider API request (Wikimedia and AIC policies ask for a
# descriptive UA with contact info; the rest simply deserve politeness).
USER_AGENT = (
    "ha-fraimic-eink/1.2 "
    "(https://github.com/kristofferR/ha-fraimic-eink; kristoffer@risanger.no)"
)


class ArtFetchError(Exception):
    """A provider could not produce an image (API down, empty pool, ...).

    HA-free on purpose; ``providers.ha`` wraps it in a HomeAssistantError
    subclass so the scheduler can tell "source problem" from "frame asleep".
    """


@dataclass(frozen=True)
class FetchRequest:
    """What the frame needs right now."""

    target_width: int  # viewed orientation (after mount rotation)
    target_height: int
    query: str | None = None  # photo providers only; museums ignore it
    api_key: str | None = None
    fit: str = "cover"


@dataclass(frozen=True)
class ArtCandidate:
    """One selectable image, metadata only (nothing downloaded yet)."""

    provider: str  # registry key
    item_id: str
    image_url: str  # full-resolution download URL
    title: str
    thumb_url: str | None = None  # media-browser thumbnail
    artist: str | None = None
    license: str | None = None
    attribution: str = ""  # ready-to-render one-liner
    width: int | None = None  # dims when the API reports them
    height: int | None = None
    extra: dict | None = None  # provider-private (e.g. Unsplash download ping URL)


@dataclass(frozen=True)
class ArtImage:
    """A downloaded, curation-approved image."""

    data: bytes
    candidate: ArtCandidate


@dataclass
class ProviderInfo:
    """Static provider facts used by UI surfaces."""

    key: str
    name: str


class ArtProvider:
    """Base class; subclasses set the class attributes and candidates()."""

    key: str = ""
    name: str = ""
    requires_key: bool = False
    key_option: str | None = None  # entry-options key holding the API key
    # Seconds between API calls (politeness / published limits).
    min_interval: float = 1.0

    async def async_candidates(
        self, session: Any, cache: Any, request: FetchRequest, count: int
    ) -> list[ArtCandidate]:
        """Up to ``count`` fresh candidates, best-effort random order."""
        raise NotImplementedError

    async def async_by_id(
        self, session: Any, cache: Any, item_id: str, request: FetchRequest
    ) -> ArtCandidate:
        """A specific item (media-browser click). Default: unsupported."""
        raise ArtFetchError(f"{self.name} does not support fetching by id")

    async def async_on_display(self, session: Any, candidate: ArtCandidate) -> None:
        """Hook fired when a candidate is actually shown (Unsplash ping)."""

    def image_headers(self, candidate: ArtCandidate) -> dict[str, str]:
        """Headers for downloading the image itself."""
        return {"User-Agent": USER_AGENT}


def api_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = {"User-Agent": USER_AGENT}
    if extra:
        headers.update(extra)
    return headers
