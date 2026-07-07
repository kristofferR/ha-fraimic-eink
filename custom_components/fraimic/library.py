"""Shared media library for Fraimic frames.

Stores uploaded originals once under ``<config>/fraimic_library/`` and caches
rendered ``.bin``/preview pairs per (resolution + conversion params), so
playlists, scenes, and repeat sends never pay the (seconds-long, CPU-bound)
OKLab dither cost twice for the same result.

Layout on disk:

    fraimic_library/
      manifest.json                     image metadata (albums, crops, ...)
      originals/{image_id}_{filename}   uploaded source, byte-exact
      thumbs/{image_id}.jpg             panel grid thumbnail (derived, on demand)
      renders/{image_id}/{WxH}_{hash}.bin/.png/.json   cached conversions

Only originals + manifest are canonical; everything else is a derivative that
can be regenerated (and is, by the background backfill worker).
"""

from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError

from .api import FraimicError
from .const import (
    DOMAIN,
    LIBRARY_ALBUM_DEFAULT,
    LIBRARY_DIR,
    LIBRARY_THUMB_SIZE,
    MAX_SOURCE_BYTES,
    MAX_SOURCE_PIXELS,
)
from .helpers import loaded_fraimic_entries, resolve_render_params
from .image_convert import convert_image
from .library_model import (
    LibraryImage,
    all_albums,
    manifest_from_dict,
    manifest_to_dict,
    normalize_crop,
    render_cache_key,
    resolution_key,
    safe_filename,
)

_LOGGER = logging.getLogger(__name__)

DATA_LIBRARY = "library"


@callback
def get_library(hass: HomeAssistant) -> FraimicLibrary | None:
    """Return the domain-wide library manager, if initialized."""
    return hass.data.get(DOMAIN, {}).get(DATA_LIBRARY)


