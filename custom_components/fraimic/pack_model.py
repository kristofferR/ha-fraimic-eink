"""Pure logic for curated art packs (no Home Assistant imports).

Catalog validation + the orientation matcher that assigns pack images to
frames when the installer auto-creates a scene.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlsplit


def validate_catalog(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the catalog's packs, raising ValueError on a malformed catalog.

    The catalog ships inside the integration, so a failure here is a packaging
    bug — better one loud error than a half-working Add-ons tab.
    """
    packs = data.get("packs")
    if not isinstance(packs, list) or not packs:
        raise ValueError("Catalog has no packs")
    seen_ids: set[str] = set()
    for pack in packs:
        pack_id = pack.get("id")
        if not pack_id or not isinstance(pack_id, str):
            raise ValueError(f"Pack without a valid id: {pack!r}")
        if pack_id in seen_ids:
            raise ValueError(f"Duplicate pack id {pack_id!r}")
        seen_ids.add(pack_id)
        for key in ("name", "category", "attribution"):
            if not isinstance(pack.get(key), str) or not pack[key]:
                raise ValueError(f"Pack {pack_id!r} is missing {key!r}")
        images = pack.get("images")
        if not isinstance(images, list) or not images:
            raise ValueError(f"Pack {pack_id!r} has no images")
        for image in images:
            for key in ("title", "url", "preview_url", "filename"):
                if not isinstance(image.get(key), str) or not image[key]:
                    raise ValueError(f"Image in pack {pack_id!r} is missing {key!r}")
            for key in ("url", "preview_url"):
                if not image[key].startswith("https://"):
                    raise ValueError(f"Image {key} in pack {pack_id!r} must be https")
    return packs


# dsackr/frame-addons category ids → display names (unknown ids title-case).
_REMOTE_CATEGORIES = {
    "famous_artists": "Famous Artists",
    "seasons": "Seasonal & Holiday",
    "history": "History",
    "nature": "Nature",
    "architecture": "Architecture",
    "productivity": "Productivity",
    "speed": "Speed",
}

# Prefix for remote pack ids so they can never collide with bundled ones.
REMOTE_PACK_PREFIX = "fa-"

# Reframed exposes hundreds of live collections/tags/artists. Catalog rows are
# deliberately lazy; the installer resolves at most this many current images
# from the selected page so one pack cannot unexpectedly consume the library.
REFRAMED_PACK_PREFIX = "rg-"
REFRAMED_PACK_LIMIT = 24
REFRAMED_FALLBACK_COVER = "https://www.reframed.gallery/favicon.ico"

# Wallhaven's search API returns 24 wallpapers per page. Its packs use the
# same lazy shape as Reframed: the catalog is instant, while gallery/install
# resolves the current first page for the selected feed or filter.
WALLHAVEN_PACK_PREFIX = "wh-"
WALLHAVEN_PACK_LIMIT = 24
WALLHAVEN_FALLBACK_COVER = "https://wallhaven.cc/favicon.ico"


def _remote_category(pack: dict[str, Any]) -> str:
    categories = pack.get("categories")
    if isinstance(categories, list) and categories:
        first = str(categories[0])
    else:
        category = pack.get("category")
        first = category if isinstance(category, str) and category else "Art"
    return _REMOTE_CATEGORIES.get(first, first.replace("_", " ").title())


