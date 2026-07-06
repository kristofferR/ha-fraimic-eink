"""Pure logic for curated art packs (no Home Assistant imports).

Catalog validation + the orientation matcher that assigns pack images to
frames when the installer auto-creates a scene.
"""

from __future__ import annotations

from typing import Any


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
            for key in ("title", "url", "filename"):
                if not isinstance(image.get(key), str) or not image[key]:
                    raise ValueError(f"Image in pack {pack_id!r} is missing {key!r}")
            if not image["url"].startswith("https://"):
                raise ValueError(f"Image URL in pack {pack_id!r} must be https")
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


def _remote_category(pack: dict[str, Any]) -> str:
    raw = pack.get("categories") or [pack.get("category") or "Art"]
    first = str(raw[0])
    return _REMOTE_CATEGORIES.get(first, first.replace("_", " ").title())


def map_remote_catalog(data: dict[str, Any], raw_base: str) -> list[dict[str, Any]]:
    """Map a frame-addons ``index.json`` into our internal pack shape.

    Unlike the bundled catalog (a packaging bug should fail loudly), remote
    content is third-party: anything malformed — and ``widget``-type packs,
    which are scripts for a different integration — is skipped, never fatal.
    """
    packs: list[dict[str, Any]] = []
    raw_base = raw_base.rstrip("/")
    for pack in data.get("packs") or []:
        if not isinstance(pack, dict) or pack.get("type") == "widget":
            continue
        pack_id = pack.get("id")
        name = pack.get("name")
        if not pack_id or not isinstance(pack_id, str) or not isinstance(name, str):
            continue
        images = []
        for image in pack.get("images") or []:
            if not isinstance(image, dict):
                continue
            path = image.get("path")
            filename = image.get("filename")
            if not path or not filename or not isinstance(path, str):
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
                    "source_url": image.get("commons_url"),
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
