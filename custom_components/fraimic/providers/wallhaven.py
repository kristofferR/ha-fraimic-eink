"""Wallhaven — keyless, SFW wallpaper search and browsing.

The public API supplies original image URLs and dimensions, so unsuitable
wallpapers can be rejected before download. Browsing mirrors Wallhaven's most
useful sort modes, categories, colors, and top-list ranges while keeping every
request restricted to SFW results and the frame's viewed orientation.
"""

from __future__ import annotations

import re
from typing import Any

from ..const import MAX_SOURCE_BYTES, MAX_SOURCE_PIXELS
from .base import (
    ArtCandidate,
    ArtFetchError,
    ArtProvider,
    BrowseFolder,
    BrowsePage,
    FetchRequest,
    api_headers,
)

API_BASE = "https://wallhaven.cc/api/v1"
SEARCH_URL = f"{API_BASE}/search"
WALLPAPER_URL = f"{API_BASE}/w"
API_TIMEOUT = 20.0
SEARCH_TTL = 300.0
DETAIL_TTL = 3600.0
MAX_BROWSE_PAGES = 20

_WALLPAPER_ID = re.compile(r"[a-z0-9]{6}")
_PAGE_SUFFIX = re.compile(r"/page/([1-9]\d*)$")

FEED_FOLDERS = (
    BrowseFolder("latest", "Latest"),
    BrowseFolder("random", "Random"),
    BrowseFolder("views", "Most viewed"),
    BrowseFolder("favorites", "Most favorited"),
)

ROOT_FOLDERS = (
    *FEED_FOLDERS,
    BrowseFolder("top", "Top lists"),
    BrowseFolder("categories", "Categories"),
    BrowseFolder("colors", "Colors"),
)

TOP_FOLDERS = (
    BrowseFolder("top/1d", "Today"),
    BrowseFolder("top/3d", "Three days"),
    BrowseFolder("top/1w", "This week"),
    BrowseFolder("top/1M", "This month"),
    BrowseFolder("top/3M", "Three months"),
    BrowseFolder("top/6M", "Six months"),
    BrowseFolder("top/1y", "This year"),
)

CATEGORY_FOLDERS = (
    BrowseFolder("category/100", "General"),
    BrowseFolder("category/010", "Anime"),
    BrowseFolder("category/001", "People"),
)

_COLORS = (
    ("660000", "Dark red"),
    ("990000", "Red"),
    ("cc0000", "Bright red"),
    ("cc3333", "Coral red"),
    ("ea4c88", "Pink"),
    ("993399", "Magenta"),
    ("663399", "Purple"),
    ("333399", "Indigo"),
    ("0066cc", "Blue"),
    ("0099cc", "Cyan blue"),
    ("66cccc", "Aqua"),
    ("77cc33", "Lime green"),
    ("669900", "Green"),
    ("336600", "Dark green"),
    ("666600", "Olive"),
    ("999900", "Mustard"),
    ("cccc33", "Yellow green"),
    ("ffff00", "Yellow"),
    ("ffcc33", "Gold"),
    ("ff9900", "Orange"),
    ("ff6600", "Deep orange"),
    ("cc6633", "Brown"),
    ("996633", "Tan"),
    ("663300", "Dark brown"),
    ("000000", "Black"),
    ("424153", "Charcoal"),
    ("999999", "Gray"),
    ("cccccc", "Light gray"),
    ("ffffff", "White"),
)
COLOR_FOLDERS = tuple(
    BrowseFolder(f"color/{value}", title) for value, title in _COLORS
)
COLOR_TITLES = dict(_COLORS)
TOP_TITLES = {
    folder.item_id.removeprefix("top/"): folder.title for folder in TOP_FOLDERS
}
CATEGORY_TITLES = {
    folder.item_id.removeprefix("category/"): folder.title
    for folder in CATEGORY_FOLDERS
}


def _positive_int(value: Any) -> int | None:
    return value if type(value) is int and value > 0 else None


def _tag_title(item: dict[str, Any]) -> str | None:
    tags = item.get("tags")
    if not isinstance(tags, list):
        return None
    names = [
        name[:1].upper() + name[1:]
        for tag in tags
        if isinstance(tag, dict) and (name := str(tag.get("name") or "").strip())
    ]
    return " · ".join(names[:3]) or None


