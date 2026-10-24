"""Import Fraimic voice creations from the account gallery into the library.

Verified against the owner gallery on 2026-10-21 (``docs/firmware/cloud-protocol.md``,
"Albums and gallery"): voice items are ``upload_type == "audio"`` and carry the
original artwork. Their signed ``original_url`` expires after about an hour
(then 403); re-reading the item signs a fresh one. Imports are manual and
repeatable: the account id + upload id identify an item, so a repeat run or a
restart mid-import never adds it twice. No Home Assistant imports here.
"""

from __future__ import annotations

import logging
import mimetypes
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any, Protocol
from urllib.parse import urlsplit

from .cloud import (
    FraimicCloudAuthError,
    FraimicCloudClient,
    FraimicCloudError,
    cloud_timestamp,
)
from .const import MAX_SOURCE_BYTES
from .library_model import Creation, LibraryImage

_LOGGER = logging.getLogger(__name__)

VOICE_UPLOAD_TYPE = "audio"
CREATIONS_ALBUM = "Creations"
# Stops a gallery that keeps reporting ``has_next`` from looping forever.
MAX_GALLERY_PAGES = 200
_TITLE_CHARS = 60
_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")


class CreationLibrary(Protocol):
    """The parts of ``FraimicLibrary`` the import uses."""

    images: dict[str, LibraryImage]
    import_lock: Any

    async def async_add_image(
        self, data: bytes, filename: str, *, albums: list[str] | None = ..., creation: Creation | None = ...
    ) -> LibraryImage: ...


class CreationImportError(Exception):
    """The import stopped partway; the items already imported are kept."""


@dataclass
class ImportResult:
    imported: int = 0
    skipped: int = 0
    failed: int = 0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def creation_from_item(item: Any, account_id: str) -> Creation | None:
    """Provenance for a voice gallery item, or None for anything else."""
    if not isinstance(item, dict) or item.get("upload_type") != VOICE_UPLOAD_TYPE:
        return None
    created_at: float | None = None
    if isinstance(item.get("created_at"), str):
        try:
            created_at = cloud_timestamp(item["created_at"])
        except ValueError:
            pass
    return Creation.from_dict(
        {
            "account_id": account_id,
            "upload_id": item.get("upload_id"),
            "created_at": created_at,
            "transcript": item.get("transcript"),
            "style": item.get("style_name"),
            "orientation": item.get("orientation"),
            "crop": item.get("crop_params"),
            "metadata": item.get("metadata"),
        }
    )


def creation_filename(creation: Creation, content_type: str | None, url: str) -> str:
    """Library filename: the transcript's start, else the creation date."""
    if creation.transcript:
        title = " ".join(creation.transcript.split())
        if len(title) > _TITLE_CHARS:
            title = title[:_TITLE_CHARS].rsplit(" ", 1)[0].rstrip(",.;:") or title[:_TITLE_CHARS]
    elif creation.created_at is not None:
        date = datetime.fromtimestamp(creation.created_at, UTC).date().isoformat()
        title = f"Voice creation {date}"
    else:
        title = "Voice creation"
    return f"{title}{_suffix(content_type, url)}"


def _suffix(content_type: str | None, url: str) -> str:
    if content_type:
        suffix = mimetypes.guess_extension(content_type.split(";")[0].strip())
        if suffix in _IMAGE_SUFFIXES:
            return suffix
    suffix = PurePosixPath(urlsplit(url).path).suffix.lower()
    return suffix if suffix in _IMAGE_SUFFIXES else ".png"


async def async_import_creations(
    library: CreationLibrary, cloud: FraimicCloudClient
) -> ImportResult:
    """Add every voice creation not yet in the library to the Creations album.

    One item failing (expired URL that won't re-sign, not an image, ...) is
    counted and skipped. Each import is saved as it lands, so an interrupted
    run keeps what it finished and the next run picks up the rest.
    """
    account_id = await cloud.async_account_id()
    result = ImportResult()
    async with library.import_lock:
        known = {
            image.creation.key for image in library.images.values() if image.creation
        }
        page = 1
        while True:
            try:
                data = await cloud.async_gallery_page(page)
            except FraimicCloudError as err:
                if page == 1:
                    raise
                raise CreationImportError(
                    f"The gallery stopped answering on page {page} "
                    f"({result.imported} imported so far): {err}"
                ) from err
            for item in data["items"]:
                creation = creation_from_item(item, account_id)
                if creation is None:
                    continue
                if creation.key in known:
                    result.skipped += 1
                    continue
                try:
                    body, content_type, url = await _async_download_original(
                        cloud, item, creation.upload_id
                    )
                    await library.async_add_image(
                        body,
                        creation_filename(creation, content_type, url),
                        albums=[CREATIONS_ALBUM],
                        creation=creation,
                    )
                except FraimicCloudAuthError:
                    raise
                except Exception as err:  # noqa: BLE001 - one item must not stop the import
                    _LOGGER.warning(
                        "Could not import Fraimic creation %s: %s", creation.upload_id, err
                    )
                    result.failed += 1
                    continue
                known.add(creation.key)
                result.imported += 1
            if not data.get("has_next"):
                return result
            if page >= MAX_GALLERY_PAGES:
                raise CreationImportError(
                    f"The gallery still had more after {page} pages "
                    f"({result.imported} imported so far)"
                )
            page += 1


async def _async_download_original(
    cloud: FraimicCloudClient, item: dict[str, Any], upload_id: str
) -> tuple[bytes, str | None, str]:
    url = item.get("original_url")
    if isinstance(url, str) and url:
        try:
            body, content_type = await cloud.async_download(url, MAX_SOURCE_BYTES)
        except FraimicCloudError as err:
            if err.status != 403:
                raise
        else:
            return body, content_type, url
    # Expired (or missing): reading the item signs a fresh URL.
    fresh = (await cloud.async_gallery_item(upload_id)).get("original_url")
    if not isinstance(fresh, str) or not fresh:
        raise FraimicCloudError("Gallery item has no original")
    body, content_type = await cloud.async_download(fresh, MAX_SOURCE_BYTES)
    return body, content_type, fresh
