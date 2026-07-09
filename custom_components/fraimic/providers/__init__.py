"""Online image providers: museum art, daily images, photos.

HA-free except ``ha.py`` (mirrors the ``render/`` package pattern) so the
registry, parsing, curation, and fetch engine run in the headless test suite.
"""

from __future__ import annotations

from .aic import AicProvider
from .apod import ApodProvider
from .base import ArtProvider
from .bing import BingProvider
from .cleveland import ClevelandProvider
from .dimu import DimuProvider
from .met import MetProvider
from .nasa import NasaImagesProvider
from .pexels import PexelsProvider
from .picsum import PicsumProvider
from .smithsonian import SmithsonianProvider
from .smk import SmkProvider
from .unsplash import UnsplashProvider
from .wellcome import WellcomeProvider
from .wikimedia import WikimediaProvider

PROVIDERS: dict[str, ArtProvider] = {
    provider.key: provider
    for provider in (
        MetProvider(),
        AicProvider(),
        ClevelandProvider(),
        SmkProvider(),
        DimuProvider(),
        SmithsonianProvider(),
        WellcomeProvider(),
        WikimediaProvider(),
        BingProvider(),
        ApodProvider(),
        NasaImagesProvider(),
        PicsumProvider(),
        UnsplashProvider(),
        PexelsProvider(),
    )
}

# The keyless museums: the zero-config "surprise me with art" pool.
# (Smithsonian stays out — its DEMO_KEY tier is too rate-limited for shuffle;
# Wellcome is illustration/archive material rather than wall masterpieces.)
MUSEUM_KEYS: tuple[str, ...] = ("met", "aic", "cleveland", "smk", "dimu")


def get_provider(key: str) -> ArtProvider | None:
    return PROVIDERS.get(key)


def available_provider_keys(entry) -> list[str]:
    """Provider keys usable for this config entry.

    Keyless providers are always available; keyed ones (added in a later
    phase) only when their key is configured in the entry options.
    """
    options = getattr(entry, "options", {}) or {}
    keys = []
    for key, provider in PROVIDERS.items():
        if provider.requires_key and not options.get(provider.key_option or ""):
            continue
        keys.append(key)
    return keys


def build_media_id(provider_key: str, item_id: str) -> str:
    """Media-browser content id for one provider item."""
    from ..const import MEDIA_SCHEME

    return f"{MEDIA_SCHEME}://{provider_key}/{item_id}"


def parse_media_id(media_id: str) -> tuple[str, str] | None:
    """Split ``fraimic-online://provider/item_id`` (item ids may contain /)."""
    from ..const import MEDIA_SCHEME

    prefix = f"{MEDIA_SCHEME}://"
    if not media_id.startswith(prefix):
        return None
    rest = media_id[len(prefix) :]
    provider_key, sep, item_id = rest.partition("/")
    if not provider_key or not sep:
        return None
    return provider_key, item_id