def parse_wallhaven_wallpaper(item: Any) -> ArtCandidate | None:
    """Parse one search/detail record, rejecting unsafe or oversized items."""
    if not isinstance(item, dict) or item.get("purity") != "sfw":
        return None
    item_id = str(item.get("id") or "")
    image_url = item.get("path")
    if not _WALLPAPER_ID.fullmatch(item_id) or not isinstance(image_url, str):
        return None
    if not image_url.startswith("https://w.wallhaven.cc/"):
        return None

    width = _positive_int(item.get("dimension_x"))
    height = _positive_int(item.get("dimension_y"))
    file_size = _positive_int(item.get("file_size"))
    if file_size and file_size > MAX_SOURCE_BYTES:
        return None
    if width and height and width * height > MAX_SOURCE_PIXELS:
        return None

    category = str(item.get("category") or "").strip()
    title = _tag_title(item) or (
        f"{category.title()} Wallpaper {item_id}"
        if category
        else f"Wallhaven Wallpaper {item_id}"
    )
    uploader = item.get("uploader")
    artist = (
        str(uploader.get("username") or "").strip()
        if isinstance(uploader, dict)
        else ""
    )
    attribution = (
        f"{title} — {artist}, Wallhaven" if artist else f"{title}, Wallhaven"
    )
    thumbs = item.get("thumbs")
    thumb_url = thumbs.get("large") if isinstance(thumbs, dict) else None
    source_url = item.get("url") or f"https://wallhaven.cc/w/{item_id}"
    return ArtCandidate(
        provider="wallhaven",
        item_id=item_id,
        image_url=image_url,
        thumb_url=thumb_url if isinstance(thumb_url, str) else None,
        title=title,
        artist=artist or None,
        attribution=attribution,
        width=width,
        height=height,
        extra={"source_url": str(source_url)},
    )


def parse_wallhaven_listing(payload: Any) -> list[ArtCandidate]:
    """Parse a search response into safe candidates."""
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        return []
    return [
        candidate
        for item in payload["data"]
        if (candidate := parse_wallhaven_wallpaper(item)) is not None
    ]


def _last_page(payload: Any) -> int:
    if not isinstance(payload, dict) or not isinstance(payload.get("meta"), dict):
        return 1
    return _positive_int(payload["meta"].get("last_page")) or 1


def _split_page(browse_id: str) -> tuple[str, int]:
    match = _PAGE_SUFFIX.search(browse_id)
    if match is None:
        return browse_id, 1
    return browse_id[: match.start()], int(match.group(1))


def _browse_query(browse_id: str) -> tuple[str, dict[str, str]] | None:
    if browse_id == "latest":
        return "Latest", {"sorting": "date_added"}
    if browse_id == "random":
        return "Random", {"sorting": "random"}
    if browse_id == "views":
        return "Most viewed", {"sorting": "views"}
    if browse_id == "favorites":
        return "Most favorited", {"sorting": "favorites"}
    if browse_id.startswith("top/"):
        top_range = browse_id.removeprefix("top/")
        title = TOP_TITLES.get(top_range)
        if title:
            return f"Top · {title}", {"sorting": "toplist", "topRange": top_range}
    if browse_id.startswith("category/"):
        categories = browse_id.removeprefix("category/")
        title = CATEGORY_TITLES.get(categories)
        if title:
            return title, {
                "categories": categories,
                "sorting": "toplist",
                "topRange": "1M",
            }
    if browse_id.startswith("color/"):
        color = browse_id.removeprefix("color/")
        title = COLOR_TITLES.get(color)
        if title:
            return title, {
                "colors": color,
                "sorting": "toplist",
                "topRange": "1M",
            }
    return None


