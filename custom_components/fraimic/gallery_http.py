"""Progressive gallery, search, detail, and picture actions for the panel."""

from __future__ import annotations

import asyncio
import io
import json
import re
import uuid
from collections import Counter
from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from aiohttp import web
from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.exceptions import HomeAssistantError

from .artwork_cache import get_artwork_cache
from .const import DOMAIN, LIBRARY_ALBUM_DEFAULT
from .helpers import resolve_render_params
from .http_helpers import require_loaded_entry
from .library import FraimicLibrary, get_library
from .library_model import LibraryImage, normalize_crop, render_cache_key
from .playlists import DATA_PLAYLISTS, PlaylistManager
from .providers import PROVIDERS, available_provider_keys, get_provider
from .providers.base import ArtCandidate
from .providers.cache import ByteCache
from .providers.ha import (
    ArtFetchError,
    artwork_source_cache_id,
    async_art_by_media_id,
    async_browse_provider,
    async_browse_candidates,
    async_candidate_by_media_id,
)
from .render.schema import SCREEN_SCHEMA, screen_from_dict

LIBRARY_SOURCE = "saved"
FAVORITES_ALBUM = "Favorites"
GALLERY_LIMIT = 40
MAX_GALLERY_OFFSET = 1000
GALLERY_THUMBNAIL_CACHE_BYTES = 24 * 1024 * 1024
GALLERY_THUMBNAIL_CACHE_TTL = 3600
GALLERY_IMAGE_CONCURRENCY = 6
SOURCE_GROUPS = {
    "met": "collections",
    "aic": "collections",
    "cleveland": "collections",
    "smk": "collections",
    "dimu": "collections",
    "reframed": "collections",
    "smithsonian": "collections",
    "wellcome": "collections",
    "wikimedia": "daily",
    "bing": "daily",
    "apod": "daily",
    "wallhaven": "photography",
    "nasa": "photography",
    "picsum": "photography",
    "unsplash": "photography",
    "pexels": "photography",
}


def _browser_cache_seconds(hass, entry, fallback: int) -> int:
    """Match browser freshness to the configured server-side cache policy."""
    cache = get_artwork_cache(hass)
    if cache is None:
        return fallback
    policy = cache.policy_for(entry)
    if not policy.enabled:
        return fallback
    if policy.retention is None:
        return 365 * 24 * 60 * 60
    return max(fallback, int(policy.retention))


def _thumbnail_cache(hass) -> ByteCache:
    data = hass.data.setdefault(DOMAIN, {})
    cache = data.get("gallery_thumbnail_cache")
    if not isinstance(cache, ByteCache):
        cache = ByteCache(GALLERY_THUMBNAIL_CACHE_BYTES)
        data["gallery_thumbnail_cache"] = cache
    return cache


async def _async_gallery_image(
    hass,
    entry,
    source: str,
    item_id: str,
    *,
    thumbnail: bool,
) -> tuple[bytes, str]:
    data = hass.data.setdefault(DOMAIN, {})
    key = (entry.entry_id, source, item_id)
    if thumbnail:
        cached = _thumbnail_cache(hass).get(key, GALLERY_THUMBNAIL_CACHE_TTL)
        if cached is not None:
            return cached

    semaphore = data.setdefault(
        "gallery_image_semaphore", asyncio.Semaphore(GALLERY_IMAGE_CONCURRENCY)
    )

    async def fetch() -> tuple[bytes, str]:
        async with semaphore:
            art = await async_art_by_media_id(
                hass, entry, source, item_id, thumbnail=thumbnail
            )
            content_type = await hass.async_add_executor_job(
                _image_content_type, art.data
            )
        result = (art.data, content_type)
        if thumbnail:
            _thumbnail_cache(hass).set(key, *result)
        return result

    if not thumbnail:
        return await fetch()

    in_flight = data.setdefault("gallery_thumbnail_requests", {})
    task = in_flight.get(key)
    if task is None:
        task = hass.async_create_task(fetch())
        in_flight[key] = task
    try:
        return await asyncio.shield(task)
    finally:
        if task.done() and in_flight.get(key) is task:
            del in_flight[key]


