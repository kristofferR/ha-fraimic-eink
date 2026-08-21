"""Reframed Gallery's public, curated artwork catalogue.

No API is required: its server-rendered pages expose download URLs and
structured artwork metadata. Keep the parser focused on those semantic
attributes so CSS/module-name changes do not affect it.
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import unquote, urlsplit

from .base import (
    ArtCandidate,
    ArtFetchError,
    ArtProvider,
    BrowseFolder,
    BrowsePage,
    FetchRequest,
    api_headers,
)
from .engine import read_capped

BASE_URL = "https://www.reframed.gallery"
PAGE_TTL = 3600.0
PAGE_TIMEOUT = 30.0
MAX_PAGE_BYTES = 8 * 1024 * 1024

_VALID_PATH = re.compile(r"[a-z0-9][a-z0-9/-]*")
_PAGE_SUFFIX = re.compile(r"/page/\d+$")
_ARTWORK_PATH = re.compile(r"/[a-z0-9-]+/[a-z0-9-]+$")


@dataclass
class _Tile:
    href: str = ""
    title: str = ""
    thumb_url: str | None = None
    download_url: str | None = None
    label: str = ""
    count: int | None = None


class _TileParser(HTMLParser):
    """Extract visible Reframed tiles without depending on hashed CSS names."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tiles: list[_Tile] = []
        self._div_depth = 0
        self._wrapper_depth: int | None = None
        self._tile: _Tile | None = None
        self._capture: str | None = None
        self._text: list[str] = []

    def handle_starttag(
        self, tag: str, attrs_list: list[tuple[str, str | None]]
    ) -> None:
        attrs = dict(attrs_list)
        classes = attrs.get("class") or ""
        if tag == "div":
            self._div_depth += 1
            if "Tile-module" in classes and "wrapper" in classes:
                self._wrapper_depth = self._div_depth
                self._tile = _Tile()
            return
        if self._tile is None:
            return
        if tag == "a" and "Tile-module" in classes and "link" in classes:
            self._tile.href = attrs.get("href") or ""
        elif tag == "img" and "Tile-module" in classes and "image" in classes:
            self._tile.title = attrs.get("alt") or ""
            self._tile.thumb_url = attrs.get("src") or None
        elif tag == "button" and attrs.get("data-download-url"):
            self._tile.download_url = attrs["data-download-url"]
        elif tag == "span" and "Tile-module" in classes:
            if "name" in classes:
                self._start_capture("label")
            elif "count" in classes:
                self._start_capture("count")

    def handle_data(self, data: str) -> None:
        if self._capture is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "span" and self._capture is not None:
            value = "".join(self._text).strip()
            if self._tile is not None:
                if self._capture == "label":
                    self._tile.label = value
                elif value.isdigit():
                    self._tile.count = int(value)
            self._capture = None
            self._text = []
        if tag != "div":
            return
        if self._wrapper_depth == self._div_depth and self._tile is not None:
            self.tiles.append(self._tile)
            self._tile = None
            self._wrapper_depth = None
        self._div_depth -= 1

    def _start_capture(self, field: str) -> None:
        self._capture = field
        self._text = []


class _LinkParser(HTMLParser):
    """Collect link text for tab-based folders such as Colors."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(
        self, tag: str, attrs_list: list[tuple[str, str | None]]
    ) -> None:
        if tag != "a":
            return
        href = dict(attrs_list).get("href") or ""
        if href.startswith("/colors/") and "/page/" not in href:
            self._href = href
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or self._href is None:
            return
        title = "".join(self._text).strip()
        if title:
            self.links.append((self._href, title))
        self._href = None
        self._text = []


class _StructuredDataParser(HTMLParser):
    """Collect JSON-LD blocks from an artwork detail page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []
        self._capturing = False
        self._text: list[str] = []

    def handle_starttag(
        self, tag: str, attrs_list: list[tuple[str, str | None]]
    ) -> None:
        attrs = dict(attrs_list)
        if tag == "script" and attrs.get("type") == "application/ld+json":
            self._capturing = True
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._capturing:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._capturing:
            self.blocks.append("".join(self._text))
            self._capturing = False
            self._text = []


def _tiles(html: str) -> list[_Tile]:
    parser = _TileParser()
    parser.feed(html)
    return parser.tiles


def _artist_from_download_url(url: str) -> str | None:
    filename = PurePosixPath(unquote(urlsplit(url).path)).name
    artist, separator, _rest = filename.partition(" - ")
    return artist.strip() if separator and artist.strip() else None