class WallhavenProvider(ArtProvider):
    key = "wallhaven"
    name = "Wallhaven"
    hierarchical_browse = True
    # Wallhaven publishes a 45 requests/minute limit.
    min_interval = 1.5

    @staticmethod
    def _frame_params(request: FetchRequest) -> dict[str, str]:
        # Wallhaven accepts these broad web-UI ratio filters in its API. An
        # exact numeric ratio would hide wallpapers that crop cleanly to the frame.
        orientation = (
            "landscape"
            if request.target_width >= request.target_height
            else "portrait"
        )
        return {
            "categories": "111",
            "purity": "100",
            "atleast": f"{request.target_width}x{request.target_height}",
            "ratios": orientation,
            "order": "desc",
        }

    async def _json(
        self,
        session: Any,
        cache: Any,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        cache_key: str | None = None,
        ttl: float = SEARCH_TTL,
    ) -> Any:
        if cache_key:
            cached = cache.get(cache_key, ttl)
            if cached is not None:
                return cached
        await cache.async_throttle(self.key, self.min_interval)
        resp = await session.get(
            url,
            params=params,
            headers=api_headers(),
            timeout=API_TIMEOUT,
        )
        async with resp:
            if resp.status == 429:
                raise ArtFetchError(
                    "Wallhaven rate limit reached; try again in a minute"
                )
            if resp.status != 200:
                raise ArtFetchError(f"Wallhaven returned HTTP {resp.status}")
            try:
                payload = await resp.json(content_type=None)
            except Exception as err:
                raise ArtFetchError(f"Wallhaven returned invalid JSON: {err}") from err
        if cache_key:
            cache.set(cache_key, payload)
        return payload

    async def async_candidates(
        self, session: Any, cache: Any, request: FetchRequest, count: int
    ) -> list[ArtCandidate]:
        params = {**self._frame_params(request), "sorting": "random"}
        if request.query:
            params["q"] = request.query
        payload = await self._json(session, cache, SEARCH_URL, params=params)
        return parse_wallhaven_listing(payload)[:count]

    async def async_by_id(
        self, session: Any, cache: Any, item_id: str, request: FetchRequest
    ) -> ArtCandidate:
        if not _WALLPAPER_ID.fullmatch(item_id):
            raise ArtFetchError("Invalid Wallhaven wallpaper id")
        payload = await self._json(
            session,
            cache,
            f"{WALLPAPER_URL}/{item_id}",
            cache_key=f"wallhaven_wallpaper_{item_id}",
            ttl=DETAIL_TTL,
        )
        item = payload.get("data") if isinstance(payload, dict) else None
        candidate = parse_wallhaven_wallpaper(item)
        if candidate is None:
            raise ArtFetchError(
                f"Wallhaven wallpaper {item_id} is not a usable SFW image"
            )
        return candidate

    async def async_browse(
        self, session: Any, cache: Any, browse_id: str, request: FetchRequest
    ) -> BrowsePage:
        normalized = browse_id.strip("/")
        if not normalized:
            return BrowsePage(title=self.name, folders=ROOT_FOLDERS)
        if normalized == "top":
            return BrowsePage(title="Top lists", folders=TOP_FOLDERS)
        if normalized == "categories":
            return BrowsePage(title="Categories", folders=CATEGORY_FOLDERS)
        if normalized == "colors":
            return BrowsePage(title="Colors", folders=COLOR_FOLDERS)

        base_id, page = _split_page(normalized)
        browse_query = _browse_query(base_id)
        if browse_query is None or not 1 <= page <= MAX_BROWSE_PAGES:
            raise ArtFetchError("Invalid Wallhaven browse path")
        title, browse_params = browse_query
        params = {**self._frame_params(request), **browse_params, "page": page}
        cache_key = (
            None
            if base_id == "random"
            else (
                f"wallhaven_browse_{base_id}_{page}_"
                f"{request.target_width}x{request.target_height}"
            )
        )
        payload = await self._json(
            session, cache, SEARCH_URL, params=params, cache_key=cache_key
        )
        candidates = tuple(parse_wallhaven_listing(payload))
        folders: tuple[BrowseFolder, ...] = ()
        if page == 1 and base_id != "random":
            folders = tuple(
                BrowseFolder(f"{base_id}/page/{number}", f"Page {number}")
                for number in range(
                    2, min(_last_page(payload), MAX_BROWSE_PAGES) + 1
                )
            )
        page_title = title if page == 1 else f"{title} · Page {page}"
        return BrowsePage(title=page_title, folders=folders, candidates=candidates)