def _assert_admin(request: web.Request) -> None:
    if not getattr(request.get("hass_user"), "is_admin", False):
        raise web.HTTPForbidden(text="Admin required")


def _manager(hass) -> PlaylistManager:
    manager = hass.data.get(DOMAIN, {}).get(DATA_PLAYLISTS)
    if not isinstance(manager, PlaylistManager):
        raise web.HTTPServiceUnavailable(text="Fraimic playlists are not loaded")
    return manager


def _library(hass) -> FraimicLibrary:
    library = get_library(hass)
    if library is None:
        raise web.HTTPServiceUnavailable(text="Fraimic is not set up")
    return library


def _extra(candidate: ArtCandidate, *keys: str) -> Any:
    extra = candidate.extra or {}
    return next((extra[key] for key in keys if extra.get(key) is not None), None)


def _source_page(candidate: ArtCandidate) -> str | None:
    value = _extra(candidate, "source_url", "source_page", "web_url", "page_url")
    return value if isinstance(value, str) else None


def _render_score(width: int | None, height: int | None, entry) -> float:
    """Rank known artwork by frame-aspect match and available resolution."""
    if not width or not height or width <= 0 or height <= 0:
        return 0.0
    frame_width, frame_height = _viewed_size(entry)
    aspect_error = abs((width / height) / (frame_width / frame_height) - 1)
    aspect_score = max(0.0, 1.0 - aspect_error)
    resolution_score = min(
        1.0, (width * height / (frame_width * frame_height)) ** 0.5
    )
    return round(aspect_score * 0.7 + resolution_score * 0.3, 3)


def _queued_refs(entry) -> tuple[set[tuple[str, str]], set[str]]:
    provider_refs: set[tuple[str, str]] = set()
    library_ids: set[str] = set()
    scheduler = entry.runtime_data.scheduler
    current_and_upcoming = [
        *scheduler.queued_slides,
        *scheduler.playlist_up_next(limit=len(scheduler.screens)),
    ]
    if scheduler.current_screen is not None:
        current_and_upcoming.append(scheduler.current_screen)
    for slide in current_and_upcoming:
        source = slide.source or {}
        if source.get("provider") and source.get("provider_item"):
            provider_refs.add((source["provider"], source["provider_item"]))
        if source.get("library_image"):
            library_ids.add(source["library_image"])
    return provider_refs, library_ids


def _candidate_payload(
    candidate: ArtCandidate,
    entry,
    library: FraimicLibrary,
) -> dict[str, Any]:
    queued_refs, _ = _queued_refs(entry)
    provider = get_provider(candidate.provider)
    candidate_urls = {candidate.image_url, _source_page(candidate)} - {None, ""}
    saved_image = next(
        (
            image
            for image in library.images.values()
            if image.source_url and image.source_url in candidate_urls
        ),
        None,
    )
    saved = saved_image is not None
    width = candidate.width if isinstance(candidate.width, int) else 4
    height = candidate.height if isinstance(candidate.height, int) else 3
    image_base = "/api/fraimic/gallery/image?" + urlencode(
        {
            "entry_id": entry.entry_id,
            "source": candidate.provider,
            "item_id": candidate.item_id,
        }
    )
    return {
        "id": candidate.item_id,
        "source": candidate.provider,
        "source_name": provider.name if provider is not None else candidate.provider,
        "title": candidate.title,
        "artist": candidate.artist,
        "thumbnail_url": f"{image_base}&size=thumbnail",
        "image_url": f"{image_base}&size=full",
        "width": width,
        "height": height,
        "dimensions_known": candidate.width is not None
        and candidate.height is not None,
        "palette_score": _render_score(candidate.width, candidate.height, entry),
        "colour": None,
        "license": candidate.license,
        "attribution": candidate.attribution,
        "saved": saved,
        "favorite": bool(
            saved_image and FAVORITES_ALBUM in saved_image.normalized_albums()
        ),
        "favorite_image_id": saved_image.image_id if saved_image else None,
        "queued": (candidate.provider, candidate.item_id) in queued_refs,
        "year": _extra(candidate, "year", "date", "created"),
        "description": _extra(candidate, "description", "caption"),
        "source_page_url": _source_page(candidate),
        "download_url": candidate.image_url,
    }