def _candidate(tile: _Tile) -> ArtCandidate | None:
    if not tile.download_url or not _ARTWORK_PATH.fullmatch(tile.href):
        return None
    title = tile.title.strip() or "Untitled"
    artist = _artist_from_download_url(tile.download_url)
    attribution = (
        f"{title} — {artist}, Reframed Gallery"
        if artist
        else f"{title}, Reframed Gallery"
    )
    return ArtCandidate(
        provider="reframed",
        item_id=tile.href.lstrip("/"),
        image_url=tile.download_url,
        thumb_url=tile.thumb_url,
        title=title,
        artist=artist,
        attribution=attribution,
        extra={"source_url": f"{BASE_URL}{tile.href}"},
    )


def parse_artwork_tiles(html: str) -> list[ArtCandidate]:
    """Parse downloadable artwork tiles from a listing page."""
    return [candidate for tile in _tiles(html) if (candidate := _candidate(tile))]


def parse_group_tiles(html: str, group: str) -> list[BrowseFolder]:
    """Parse collection, tag, or artist tiles into browse folders."""
    folders: list[BrowseFolder] = []
    for tile in _tiles(html):
        path = tile.href.lstrip("/")
        if group in ("collections", "tags"):
            if not path.startswith(f"{group}/") or _PAGE_SUFFIX.search(path):
                continue
            item_id = path
        elif group == "artists":
            if "/" in path or not path:
                continue
            item_id = f"artist/{path}"
        else:
            continue
        title = tile.label.strip() or tile.title.strip()
        if title:
            folders.append(
                BrowseFolder(
                    item_id=item_id,
                    title=title,
                    thumb_url=tile.thumb_url,
                    count=tile.count,
                )
            )
    return sorted(folders, key=lambda folder: folder.title.casefold())


def parse_color_links(html: str) -> list[BrowseFolder]:
    """Parse the color tabs, preserving Reframed's spectrum order."""
    parser = _LinkParser()
    parser.feed(html)
    seen: set[str] = set()
    folders: list[BrowseFolder] = []
    for href, title in parser.links:
        item_id = href.lstrip("/")
        if item_id not in seen:
            seen.add(item_id)
            folders.append(BrowseFolder(item_id=item_id, title=title))
    return folders


def parse_page_count(html: str, path: str) -> int:
    """Return the highest pagination number linked from ``path``."""
    canonical = _PAGE_SUFFIX.sub("", path)
    pattern = re.compile(rf'href="/{re.escape(canonical)}/page/(\d+)"')
    return max((int(value) for value in pattern.findall(html)), default=1)


def parse_heading(html: str, fallback: str) -> str:
    """Extract the page's plain h1 heading."""
    match = re.search(r"<h1[^>]*>([^<]+)</h1>", html)
    return match.group(1).strip() if match else fallback


def _json_ld_records(payload: Any) -> list[dict[str, Any]]:
    """Flatten the common JSON-LD document shapes into object records."""
    if isinstance(payload, list):
        return [record for item in payload for record in _json_ld_records(item)]
    if not isinstance(payload, dict):
        return []
    graph = payload.get("@graph")
    return [payload, *_json_ld_records(graph)] if graph is not None else [payload]


def parse_artwork_page(html: str, item_id: str) -> ArtCandidate | None:
    """Parse one artwork's schema.org VisualArtwork block."""
    parser = _StructuredDataParser()
    parser.feed(html)
    for block in parser.blocks:
        try:
            payload = json.loads(block)
        except json.JSONDecodeError:
            continue
        for record in _json_ld_records(payload):
            if record.get("@type") != "VisualArtwork":
                continue
            title = str(record.get("name") or "Untitled")
            artist_data = record.get("artist") or {}
            artist = artist_data.get("name") if isinstance(artist_data, dict) else None
            image_url = record.get("contentUrl")
            if not image_url:
                continue
            attribution = (
                f"{title} — {artist}, Reframed Gallery"
                if artist
                else f"{title}, Reframed Gallery"
            )
            return ArtCandidate(
                provider="reframed",
                item_id=item_id,
                image_url=str(image_url),
                thumb_url=record.get("thumbnailUrl") or record.get("image"),
                title=title,
                artist=str(artist) if artist else None,
                attribution=attribution,
                extra={"source_url": f"{BASE_URL}/{item_id}"},
            )
    return None


ROOT_FOLDERS = (
    BrowseFolder("collections", "Collections"),
    BrowseFolder("colors", "Colors"),
    BrowseFolder("tags", "Tags"),
    BrowseFolder("artists", "Artists"),
    BrowseFolder("verticals", "Vertical artworks"),
    BrowseFolder("recent", "Recently added"),
)