class FraimicLibrary:
    """Domain-level image library shared by every configured frame."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.root = Path(hass.config.path(LIBRARY_DIR))
        self.originals_dir = self.root / "originals"
        self.thumbs_dir = self.root / "thumbs"
        self.renders_dir = self.root / "renders"
        self.manifest_path = self.root / "manifest.json"
        self.images: dict[str, LibraryImage] = {}
        self._manifest_lock = asyncio.Lock()
        self._backfill_queue: asyncio.Queue[str] = asyncio.Queue()
        self._backfill_pending: set[str] = set()
        self._backfill_task: asyncio.Task | None = None

    # ------------------------------------------------------------- lifecycle

    async def async_setup(self) -> None:
        """Create directories, load the manifest, start the backfill worker."""
        self.images = await self.hass.async_add_executor_job(self._setup_sync)
        self._backfill_task = self.hass.async_create_background_task(
            self._async_backfill_worker(), name="fraimic_library_backfill"
        )

    def _setup_sync(self) -> dict[str, LibraryImage]:
        for path in (self.root, self.originals_dir, self.thumbs_dir, self.renders_dir):
            path.mkdir(parents=True, exist_ok=True)
        if not self.manifest_path.exists():
            return {}
        try:
            data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as err:
            # Never wipe a manifest we failed to parse — move it aside so the
            # originals stay recoverable, and start empty.
            _LOGGER.error("Fraimic library manifest is unreadable (%s); starting fresh", err)
            try:
                self.manifest_path.rename(self.manifest_path.with_suffix(".corrupt"))
            except OSError:
                pass
            return {}
        return manifest_from_dict(data)

    async def async_shutdown(self) -> None:
        if self._backfill_task is not None:
            self._backfill_task.cancel()
            self._backfill_task = None

    async def _async_save_manifest(self) -> None:
        async with self._manifest_lock:
            data = manifest_to_dict(self.images)
            await self.hass.async_add_executor_job(self._write_manifest_sync, data)

    def _write_manifest_sync(self, data: dict[str, Any]) -> None:
        tmp = self.manifest_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.manifest_path)

    # ------------------------------------------------------------------ CRUD

    def get(self, image_id: str) -> LibraryImage:
        image = self.images.get(image_id)
        if image is None:
            raise HomeAssistantError(f"No library image with id {image_id}")
        return image

    def original_path(self, image: LibraryImage) -> Path:
        return self.originals_dir / f"{image.image_id}_{safe_filename(image.filename)}"

    async def async_add_image(
        self, data: bytes, filename: str, *, albums: list[str] | None = None
    ) -> LibraryImage:
        """Store an uploaded original and register it in the manifest."""
        if len(data) > MAX_SOURCE_BYTES:
            raise HomeAssistantError("Image is too large for the library")
        image_id = uuid.uuid4().hex[:12]
        filename = safe_filename(filename)
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        image = LibraryImage(
            image_id=image_id,
            filename=filename,
            content_type=content_type,
            uploaded_at=time.time(),
            albums=[a for a in (albums or []) if a.strip()] or [LIBRARY_ALBUM_DEFAULT],
        )

        def _store() -> tuple[int, int]:
            size = _probe_dimensions(data)
            if size[0] * size[1] > MAX_SOURCE_PIXELS:
                raise ValueError(f"image is too large ({size[0]}x{size[1]})")
            self.original_path(image).write_bytes(data)
            return size

        try:
            image.width, image.height = await self.hass.async_add_executor_job(_store)
        except ValueError as err:
            raise HomeAssistantError(f"Not a supported image: {err}") from err

        self.images[image_id] = image
        await self._async_save_manifest()
        self.schedule_backfill(image_id)
        return image

    async def async_delete_image(self, image_id: str) -> None:
        image = self.get(image_id)
        self.images.pop(image_id, None)
        self._backfill_pending.discard(image_id)
        await self._async_save_manifest()

        def _remove() -> None:
            self.original_path(image).unlink(missing_ok=True)
            (self.thumbs_dir / f"{image_id}.jpg").unlink(missing_ok=True)
            shutil.rmtree(self.renders_dir / image_id, ignore_errors=True)

        await self.hass.async_add_executor_job(_remove)

    async def async_update_image(
        self,
        image_id: str,
        *,
        albums: list[str] | None = None,
    ) -> LibraryImage:
        image = self.get(image_id)
        if albums is not None:
            image.albums = [a for a in albums if a.strip()] or [LIBRARY_ALBUM_DEFAULT]
        await self._async_save_manifest()
        return image

    async def async_set_crop(
        self, image_id: str, width: int, height: int, box: list[float] | None
    ) -> LibraryImage:
        """Set (or clear, with ``box=None``) the crop for one resolution.

        Every cached render at that resolution is stale afterwards, so they are
        deleted in the same step — a prefix match on the cache-file stem.
        """
        image = self.get(image_id)
        key = resolution_key(width, height)
        if box is None:
            image.crops.pop(key, None)
        else:
            image.crops[key] = list(normalize_crop(box))
        await self._async_save_manifest()
        await self.hass.async_add_executor_job(self._invalidate_renders_sync, image_id, key)
        self.schedule_backfill(image_id)
        return image

    def _invalidate_renders_sync(self, image_id: str, res_key: str) -> None:
        render_dir = self.renders_dir / image_id
        if not render_dir.is_dir():
            return
        for path in render_dir.iterdir():
            if path.name.startswith(f"{res_key}_"):
                path.unlink(missing_ok=True)

    # ---------------------------------------------------------------- albums

    def albums(self) -> list[str]:
        return all_albums(self.images)

    async def async_rename_album(self, old: str, new: str) -> None:
        if old == LIBRARY_ALBUM_DEFAULT:
            raise HomeAssistantError(f"The {LIBRARY_ALBUM_DEFAULT!r} album cannot be renamed")
        new = new.strip()
        if not new:
            raise HomeAssistantError("Album name cannot be empty")
        for image in self.images.values():
            image.albums = [new if album == old else album for album in image.normalized_albums()]
        await self._async_save_manifest()

    async def async_delete_album(self, name: str) -> None:
        if name == LIBRARY_ALBUM_DEFAULT:
            raise HomeAssistantError(f"The {LIBRARY_ALBUM_DEFAULT!r} album cannot be deleted")
        for image in self.images.values():
            image.albums = [a for a in image.normalized_albums() if a != name] or [
                LIBRARY_ALBUM_DEFAULT
            ]
        await self._async_save_manifest()

    # ------------------------------------------------------------- retrieval

    async def async_get_original(self, image_id: str) -> tuple[bytes, str]:
        image = self.get(image_id)
        path = self.original_path(image)
        try:
            data = await self.hass.async_add_executor_job(path.read_bytes)
        except OSError as err:
            raise HomeAssistantError(f"Library file for {image_id} is missing: {err}") from err
        return data, image.content_type

    async def async_get_thumbnail(self, image_id: str) -> bytes:
        image = self.get(image_id)
        thumb_path = self.thumbs_dir / f"{image_id}.jpg"

        def _thumb() -> bytes:
            if thumb_path.exists():
                return thumb_path.read_bytes()
            data = _make_thumbnail(self.original_path(image))
            thumb_path.write_bytes(data)
            return data

        try:
            return await self.hass.async_add_executor_job(_thumb)
        except (OSError, ValueError) as err:
            raise HomeAssistantError(f"Could not thumbnail {image_id}: {err}") from err

    # ------------------------------------------------------------- rendering

    async def async_render_for_entry(
        self,
        image_id: str,
        entry: ConfigEntry,
        overrides: dict | None = None,
    ) -> tuple[bytes, bytes | None, str]:
        """Return ``(bin, preview_png, mode)`` for one frame, via the cache."""
        image = self.get(image_id)
        params = resolve_render_params(entry, overrides)
        crop = image.crop_for(params["width"], params["height"])
        cache_params = dict(params)
        cache_params["crop"] = list(crop) if crop else None
        key = render_cache_key(cache_params)
        render_dir = self.renders_dir / image_id

        cached = await self.hass.async_add_executor_job(self._read_render_sync, render_dir, key)
        if cached is not None:
            return cached

        try:
            source = await self.hass.async_add_executor_job(
                self.original_path(image).read_bytes
            )
        except OSError as err:
            raise HomeAssistantError(
                f"Library file for {image_id} is missing: {err}"
            ) from err
        try:
            bin_data, preview_png, used_mode = await self.hass.async_add_executor_job(
                lambda: convert_image(source, **params, crop=crop)
            )
        except Exception as err:  # noqa: BLE001 - Pillow raises a variety of errors
            raise HomeAssistantError(f"Could not convert library image: {err}") from err

        try:
            await self.hass.async_add_executor_job(
                self._write_render_sync, render_dir, key, bin_data, preview_png, used_mode
            )
        except OSError as err:
            _LOGGER.warning("Could not write render cache for %s: %s", image_id, err)
        return bin_data, preview_png, used_mode

    def _read_render_sync(
        self, render_dir: Path, key: str
    ) -> tuple[bytes, bytes | None, str] | None:
        bin_path = render_dir / f"{key}.bin"
        png_path = render_dir / f"{key}.png"
        meta_path = render_dir / f"{key}.json"
        if not (bin_path.exists() and png_path.exists() and meta_path.exists()):
            return None
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            return bin_path.read_bytes(), png_path.read_bytes(), str(meta.get("mode", "auto"))
        except (OSError, ValueError):
            return None

    def _write_render_sync(
        self, render_dir: Path, key: str, bin_data: bytes, preview_png: bytes | None, mode: str
    ) -> None:
        render_dir.mkdir(parents=True, exist_ok=True)

        def _atomic_write(path: Path, write) -> None:
            tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
            write(tmp)
            tmp.replace(path)

        _atomic_write(render_dir / f"{key}.bin", lambda path: path.write_bytes(bin_data))
        if preview_png is not None:
            _atomic_write(
                render_dir / f"{key}.png", lambda path: path.write_bytes(preview_png)
            )
        _atomic_write(
            render_dir / f"{key}.json",
            lambda path: path.write_text(json.dumps({"mode": mode}), encoding="utf-8"),
        )

    async def async_send_to_entry(
        self,
        image_id: str,
        entry: ConfigEntry,
        overrides: dict | None = None,
    ) -> None:
        """Render (cache-aware) and upload one library image to one frame."""
        rendered = await self.async_render_for_entry(image_id, entry, overrides)
        image = self.get(image_id)
        await async_upload_rendered(entry, *rendered, media_title=image.filename)

    # -------------------------------------------------------------- backfill

    @callback
    def schedule_backfill(self, image_id: str) -> None:
        """Queue background render-cache generation for one image."""
        if image_id in self._backfill_pending:
            return
        self._backfill_pending.add(image_id)
        self._backfill_queue.put_nowait(image_id)

    @callback
    def schedule_full_backfill(self) -> None:
        """Queue a sweep over the whole library (e.g. after a frame loads)."""
        for image_id in self.images:
            self.schedule_backfill(image_id)

    async def _async_backfill_worker(self) -> None:
        """Serially pre-render default variants so sends are instant later.

        Strictly an optimization: any miss here is rendered on demand at send
        time, so failures only get logged.
        """
        while True:
            image_id = await self._backfill_queue.get()
            self._backfill_pending.discard(image_id)
            if image_id not in self.images:
                continue
            for entry in loaded_fraimic_entries(self.hass):
                try:
                    await self.async_render_for_entry(image_id, entry)
                except HomeAssistantError as err:
                    _LOGGER.warning(
                        "Backfill render of %s for %s failed: %s",
                        image_id,
                        entry.title,
                        err,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as err:  # noqa: BLE001 - backfill is best-effort
                    _LOGGER.warning(
                        "Backfill render of %s for %s failed unexpectedly: %s",
                        image_id,
                        getattr(entry, "title", entry.entry_id),
                        err,
                    )


async def async_upload_rendered(
    entry: ConfigEntry,
    bin_data: bytes,
    preview_png: bytes | None,
    mode: str,
    *,
    media_title: str | None = None,
) -> None:
    """Upload an already-rendered buffer to one frame and update its preview.

    Shared by direct library sends and scene activation (which pre-renders all
    frames first, then uploads concurrently).
    """
    runtime = entry.runtime_data
    async with runtime.upload_lock:
        try:
            await runtime.client.upload_image(bin_data)
        except FraimicError as err:
            raise HomeAssistantError(f"Could not upload to the frame: {err}") from err
        runtime.last_art = None
        runtime.media_title = media_title
        if preview_png:
            runtime.last_preview = preview_png
            if runtime.preview_image is not None:
                runtime.preview_image.set_preview(preview_png, mode)
        await runtime.coordinator.async_request_refresh()
        runtime.coordinator.async_update_listeners()


def _probe_dimensions(data: bytes) -> tuple[int, int]:
    """Return the display (EXIF-corrected) dimensions of an encoded image.

    Only the header is decoded. Raises ValueError for non-images — this is the
    upload-time validation that keeps junk out of the library.
    """
    import io

    from PIL import Image, UnidentifiedImageError

    from .image_convert import _ensure_extra_decoders

    _ensure_extra_decoders()
    try:
        with Image.open(io.BytesIO(data)) as img:
            width, height = img.size
            orientation = img.getexif().get(0x0112)
    except (UnidentifiedImageError, OSError) as err:
        raise ValueError("undecodable image data") from err
    # Orientations 5-8 transpose the axes; the library stores display-space
    # dimensions because that's the space crop boxes are defined in.
    if orientation in (5, 6, 7, 8):
        width, height = height, width
    return width, height


def _make_thumbnail(original: Path) -> bytes:
    """Render the panel-grid JPEG thumbnail for one original."""
    import io

    from PIL import Image, ImageOps

    from .image_convert import _ensure_extra_decoders

    _ensure_extra_decoders()
    with Image.open(original) as img:
        img = ImageOps.exif_transpose(img)
        img.thumbnail((LIBRARY_THUMB_SIZE, LIBRARY_THUMB_SIZE))
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()