def _library_payload(image, entry) -> dict[str, Any]:
    _, queued_ids = _queued_refs(entry)
    title = Path(image.filename).stem or "Untitled"
    return {
        "id": image.image_id,
        "source": LIBRARY_SOURCE,
        "source_name": "My library",
        "title": title,
        "artist": image.attribution,
        "thumbnail_url": f"/api/fraimic/library/thumb/{image.image_id}",
        "image_url": f"/api/fraimic/library/image/{image.image_id}",
        "width": image.width or 4,
        "height": image.height or 3,
        "dimensions_known": image.width is not None and image.height is not None,
        "palette_score": _render_score(image.width, image.height, entry),
        "colour": None,
        "license": image.license,
        "attribution": image.attribution,
        "saved": True,
        "favorite": FAVORITES_ALBUM in image.normalized_albums(),
        "favorite_image_id": image.image_id,
        "queued": image.image_id in queued_ids,
        "year": None,
        "description": None,
        "source_page_url": image.source_url,
        "albums": image.normalized_albums(),
    }


def _facets(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    artists = Counter(item["artist"] for item in items if item.get("artist"))
    colours = Counter(item["colour"] for item in items if item.get("colour"))
    collections = Counter(
        album for item in items for album in item.get("albums", []) if album
    )
    eras = Counter(str(item["year"]) for item in items if item.get("year") is not None)

    def rows(values: Counter) -> list[dict[str, Any]]:
        return [
            {"value": value, "count": count} for value, count in values.most_common(100)
        ]

    return {
        "artists": rows(artists),
        "colours": rows(colours),
        "collections": rows(collections),
        "eras": rows(eras),
    }


def _source_payload(provider, available: set[str]) -> dict[str, Any]:
    enabled = provider.key in available
    return {
        "key": provider.key,
        "name": provider.name,
        "available": enabled,
        "requires_key": bool(provider.requires_key and not enabled),
        "hierarchical": provider.hierarchical_browse,
        "group": SOURCE_GROUPS.get(provider.key, "other"),
    }


def _library_folders(library: FraimicLibrary) -> list[dict[str, Any]]:
    """Return the compact My Library tree shown in the source rail."""
    images = list(library.images.values())
    favorite_count = sum(
        FAVORITES_ALBUM in image.normalized_albums() for image in images
    )
    counts = Counter(
        album
        for image in images
        for album in image.normalized_albums()
        if album not in {LIBRARY_ALBUM_DEFAULT, FAVORITES_ALBUM}
    )
    return [
        {"id": "", "title": "All pictures", "count": len(images)},
        {"id": "favorites", "title": "Favorites", "count": favorite_count},
        *[
            {"id": f"album:{name}", "title": name, "count": count}
            for name, count in sorted(
                counts.items(), key=lambda item: item[0].casefold()
            )
        ],
    ]


def _favorite_image_for_item(
    library: FraimicLibrary, source: str, item_id: str, item: dict[str, Any]
) -> LibraryImage | None:
    """Find the library original backing a gallery favorite, if any."""
    if source == LIBRARY_SOURCE:
        return library.get(item_id)
    favorite_id = item.get("favorite_image_id")
    if isinstance(favorite_id, str):
        return library.images.get(favorite_id)
    source_url = item.get("source_page_url") or item.get("download_url")
    return next(
        (
            image
            for image in library.images.values()
            if source_url and image.source_url == source_url
        ),
        None,
    )


async def _resolve_item(hass, entry, source: str, item_id: str) -> dict[str, Any]:
    library = _library(hass)
    if source == LIBRARY_SOURCE:
        return _library_payload(library.get(item_id), entry)
    candidate = await async_candidate_by_media_id(hass, entry, source, item_id)
    return _candidate_payload(candidate, entry, library)


def _slide_data(
    item: dict[str, Any],
    *,
    fit: str = "cover",
    tone: str = "balanced",
    crop: tuple[float, float, float, float] | None = None,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "name": item["title"],
        "kind": "picture",
        "fit": fit,
        "tone": tone,
        "show_header": False,
    }
    if item["source"] == LIBRARY_SOURCE:
        base["library_image"] = item["id"]
    else:
        base.update(
            {
                "provider": item["source"],
                "provider_item": item["id"],
            }
        )
    base["metadata"] = {
        key: item.get(key)
        for key in (
            "title",
            "artist",
            "source_name",
            "license",
            "attribution",
            "year",
            "description",
            "source_page_url",
            "download_url",
            "thumbnail_url",
            "image_url",
        )
        if item.get(key) is not None
    }
    if crop is not None:
        base["crop"] = list(crop)
    return SCREEN_SCHEMA(base)


def _cursor(value: str | None) -> int:
    if value in {None, ""}:
        return 0
    try:
        cursor = int(value)
    except ValueError:
        raise web.HTTPBadRequest(text="cursor must be a number") from None
    if cursor < 0 or cursor > MAX_GALLERY_OFFSET:
        raise web.HTTPBadRequest(text="cursor is outside the supported range")
    return cursor


def _crop(value: Any) -> tuple[float, float, float, float] | None:
    if value is None or value == "":
        return None
    try:
        raw = json.loads(value) if isinstance(value, str) else value
        return normalize_crop(raw)
    except (TypeError, ValueError, json.JSONDecodeError) as err:
        raise web.HTTPBadRequest(text=f"Invalid crop: {err}") from err


def _viewed_size(entry) -> tuple[int, int]:
    width = int(entry.data.get("width", 1600))
    height = int(entry.data.get("height", 1200))
    if entry.options.get("rotation", 0) in (90, 270):
        return height, width
    return width, height


def _image_content_type(data: bytes) -> str:
    from PIL import Image

    with Image.open(io.BytesIO(data)) as image:
        return Image.MIME.get(image.format or "", "application/octet-stream")


class GallerySourcesView(HomeAssistantView):
    url = "/api/fraimic/gallery/sources"
    name = "api:fraimic:gallery:sources"

    async def get(self, request: web.Request) -> web.Response:
        hass = request.app[KEY_HASS]
        entry = require_loaded_entry(hass, request.query.get("entry_id"))
        available = set(available_provider_keys(entry))
        library = _library(hass)
        return self.json(
            {
                "sources": [
                    {
                        "key": LIBRARY_SOURCE,
                        "name": "My library",
                        "available": True,
                        "requires_key": False,
                        "hierarchical": True,
                        "group": "library",
                        "count": len(library.images),
                        "children": _library_folders(library),
                    },
                    *[
                        _source_payload(provider, available)
                        for provider in PROVIDERS.values()
                    ],
                ]
            }
        )


class GallerySourceTreeView(HomeAssistantView):
    """Lazy source-folder navigation for the gallery sidebar."""

    url = "/api/fraimic/gallery/tree"
    name = "api:fraimic:gallery:tree"

    async def get(self, request: web.Request) -> web.Response:
        hass = request.app[KEY_HASS]
        entry = require_loaded_entry(hass, request.query.get("entry_id"))
        source = request.query.get("source", "")
        browse_id = request.query.get("browse_id", "").strip("/")
        if source == LIBRARY_SOURCE:
            library = _library(hass)
            return self.json(
                {
                    "title": "My library",
                    "folders": _library_folders(library),
                    "has_items": bool(library.images),
                }
            )
        provider = get_provider(source)
        if provider is None or not provider.hierarchical_browse:
            raise web.HTTPNotFound(text="This source has no folders")
        if source not in available_provider_keys(entry):
            raise web.HTTPConflict(text="This source is not configured")
        try:
            page = await async_browse_provider(hass, entry, source, browse_id)
        except (ArtFetchError, HomeAssistantError) as err:
            raise web.HTTPBadGateway(text=str(err)) from err
        return self.json(
            {
                "title": page.title,
                "folders": [
                    {
                        "id": folder.item_id,
                        "title": folder.title,
                        "count": folder.count,
                    }
                    for folder in page.folders
                ],
                "has_items": bool(page.candidates),
            }
        )


class GalleryBrowseView(HomeAssistantView):
    url = "/api/fraimic/gallery"
    name = "api:fraimic:gallery"

    async def get(self, request: web.Request) -> web.Response:
        hass = request.app[KEY_HASS]
        entry = require_loaded_entry(hass, request.query.get("entry_id"))
        source = request.query.get("source", "")
        browse_id = request.query.get("browse_id", "").strip("/")
        query = request.query.get("q", "").strip()
        refresh = request.query.get("refresh") in {"1", "true", "yes"}
        cursor = _cursor(request.query.get("cursor"))
        try:
            limit = min(
                GALLERY_LIMIT, max(3, int(request.query.get("limit", GALLERY_LIMIT)))
            )
        except ValueError:
            raise web.HTTPBadRequest(text="limit must be a number") from None
        if source == LIBRARY_SOURCE:
            images = sorted(
                _library(hass).images.values(),
                key=lambda image: image.uploaded_at,
                reverse=True,
            )
            title = "All pictures"
            if browse_id == "favorites":
                images = [
                    image
                    for image in images
                    if FAVORITES_ALBUM in image.normalized_albums()
                ]
                title = "Favorites"
            elif browse_id.startswith("album:"):
                album = browse_id.removeprefix("album:").strip()
                images = [
                    image for image in images if album in image.normalized_albums()
                ]
                title = album or "All pictures"
            items = [_library_payload(image, entry) for image in images]
            if query:
                needle = query.casefold()
                items = [
                    item
                    for item in items
                    if needle
                    in f"{item['title']} {item.get('artist') or ''}".casefold()
                ]
            total = len(items)
            items = items[cursor : cursor + limit]
            next_cursor = cursor + len(items) if cursor + len(items) < total else None
            return self.json(
                {
                    "results": items,
                    "total": total,
                    "next_cursor": str(next_cursor)
                    if next_cursor is not None
                    else None,
                    "facets": _facets(items),
                    "source_status": [{"source": source, "status": "ready"}],
                    "title": title,
                }
            )
        provider = get_provider(source)
        if provider is None:
            raise web.HTTPNotFound(text="Unknown source")
        if source not in available_provider_keys(entry):
            return self.json(
                {
                    "results": [],
                    "total": 0,
                    "facets": _facets([]),
                    "source_status": [{"source": source, "status": "needs_key"}],
                }
            )
        if browse_id:
            if not provider.hierarchical_browse:
                raise web.HTTPBadRequest(text="This source has no browse folders")
            try:
                browse_page = await async_browse_provider(
                    hass, entry, source, browse_id
                )
            except (ArtFetchError, HomeAssistantError) as err:
                return self.json(
                    {
                        "results": [],
                        "total": 0,
                        "facets": _facets([]),
                        "source_status": [
                            {"source": source, "status": "error", "detail": str(err)}
                        ],
                        "title": browse_id.rsplit("/", 1)[-1]
                        .replace("-", " ")
                        .title(),
                    }
                )
            candidates = list(browse_page.candidates)
            if query:
                needle = query.casefold()
                candidates = [
                    candidate
                    for candidate in candidates
                    if needle
                    in " ".join(
                        filter(None, (candidate.title, candidate.artist))
                    ).casefold()
                ]
            total = len(candidates)
            items = [
                _candidate_payload(candidate, entry, _library(hass))
                for candidate in candidates[cursor : cursor + limit]
            ]
            next_cursor = cursor + len(items) if cursor + len(items) < total else None
            return self.json(
                {
                    "results": items,
                    "total": total,
                    "next_cursor": str(next_cursor)
                    if next_cursor is not None
                    else None,
                    "facets": _facets(items),
                    "source_status": [{"source": source, "status": "ready"}],
                    "title": browse_page.title,
                }
            )
        try:
            candidates = await async_browse_candidates(
                hass,
                entry,
                source,
                cursor + limit,
                query=query or None,
                refresh=refresh,
            )
        except ArtFetchError as err:
            return self.json(
                {
                    "results": [],
                    "total": 0,
                    "facets": _facets([]),
                    "source_status": [
                        {"source": source, "status": "error", "detail": str(err)}
                    ],
                }
            )
        page = candidates[cursor : cursor + limit]
        items = [
            _candidate_payload(candidate, entry, _library(hass)) for candidate in page
        ]
        next_cursor = cursor + len(items) if len(page) == limit else None
        return self.json(
            {
                "results": items,
                "total": max(cursor + len(items), len(candidates)),
                "next_cursor": str(next_cursor) if next_cursor is not None else None,
                "facets": _facets(items),
                "source_status": [{"source": source, "status": "ready"}],
            }
        )


class GalleryDetailView(HomeAssistantView):
    url = "/api/fraimic/gallery/detail"
    name = "api:fraimic:gallery:detail"

    async def get(self, request: web.Request) -> web.Response:
        hass = request.app[KEY_HASS]
        entry = require_loaded_entry(hass, request.query.get("entry_id"))
        source = request.query.get("source")
        item_id = request.query.get("item_id")
        if not source or not item_id:
            raise web.HTTPBadRequest(text="source and item_id are required")
        try:
            item = await _resolve_item(hass, entry, source, item_id)
        except (ArtFetchError, HomeAssistantError) as err:
            return self.json_message(str(err), HTTPStatus.NOT_FOUND)
        preview_base = "/api/fraimic/gallery/preview?" + urlencode(
            {
                "entry_id": entry.entry_id,
                "source": source,
                "item_id": item_id,
            }
        )
        item.update(
            {
                "saved_crop": (
                    _library(hass).get(item_id).crop_for(*_viewed_size(entry))
                    if source == LIBRARY_SOURCE
                    else None
                ),
                "cover_preview_url": f"{preview_base}&fit=cover",
                "contain_preview_url": f"{preview_base}&fit=contain",
            }
        )
        return self.json(item)


class GalleryImageView(HomeAssistantView):
    url = "/api/fraimic/gallery/image"
    name = "api:fraimic:gallery:image"

    async def get(self, request: web.Request) -> web.Response:
        hass = request.app[KEY_HASS]
        entry = require_loaded_entry(hass, request.query.get("entry_id"))
        source = request.query.get("source")
        item_id = request.query.get("item_id")
        size = request.query.get("size", "full")
        if not source or not item_id or size not in {"thumbnail", "full"}:
            raise web.HTTPBadRequest(
                text="source, item_id, and a valid size are required"
            )
        try:
            image, content_type = await _async_gallery_image(
                hass, entry, source, item_id, thumbnail=size == "thumbnail"
            )
        except (ArtFetchError, HomeAssistantError, OSError) as err:
            raise web.HTTPBadGateway(text=str(err)) from err
        return web.Response(
            body=image,
            content_type=content_type,
            headers={
                "Cache-Control": (
                    "private, max-age="
                    f"{_browser_cache_seconds(hass, entry, 3600)}"
                )
            },
        )


class GalleryPreviewView(HomeAssistantView):
    url = "/api/fraimic/gallery/preview"
    name = "api:fraimic:gallery:preview"

    async def get(self, request: web.Request) -> web.Response:
        hass = request.app[KEY_HASS]
        entry = require_loaded_entry(hass, request.query.get("entry_id"))
        source = request.query.get("source")
        item_id = request.query.get("item_id")
        fit = request.query.get("fit", "cover")
        tone = request.query.get("tone", "balanced")
        crop = _crop(request.query.get("crop"))
        if (
            not source
            or not item_id
            or fit not in {"cover", "contain", "stretch"}
            or tone not in {"vivid", "balanced", "soft"}
        ):
            raise web.HTTPBadRequest(
                text="source, item_id, and a valid fit are required"
            )
        cache = hass.data.setdefault(DOMAIN, {}).setdefault("gallery_previews", {})
        render_settings = render_cache_key(
            resolve_render_params(entry, {"fit": fit})
        )
        key = (entry.entry_id, source, item_id, fit, tone, crop, render_settings)
        png = cache.get(key)
        if png is None:
            from .services import async_convert_for_entry

            try:
                if source == LIBRARY_SOURCE:
                    png = await _library(hass).async_render_adhoc_preview(
                        item_id,
                        entry,
                        list(crop) if crop is not None else None,
                        overrides={"fit": fit, "tone_name": tone},
                    )
                else:
                    art = await async_art_by_media_id(hass, entry, source, item_id)
                    _, png, _ = await async_convert_for_entry(
                        hass,
                        entry,
                        art.data,
                        {"fit": fit, "tone_name": tone, "crop": crop},
                        cache_id=artwork_source_cache_id(source, item_id),
                    )
            except (ArtFetchError, HomeAssistantError) as err:
                raise web.HTTPBadGateway(text=str(err)) from err
            if png is None:
                raise web.HTTPInternalServerError(text="No preview was rendered")
            if len(cache) >= 24:
                cache.pop(next(iter(cache)))
            cache[key] = png
        return web.Response(
            body=png,
            content_type="image/png",
            # Unlike an original, a preview also depends on frame options that
            # are not encoded in its URL. Keep browser freshness short; the
            # persistent render cache still makes a re-request inexpensive.
            headers={"Cache-Control": "private, max-age=600"},
        )


class GalleryActionView(HomeAssistantView):
    url = "/api/fraimic/gallery/action"
    name = "api:fraimic:gallery:action"

    async def post(self, request: web.Request) -> web.Response:
        _assert_admin(request)
        hass = request.app[KEY_HASS]
        try:
            body = await request.json()
        except ValueError:
            raise web.HTTPBadRequest(text="Body must be JSON") from None
        if not isinstance(body, dict):
            raise web.HTTPBadRequest(text="Body must be a JSON object")
        entry = require_loaded_entry(hass, body.get("entry_id"))
        source = body.get("source")
        item_id = body.get("item_id")
        action = body.get("action")
        if not isinstance(source, str) or not isinstance(item_id, str):
            raise web.HTTPBadRequest(text="source and item_id are required")
        try:
            fit = body.get("fit", "cover")
            tone = body.get("tone", "balanced")
            crop = _crop(body.get("crop"))
            if fit not in {"cover", "contain", "stretch"}:
                raise ValueError("Unknown fit")
            if fit != "cover":
                crop = None
            if tone not in {"vivid", "balanced", "soft"}:
                raise ValueError("Unknown tone")
            item = await _resolve_item(hass, entry, source, item_id)
            if source == LIBRARY_SOURCE and crop is not None:
                await _library(hass).async_set_crop(
                    item_id, *_viewed_size(entry), list(crop)
                )
            if action in {"favorite", "unfavorite"}:
                library = _library(hass)
                saved = _favorite_image_for_item(library, source, item_id, item)
                if action == "favorite" and saved is None:
                    art = await async_art_by_media_id(hass, entry, source, item_id)
                    extension = Path(
                        re.sub(r"[?#].*$", "", art.candidate.image_url)
                    ).suffix
                    filename = f"{art.candidate.title}{extension or '.jpg'}"
                    saved = await library.async_add_image(
                        art.data,
                        filename,
                        albums=[FAVORITES_ALBUM],
                        source_url=_source_page(art.candidate)
                        or art.candidate.image_url,
                        license_text=art.candidate.license,
                        attribution=art.candidate.attribution,
                    )
                elif saved is not None:
                    albums = saved.normalized_albums()
                    if action == "favorite" and FAVORITES_ALBUM not in albums:
                        albums.append(FAVORITES_ALBUM)
                    elif action == "unfavorite":
                        albums = [
                            album for album in albums if album != FAVORITES_ALBUM
                        ]
                        if not albums:
                            albums = [LIBRARY_ALBUM_DEFAULT]
                    saved = await library.async_update_image(
                        saved.image_id, albums=albums
                    )
                if action == "favorite" and saved is not None and crop is not None:
                    await library.async_set_crop(
                        saved.image_id, *_viewed_size(entry), list(crop)
                    )
                updated = await _resolve_item(hass, entry, source, item_id)
                return self.json(
                    {
                        "item": updated,
                        "favorite": action == "favorite",
                        "saved": saved.image_id if saved is not None else None,
                        "deleted": False,
                    }
                )
            data = _slide_data(item, fit=fit, tone=tone, crop=crop)
            slide = screen_from_dict(data, f"gallery_{uuid.uuid4().hex}")
            scheduler = entry.runtime_data.scheduler
            if action == "show_now":
                stopper = entry.runtime_data.stop_camera_loop
                if stopper is not None:
                    stopper()
                await scheduler.async_add_to_queue(slide, play_next=True, raw_data=data)
                await scheduler.async_next()
            elif action in {"play_next", "queue"}:
                if action == "play_next" and not scheduler.screens:
                    raise ValueError(
                        "Choose a playlist on this frame before playing next"
                    )
                await scheduler.async_add_to_queue(
                    slide,
                    play_next=action == "play_next",
                    insert_at=body.get("queue_index"),
                    raw_data=data,
                )
            elif action == "add_playlist":
                playlist_id = body.get("playlist_id")
                if not isinstance(playlist_id, str):
                    raise ValueError("playlist_id is required")
                await _manager(hass).async_add_slides(
                    playlist_id,
                    [data],
                    insert_at=body.get("playlist_index"),
                    before_slide_id=body.get("playlist_before_id"),
                )
                for candidate in hass.config_entries.async_entries(DOMAIN):
                    runtime = getattr(candidate, "runtime_data", None)
                    if (
                        runtime is not None
                        and runtime.scheduler.playlist_id == playlist_id
                    ):
                        await runtime.scheduler.async_refresh_playlist()
            elif action == "save":
                if source == LIBRARY_SOURCE:
                    return self.json({"item": item, "saved": item_id})
                art = await async_art_by_media_id(hass, entry, source, item_id)
                extension = Path(re.sub(r"[?#].*$", "", art.candidate.image_url)).suffix
                filename = f"{art.candidate.title}{extension or '.jpg'}"
                saved = await _library(hass).async_add_image(
                    art.data,
                    filename,
                    source_url=_source_page(art.candidate) or art.candidate.image_url,
                    license_text=art.candidate.license,
                    attribution=art.candidate.attribution,
                )
                if crop is not None:
                    await _library(hass).async_set_crop(
                        saved.image_id, *_viewed_size(entry), list(crop)
                    )
                item["saved"] = True
                return self.json({"item": item, "saved": saved.image_id})
            else:
                raise ValueError("Unknown gallery action")
        except (ArtFetchError, HomeAssistantError, ValueError) as err:
            return self.json_message(str(err), HTTPStatus.CONFLICT)
        return self.json({"item": await _resolve_item(hass, entry, source, item_id)})


def gallery_views() -> tuple[HomeAssistantView, ...]:
    return (
        GallerySourcesView(),
        GallerySourceTreeView(),
        GalleryBrowseView(),
        GalleryDetailView(),
        GalleryImageView(),
        GalleryPreviewView(),
        GalleryActionView(),
    )
