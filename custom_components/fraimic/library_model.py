"""Pure data model for the Fraimic media library.

No Home Assistant imports here — everything in this module is plain Python so
it can be unit-tested standalone (like ``image_convert``). The I/O and HA
wiring live in ``library.py``.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any

from .const import LIBRARY_ALBUM_DEFAULT

# Bump when the render pipeline changes output for identical params (palette
# tweaks, dither fixes, ...) so every cached .bin is invalidated at once.
RENDER_CACHE_VERSION = 1

MANIFEST_VERSION = 1

_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


def safe_filename(name: str) -> str:
    """Reduce an arbitrary upload filename to a filesystem-safe form."""
    name = _SAFE_FILENAME.sub("_", name.strip().strip("."))
    return name[-80:] or "image"


def resolution_key(width: int, height: int) -> str:
    """Canonical string key for a frame resolution ("1600x1200")."""
    return f"{width}x{height}"


def normalize_crop(box: Any) -> tuple[float, float, float, float]:
    """Validate a normalized crop box, returning it as a float 4-tuple.

    Raises ValueError on anything that isn't an ordered, non-degenerate
    (x0, y0, x1, y1) box within 0.0-1.0.
    """
    try:
        x0, y0, x1, y1 = (float(v) for v in box)
    except (TypeError, ValueError) as err:
        raise ValueError(f"Crop box must be four numbers, got {box!r}") from err
    for value in (x0, y0, x1, y1):
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"Crop coordinates must be within 0.0-1.0, got {box!r}")
    if x1 - x0 < 0.01 or y1 - y0 < 0.01:
        raise ValueError(f"Crop box {box!r} is empty or too small")
    return (x0, y0, x1, y1)


def render_cache_key(params: dict[str, Any]) -> str:
    """Deterministic cache filename stem for one rendered variant.

    ``params`` is the full resolved conversion parameter dict (resolution, fit,
    rotate, mode, saturation/contrast/sharpen/tone, crop, ...). The stem leads
    with the resolution so a per-resolution invalidation (crop changed) can be
    a simple prefix match on the files in the image's render directory.
    """
    payload = dict(params)
    payload["_v"] = RENDER_CACHE_VERSION
    digest = hashlib.sha1(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:16]
    return f"{params['width']}x{params['height']}_{digest}"


@dataclass
class LibraryImage:
    """One image in the shared library."""

    image_id: str
    filename: str
    content_type: str
    uploaded_at: float
    width: int | None = None
    height: int | None = None
    albums: list[str] = field(default_factory=lambda: [LIBRARY_ALBUM_DEFAULT])
    # Saved manual crops, keyed by resolution_key(): [x0, y0, x1, y1] normalized.
    crops: dict[str, list[float]] = field(default_factory=dict)

    def normalized_albums(self) -> list[str]:
        """Albums with duplicates removed and the default as fallback."""
        seen: list[str] = []
        for album in self.albums:
            album = album.strip()
            if album and album not in seen:
                seen.append(album)
        return seen or [LIBRARY_ALBUM_DEFAULT]

    def crop_for(self, width: int, height: int) -> tuple[float, float, float, float] | None:
        """Return the saved crop for a resolution, if any."""
        box = self.crops.get(resolution_key(width, height))
        if box is None:
            return None
        try:
            return normalize_crop(box)
        except ValueError:
            # A manifest edited by hand (or an older buggy write) must not make
            # the image unsendable; ignore the bad crop instead.
            return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "image_id": self.image_id,
            "filename": self.filename,
            "content_type": self.content_type,
            "uploaded_at": self.uploaded_at,
            "width": self.width,
            "height": self.height,
            "albums": self.normalized_albums(),
            "crops": self.crops,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LibraryImage:
        crops = data.get("crops") or {}
        if not isinstance(crops, dict):
            crops = {}
        parsed_crops: dict[str, list[float]] = {}
        for key, value in crops.items():
            try:
                parsed_crops[str(key)] = list(value)
            except TypeError:
                continue
        return cls(
            image_id=str(data["image_id"]),
            filename=str(data.get("filename") or "image"),
            content_type=str(data.get("content_type") or "application/octet-stream"),
            uploaded_at=float(data.get("uploaded_at") or 0.0),
            width=data.get("width"),
            height=data.get("height"),
            albums=list(data.get("albums") or [LIBRARY_ALBUM_DEFAULT]),
            crops=parsed_crops,
        )


def manifest_to_dict(images: dict[str, LibraryImage]) -> dict[str, Any]:
    return {
        "version": MANIFEST_VERSION,
        "images": {image_id: image.to_dict() for image_id, image in images.items()},
    }


def manifest_from_dict(data: Any) -> dict[str, LibraryImage]:
    """Parse a manifest dict, skipping entries too broken to load."""
    images: dict[str, LibraryImage] = {}
    if not isinstance(data, dict):
        return images
    raw_images = data.get("images") or {}
    if not isinstance(raw_images, dict):
        return images
    for image_id, raw in raw_images.items():
        try:
            raw = dict(raw)
            raw.setdefault("image_id", image_id)
            images[str(image_id)] = LibraryImage.from_dict(raw)
        except (TypeError, ValueError, KeyError):
            continue
    return images


def all_albums(images: dict[str, LibraryImage]) -> list[str]:
    """Sorted album names across the library; the default album always exists."""
    names = {LIBRARY_ALBUM_DEFAULT}
    for image in images.values():
        names.update(image.normalized_albums())
    return sorted(names, key=lambda name: (name != LIBRARY_ALBUM_DEFAULT, name.lower()))
