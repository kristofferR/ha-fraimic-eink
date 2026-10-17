"""Turn one auto mode source into one concrete picture slide.

Online picks become fixed ``provider_item`` slides whose original is already
in the artwork cache, so the scheduler can prepare and preview them long
before they are due. Returns None when a source has nothing new to offer.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .auto_mode import (
    SOURCE_PLAYLIST,
    SOURCE_SHUFFLE,
    AutoHistory,
    AutoSettings,
    AutoSource,
    picture_key,
)
from .const import ATTR_FIT, FIT_COVER, PROVIDER_SHUFFLE
from .gallery_http import (
    LIBRARY_SOURCE,
    candidate_source_page,
    library_folder_images,
    picture_slide_data,
)
from .library import get_library
from .providers import get_provider
from .providers.base import ArtCandidate
from .providers.curation import acceptable_for_fit
from .providers.ha import (
    async_art_by_media_id,
    async_browse_provider,
    async_fetch_art,
    async_remember_candidate,
)
from .render.display import viewed_size
from .render.schema import ScreenConfig, screen_from_dict

if TYPE_CHECKING:
    from .coordinator import FraimicConfigEntry
    from .playlists import PlaylistManager

# Random online draws that land on something shown recently are retried.
RANDOM_ATTEMPTS = 3
# Folders holding only subfolders (Reframed "Collections") pick one at random.
MAX_FOLDER_DEPTH = 2


async def async_resolve_pick(
    hass: HomeAssistant,
    entry: FraimicConfigEntry,
    settings: AutoSettings,
    source: AutoSource,
    history: AutoHistory,
    *,
    exclude: set[str],
    playlists: PlaylistManager | None,
) -> ScreenConfig | None:
    """One new slide from ``source``, honouring repeat avoidance."""
    picker = _Picker(hass, entry, settings, history, exclude)
    if source.kind == SOURCE_PLAYLIST:
        return picker.from_playlist(playlists, source.playlist_id)
    if source.kind == SOURCE_SHUFFLE:
        return await picker.random_online(PROVIDER_SHUFFLE, None)
    if source.source == LIBRARY_SOURCE:
        return picker.from_library(source.browse_id, source.query)
    if source.browse_id:
        return await picker.from_folder(source.source, source.browse_id, source.query)
    return await picker.random_online(source.source, source.query or None)


class _Picker:
    def __init__(
        self,
        hass: HomeAssistant,
        entry: FraimicConfigEntry,
        settings: AutoSettings,
        history: AutoHistory,
        exclude: set[str],
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.settings = settings
        self.history = history
        self.exclude = exclude
        self.now = dt_util.utcnow()
        self.fit = settings.fit or entry.options.get(ATTR_FIT, FIT_COVER)

    def _choose(self, keys: list[str]) -> str | None:
        return self.history.choose(
            keys, self.settings.avoid_repeats_days, self.now, exclude=self.exclude
        )

    def _fits(self, width: int | None, height: int | None) -> bool | None:
        """Orientation check; None when the dimensions are unknown."""
        if not width or not height:
            return None
        target_w, target_h = viewed_size(self.entry)
        return acceptable_for_fit(width, height, target_w, target_h, self.fit)

    def _suitable[T](
        self, pool: list[T], dims: Callable[[T], tuple[int | None, int | None]]
    ) -> list[T]:
        """Prefer art that suits the frame; strict mode requires known matches."""
        verdicts = [self._fits(*dims(item)) for item in pool]
        if self.settings.strict_orientation:
            return [item for item, ok in zip(pool, verdicts, strict=True) if ok is True]
        good = [item for item, ok in zip(pool, verdicts, strict=True) if ok is not False]
        if any(verdicts):
            return good
        return pool

    def _slide(self, item: dict[str, Any], *, caption: bool = False) -> ScreenConfig:
        data = picture_slide_data(item, fit=self.settings.fit, tone=self.settings.tone)
        if caption:
            data["caption"] = True
        return screen_from_dict(data, "auto")

    async def _candidate_slide(self, candidate: ArtCandidate) -> ScreenConfig:
        await async_remember_candidate(self.hass, self.entry, candidate)
        provider = get_provider(candidate.provider)
        return self._slide(
            {
                "source": candidate.provider,
                "id": candidate.item_id,
                "title": candidate.title or "Artwork",
                "artist": candidate.artist,
                "source_name": provider.name if provider else candidate.provider,
                "license": candidate.license,
                "attribution": candidate.attribution or None,
                "source_page_url": candidate_source_page(candidate),
                "download_url": candidate.image_url,
            },
            caption=self.settings.caption,
        )

    async def random_online(
        self, provider_key: str, query: str | None
    ) -> ScreenConfig | None:
        recent = self.history.recent(self.settings.avoid_repeats_days, self.now)
        for _attempt in range(RANDOM_ATTEMPTS):
            art = await async_fetch_art(
                self.hass, self.entry, provider_key, query=query, fit=self.fit
            )
            candidate = art.candidate
            key = f"provider:{candidate.provider}:{candidate.item_id}"
            if key in recent or key in self.exclude:
                continue
            if self.settings.strict_orientation:
                width, height = candidate.width, candidate.height
                if not width or not height:
                    width, height = await self.hass.async_add_executor_job(
                        _decode_dims, art.data
                    )
                if not self._fits(width, height):
                    continue
            return await self._candidate_slide(candidate)
        return None

    async def from_folder(
        self, provider_key: str, browse_id: str, query: str
    ) -> ScreenConfig | None:
        page = await async_browse_provider(self.hass, self.entry, provider_key, browse_id)
        for _depth in range(MAX_FOLDER_DEPTH):
            if page.candidates or not page.folders:
                break
            folder = random.choice(page.folders)
            page = await async_browse_provider(
                self.hass, self.entry, provider_key, folder.item_id
            )
        candidates = list(page.candidates)
        if query:
            needle = query.casefold()
            candidates = [
                c
                for c in candidates
                if needle in " ".join(filter(None, (c.title, c.artist))).casefold()
            ]
        if self.settings.strict_orientation:
            candidates = [
                c for c in candidates if self._fits(c.width, c.height) is not False
            ]
        else:
            candidates = self._suitable(candidates, lambda c: (c.width, c.height))
        by_key = {f"provider:{c.provider}:{c.item_id}": c for c in candidates}
        for _attempt in range(RANDOM_ATTEMPTS):
            key = self._choose(list(by_key))
            if key is None:
                return None
            candidate = by_key.pop(key)
            if self.settings.strict_orientation and self._fits(
                candidate.width, candidate.height
            ) is None:
                try:
                    art = await async_art_by_media_id(
                        self.hass, self.entry, candidate.provider, candidate.item_id
                    )
                    width, height = await self.hass.async_add_executor_job(
                        _decode_dims, art.data
                    )
                except (HomeAssistantError, OSError, ValueError):
                    continue
                if not self._fits(width, height):
                    continue
            return await self._candidate_slide(candidate)
        return None

    def from_library(self, browse_id: str, query: str) -> ScreenConfig | None:
        library = get_library(self.hass)
        if library is None:
            raise HomeAssistantError("The picture library is not loaded")
        _title, images = library_folder_images(self.hass, library, browse_id)
        if query:
            needle = query.casefold()
            images = [
                image
                for image in images
                if needle
                in f"{Path(image.filename).stem} {image.attribution or ''}".casefold()
            ]
        images = self._suitable(images, lambda image: (image.width, image.height))
        by_key = {f"library:{image.image_id}": image for image in images}
        key = self._choose(list(by_key))
        if key is None:
            return None
        image = by_key[key]
        return self._slide(
            {
                "source": LIBRARY_SOURCE,
                "id": image.image_id,
                "title": Path(image.filename).stem or "Untitled",
                "artist": image.attribution,
                "license": image.license,
                "attribution": image.attribution,
                "source_page_url": image.source_url,
            }
        )

    def from_playlist(
        self, playlists: PlaylistManager | None, playlist_id: str
    ) -> ScreenConfig | None:
        if playlists is None or playlists.get(playlist_id) is None:
            raise HomeAssistantError("This playlist no longer exists")
        # Playlist slides keep their own look; only repeat avoidance applies.
        slides = {
            picture_key(slide) or f"slide:{playlist_id}:{slide.screen_id}": slide
            for slide in playlists.render_slides(playlist_id)
            if slide.enabled
        }
        key = self._choose(list(slides))
        return slides[key] if key else None


def _decode_dims(data: bytes) -> tuple[int, int]:
    import io

    from PIL import Image

    with Image.open(io.BytesIO(data)) as image:
        return image.size