def map_remote_catalog(data: dict[str, Any], raw_base: str) -> list[dict[str, Any]]:
    """Map a frame-addons ``index.json`` into our internal pack shape.

    Unlike the bundled catalog (a packaging bug should fail loudly), remote
    content is third-party: anything malformed — and ``widget``-type packs,
    which are scripts for a different integration — is skipped, never fatal.
    """
    packs: list[dict[str, Any]] = []
    if not isinstance(data, dict):
        return packs
    remote_packs = data.get("packs") or []
    if not isinstance(remote_packs, list):
        return packs
    raw_base = raw_base.rstrip("/")
    for pack in remote_packs:
        if not isinstance(pack, dict) or pack.get("type") == "widget":
            continue
        pack_id = pack.get("id")
        name = pack.get("name")
        if not pack_id or not isinstance(pack_id, str) or not isinstance(name, str):
            continue
        raw_images = pack.get("images") or []
        if not isinstance(raw_images, list):
            continue
        images = []
        for image in raw_images:
            if not isinstance(image, dict):
                continue
            path = image.get("path")
            filename = image.get("filename")
            if (
                not path
                or not filename
                or not isinstance(path, str)
                or not isinstance(filename, str)
            ):
                continue
            url = f"{raw_base}/{path.lstrip('/')}"
            images.append(
                {
                    "title": str(image.get("title") or filename),
                    "url": url,
                    # Prefix so remote filenames can't collide across packs.
                    "filename": f"{pack_id}_{filename}",
                    # GitHub-raw images are hot-linkable; galleries use them directly.
                    "preview_url": url,
                    "source_url": _optional_string(image.get("commons_url")),
                    "license": _optional_string(image.get("license")),
                    "attribution": _optional_string(image.get("attribution")),
                }
            )
        if not images:
            continue
        cover = pack.get("cover")
        packs.append(
            {
                "id": f"{REMOTE_PACK_PREFIX}{pack_id}",
                "name": name,
                "category": _remote_category(pack),
                "description": str(pack.get("description") or ""),
                "attribution": str(pack.get("license") or "See per-image sources")
                + " — content from dsackr/frame-addons",
                "cover_url": f"{raw_base}/{str(cover).lstrip('/')}"
                if cover
                else images[0]["url"],
                "images": images,
            }
        )
    return packs


def make_reframed_pack(
    provider_path: str,
    name: str,
    category: str,
    *,
    cover_url: str | None = None,
    source_count: int | None = None,
) -> dict[str, Any]:
    """Build a lazy catalog row for one Reframed browse folder."""
    normalized = provider_path.strip("/")
    pack_id = f"{REFRAMED_PACK_PREFIX}{normalized.replace('/', '-')}"
    if source_count is None:
        image_count = REFRAMED_PACK_LIMIT
        description = (
            "Current artwork from Reframed Gallery. "
            f"Installs up to {REFRAMED_PACK_LIMIT}."
        )
    else:
        image_count = min(source_count, REFRAMED_PACK_LIMIT)
        description = (
            f"{source_count} artworks from Reframed Gallery. "
            f"Installs up to {REFRAMED_PACK_LIMIT}."
        )
    return {
        "id": pack_id,
        "name": name,
        "category": category,
        "description": description,
        "attribution": "Artwork via Reframed Gallery; see each image source",
        "cover_url": cover_url or REFRAMED_FALLBACK_COVER,
        "images": [],
        "image_count": image_count,
        "provider_key": "reframed",
        "provider_path": normalized,
    }


def reframed_filename(
    title: str, image_url: str, attribution: str | None = None
) -> str:
    """Use ``Artist - Artwork`` as the readable library filename."""
    suffix = PurePosixPath(urlsplit(image_url).path).suffix.lower()
    if suffix not in (".avif", ".heic", ".heif", ".jpeg", ".jpg", ".png", ".webp"):
        suffix = ".jpg"
    title = title.strip() or "Untitled"
    artist = None
    if attribution:
        _attributed_title, separator, credit = attribution.partition(" — ")
        if separator:
            artist = credit.removesuffix(", Reframed Gallery").strip() or None
    stem = f"{artist} - {title}" if artist else title
    return f"{stem}{suffix}"


def make_wallhaven_pack(
    provider_path: str,
    name: str,
    category: str,
    *,
    cover_url: str | None = None,
) -> dict[str, Any]:
    """Build a lazy catalog row for one Wallhaven feed or filter."""
    normalized = provider_path.strip("/")
    pack_id = f"{WALLHAVEN_PACK_PREFIX}{normalized.replace('/', '-').lower()}"
    return {
        "id": pack_id,
        "name": name,
        "category": category,
        "description": (
            "Current SFW wallpapers from Wallhaven. "
            f"Installs up to {WALLHAVEN_PACK_LIMIT}."
        ),
        "attribution": "Wallpapers via Wallhaven; see each image source",
        "cover_url": cover_url or WALLHAVEN_FALLBACK_COVER,
        "images": [],
        "image_count": WALLHAVEN_PACK_LIMIT,
        "provider_key": "wallhaven",
        "provider_path": normalized,
    }