ARTIST_RANGES = (
    BrowseFolder("artists/page/1", "A – C"),
    BrowseFolder("artists/page/2", "D – F"),
    BrowseFolder("artists/page/3", "G – I"),
    BrowseFolder("artists/page/4", "J – L"),
    BrowseFolder("artists/page/5", "M – O"),
    BrowseFolder("artists/page/6", "P – S"),
    BrowseFolder("artists/page/7", "T – Z"),
)


class ReframedProvider(ArtProvider):
    key = "reframed"
    name = "Reframed Gallery"
    hierarchical_browse = True
    min_interval = 0.5

    async def _page(self, session: Any, cache: Any, path: str) -> str:
        normalized = path.strip("/")
        if (
            not normalized
            or not _VALID_PATH.fullmatch(normalized)
            or ".." in normalized
        ):
            raise ArtFetchError("Invalid Reframed browse path")
        cache_key = f"reframed_page_{normalized}"
        cached = cache.get(cache_key, PAGE_TTL)
        if cached is not None:
            return cached
        await cache.async_throttle(self.key, self.min_interval)
        url = f"{BASE_URL}/{normalized}"
        resp = await session.get(url, headers=api_headers(), timeout=PAGE_TIMEOUT)
        async with resp:
            if resp.status != 200:
                raise ArtFetchError(f"Reframed page returned HTTP {resp.status}")
            try:
                data = await read_capped(resp.content, MAX_PAGE_BYTES)
            except ValueError as err:
                raise ArtFetchError("Reframed page exceeds the size cap") from err
        html = data.decode("utf-8", errors="replace")
        cache.set(cache_key, html)
        return html

    async def async_candidates(
        self, session: Any, cache: Any, request: FetchRequest, count: int
    ) -> list[ArtCandidate]:
        first_page = await self._page(session, cache, "recent")
        page_number = random.randint(1, parse_page_count(first_page, "recent"))
        html = (
            first_page
            if page_number == 1
            else await self._page(session, cache, f"recent/page/{page_number}")
        )
        candidates = parse_artwork_tiles(html)
        random.shuffle(candidates)
        return candidates[:count]

    async def async_by_id(
        self, session: Any, cache: Any, item_id: str, request: FetchRequest
    ) -> ArtCandidate:
        if not _ARTWORK_PATH.fullmatch(f"/{item_id}"):
            raise ArtFetchError("Invalid Reframed artwork id")
        candidate = parse_artwork_page(
            await self._page(session, cache, item_id), item_id
        )
        if candidate is None:
            raise ArtFetchError(f"Reframed artwork {item_id} has no download")
        return candidate

    async def async_browse(
        self, session: Any, cache: Any, browse_id: str, request: FetchRequest
    ) -> BrowsePage:
        normalized = browse_id.strip("/")
        if not normalized:
            return BrowsePage(title=self.name, folders=ROOT_FOLDERS)
        if normalized == "artists":
            return BrowsePage(title="Artists", folders=ARTIST_RANGES)
        if normalized.startswith("artists/page/"):
            page_number = normalized.rsplit("/", 1)[-1]
            path = "artists" if page_number == "1" else normalized
            html = await self._page(session, cache, path)
            title = next(
                (
                    folder.title
                    for folder in ARTIST_RANGES
                    if folder.item_id == normalized
                ),
                "Artists",
            )
            return BrowsePage(
                title=f"Artists {title}",
                folders=tuple(parse_group_tiles(html, "artists")),
            )
        if normalized in ("collections", "tags", "colors"):
            html = await self._page(session, cache, normalized)
            folders = (
                parse_color_links(html)
                if normalized == "colors"
                else parse_group_tiles(html, normalized)
            )
            return BrowsePage(
                title=parse_heading(html, normalized.title()), folders=tuple(folders)
            )

        site_path = normalized.removeprefix("artist/")
        html = await self._page(session, cache, site_path)
        candidates = tuple(parse_artwork_tiles(html))
        page_folders: tuple[BrowseFolder, ...] = ()
        if not _PAGE_SUFFIX.search(site_path):
            page_folders = tuple(
                BrowseFolder(f"{normalized}/page/{page}", f"Page {page}")
                for page in range(2, parse_page_count(html, site_path) + 1)
            )
        fallback = site_path.rsplit("/", 1)[-1].replace("-", " ").title()
        return BrowsePage(
            title=parse_heading(html, fallback),
            folders=page_folders,
            candidates=candidates,
        )