def wallhaven_filename(title: str, image_url: str, artist: str | None = None) -> str:
    """Use ``Artist - Title`` when Wallhaven supplies an uploader."""
    suffix = PurePosixPath(urlsplit(image_url).path).suffix.lower()
    if suffix not in (".avif", ".heic", ".heif", ".jpeg", ".jpg", ".png", ".webp"):
        suffix = ".jpg"
    title = title.strip() or "Untitled"
    artist = artist.strip() if artist else None
    stem = f"{artist} - {title}" if artist else title
    return f"{stem}{suffix}"


def _materialize_provider_pack(
    pack: dict[str, Any],
    candidates: list[Any],
    *,
    limit: int,
    fallback_cover: str,
    filename: Callable[[Any, str, str], str],
) -> dict[str, Any]:
    """Fill one lazy provider pack from a bounded candidate list."""
    images: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for candidate in candidates:
        item_id = str(getattr(candidate, "item_id", ""))
        image_url = str(getattr(candidate, "image_url", ""))
        if not item_id or item_id in seen_ids or not image_url.startswith("https://"):
            continue
        seen_ids.add(item_id)
        title = str(getattr(candidate, "title", "") or "Untitled").strip()
        extra = getattr(candidate, "extra", None)
        source_url = extra.get("source_url") if isinstance(extra, dict) else None
        images.append(
            {
                "title": title,
                "url": image_url,
                "preview_url": str(getattr(candidate, "thumb_url", "") or image_url),
                "filename": filename(candidate, title, image_url),
                "source_url": _optional_string(source_url),
                "license": _optional_string(getattr(candidate, "license", None)),
                "attribution": _optional_string(
                    getattr(candidate, "attribution", None)
                ),
            }
        )
        if len(images) >= limit:
            break

    materialized = {**pack, "images": images, "image_count": len(images)}
    if images and pack.get("cover_url") == fallback_cover:
        materialized["cover_url"] = images[0]["preview_url"]
    return materialized


def materialize_reframed_pack(
    pack: dict[str, Any], candidates: list[Any]
) -> dict[str, Any]:
    """Fill a lazy Reframed pack from current provider candidates."""
    return _materialize_provider_pack(
        pack,
        candidates,
        limit=REFRAMED_PACK_LIMIT,
        fallback_cover=REFRAMED_FALLBACK_COVER,
        filename=lambda candidate, title, image_url: reframed_filename(
            title,
            image_url,
            _optional_string(getattr(candidate, "attribution", None)),
        ),
    )


def materialize_wallhaven_pack(
    pack: dict[str, Any], candidates: list[Any]
) -> dict[str, Any]:
    """Fill a lazy Wallhaven pack from current provider candidates."""
    return _materialize_provider_pack(
        pack,
        candidates,
        limit=WALLHAVEN_PACK_LIMIT,
        fallback_cover=WALLHAVEN_FALLBACK_COVER,
        filename=lambda candidate, title, image_url: wallhaven_filename(
            title,
            image_url,
            _optional_string(getattr(candidate, "artist", None)),
        ),
    )


def _optional_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _is_landscape(width: int | None, height: int | None) -> bool | None:
    if not width or not height:
        return None
    if width == height:
        return None  # square fits either orientation
    return width > height


def match_images_to_frames(
    frames: list[tuple[str, int, int]],
    images: list[tuple[str, int | None, int | None]],
) -> dict[str, str]:
    """Assign one pack image per frame, preferring matching orientation.

    ``frames``: (entry_id, effective_width, effective_height) — effective means
    the mount rotation is already applied. ``images``: (image_id, width,
    height). Each image is used once before any repeats, so a wall of frames
    gets variety; a frame with no orientation match still gets *an* image.
    """
    assignments: dict[str, str] = {}
    used: set[str] = set()

    def pick(frame_landscape: bool | None, allow_used: bool) -> str | None:
        for image_id, width, height in images:
            if not allow_used and image_id in used:
                continue
            image_landscape = _is_landscape(width, height)
            if (
                frame_landscape is None
                or image_landscape is None
                or image_landscape == frame_landscape
            ):
                return image_id
        return None

    for entry_id, width, height in frames:
        frame_landscape = _is_landscape(width, height)
        image_id = (
            pick(frame_landscape, allow_used=False)
            # All matching images used: any unused image beats a duplicate.
            or pick(None, allow_used=False)
            # More frames than images: repeat, but keep the orientation match.
            or pick(frame_landscape, allow_used=True)
            or pick(None, allow_used=True)
        )
        if image_id is not None:
            assignments[entry_id] = image_id
            used.add(image_id)
    return assignments
