"""Tests for the online image providers (pure parsing/curation/engine).

Fixtures under tests/fixtures/providers/ are trimmed real API responses
captured 2026-07-05. No network is touched: the engine runs against a
hand-rolled fake session.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from conftest import load

base = load("providers.base")
curation = load("providers.curation")
cache_mod = load("providers.cache")
engine = load("providers.engine")
met = load("providers.met")
aic = load("providers.aic")
cleveland = load("providers.cleveland")
wikimedia = load("providers.wikimedia")
bing = load("providers.bing")
apod = load("providers.apod")
providers_pkg = load("providers")

FIXTURES = Path(__file__).parent / "fixtures" / "providers"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


# --- parsing -----------------------------------------------------------


def test_parse_met_object() -> None:
    candidate = met.parse_met_object(_fixture("met_object.json"))
    assert candidate is not None
    assert candidate.provider == "met"
    assert candidate.title == "Wheat Field with Cypresses"
    assert candidate.image_url.startswith("https://images.metmuseum.org/")
    assert candidate.thumb_url and "web-large" in candidate.thumb_url
    assert "Gogh" in (candidate.artist or "")
    assert "The Met" in candidate.attribution


def test_parse_met_object_without_image_is_rejected() -> None:
    assert met.parse_met_object(_fixture("met_object_no_image.json")) is None


def test_parse_aic_items_scale_metadata_dims() -> None:
    data = _fixture("aic_search.json")["data"]
    candidates = [aic.parse_aic_item(item) for item in data]
    first = candidates[0]
    assert first is not None
    assert first.image_url.endswith("/full/1686,/0/default.jpg")
    assert first.width == 1686  # master-scan dims scaled to IIIF delivery
    assert first.height and 0 < first.height < first.width * 2
    assert first.artist and "(" not in first.artist  # nationality stripped
    assert "Art Institute of Chicago" in first.attribution


def test_parse_cleveland_item() -> None:
    item = _fixture("cleveland_list.json")["data"][0]
    candidate = cleveland.parse_cleveland_item(item)
    assert candidate is not None
    assert candidate.image_url == item["images"]["print"]["url"]
    assert candidate.width and candidate.height
    assert "Cleveland Museum of Art" in candidate.attribution


def test_parse_wikimedia_potd_prefers_sized_thumb() -> None:
    candidate = wikimedia.parse_potd(_fixture("wikimedia_potd.json"), "2026-07-04", 1600)
    assert candidate is not None
    assert "3840px-" in candidate.image_url  # snapped up from 1.5x target width
    assert candidate.license == "CC BY-SA 4.0"
    assert candidate.attribution  # attribution mandatory for CC BY-SA


def test_wikimedia_sized_thumb_rewrite() -> None:
    url = "https://upload.wikimedia.org/x/thumb/a/ab/Foo.jpg/960px-Foo.jpg"
    assert wikimedia.sized_thumb(url, 1800).endswith("/1920px-Foo.jpg")
    assert wikimedia.sized_thumb(url, 2400).endswith("/3840px-Foo.jpg")


def test_parse_bing_archive_rewrites_uhd() -> None:
    candidates = bing.parse_bing_archive(_fixture("bing_archive.json"))
    assert len(candidates) == 2
    assert candidates[0].image_url.endswith("_UHD.jpg")
    assert candidates[0].width == 3840


def test_parse_apod_filters_videos() -> None:
    image_item = _fixture("apod.json")
    video_item = {**image_item, "media_type": "video"}
    assert len(apod.parse_apod_items([image_item, video_item])) == 1
    candidate = apod.parse_apod_items(image_item)[0]
    assert candidate.image_url == (image_item.get("hdurl") or image_item["url"])
    assert "APOD" in candidate.attribution


def test_wikimedia_attribution_does_not_duplicate_license_without_artist() -> None:
    payload = _fixture("wikimedia_potd.json")
    payload["image"]["artist"]["text"] = ""
    candidate = wikimedia.parse_potd(payload, "2026-07-04", 1600)

    assert candidate is not None
    assert candidate.attribution.endswith("(CC BY-SA 4.0)")
    assert "CC BY-SA 4.0 — CC BY-SA 4.0" not in candidate.attribution


# --- curation ----------------------------------------------------------


@pytest.mark.parametrize(
    "w,h,tw,th,ok",
    [
        (3000, 2400, 1600, 1200, True),  # landscape art on landscape frame
        (1200, 1500, 1200, 1600, True),  # portrait art on portrait frame
        (900, 3000, 1600, 1200, False),  # tall scroll on landscape frame
        (6000, 1500, 1600, 1200, False),  # extreme panorama
        (800, 600, 1600, 1200, False),  # too small
        (2400, 1000, 1200, 1600, False),  # wide landscape art on portrait frame
        (0, 100, 1600, 1200, False),
    ],
)
def test_acceptable(w, h, tw, th, ok) -> None:
    assert curation.acceptable(w, h, tw, th) is ok


def test_contain_fit_relaxes_aspect_but_not_resolution() -> None:
    assert curation.acceptable_for_fit(3840, 2160, 1200, 1600, "contain") is True
    assert curation.acceptable_for_fit(3840, 2160, 1200, 1600, "cover") is False
    assert curation.acceptable_for_fit(800, 450, 1200, 1600, "contain") is False


def test_aspect_score_prefers_matching_aspect() -> None:
    perfect = curation.aspect_score(3200, 2400, 1600, 1200)
    skewed = curation.aspect_score(3200, 1200, 1600, 1200)
    tiny = curation.aspect_score(400, 300, 1600, 1200)
    assert perfect > skewed
    assert perfect > tiny


# --- engine ------------------------------------------------------------


class FakeResponse:
    def __init__(self, *, status=200, body=b"", payload=None):
        self.status = status
        self._body = body
        self._consumed = False
        self._payload = payload
        self.content = self

    async def read(self, _n=-1):
        # Mimic a stream: full body once, then EOF (read_capped loops).
        if self._consumed:
            return b""
        self._consumed = True
        return self._body

    async def json(self, content_type=None):
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class FakeSession:
    """Maps URL prefixes to queued responses."""

    def __init__(self):
        self.routes: list[tuple[str, FakeResponse]] = []
        self.requests: list[str] = []
        self.calls: list[dict[str, object]] = []

    def add(self, prefix: str, response: FakeResponse) -> None:
        self.routes.append((prefix, response))

    async def get(self, url, headers=None, timeout=None, **kwargs):
        self.requests.append(url)
        self.calls.append(
            {"url": url, "headers": headers, "timeout": timeout, **kwargs}
        )
        for index, (prefix, response) in enumerate(self.routes):
            if url.startswith(prefix):
                # Consume queued responses so retries get the next one.
                if sum(1 for p, _ in self.routes if p == prefix) > 1:
                    self.routes.pop(index)
                return response
        raise AssertionError(f"unexpected request: {url}")

    async def post(self, url, headers=None, timeout=None, **kwargs):
        return await self.get(url, headers=headers, timeout=timeout)


class _Provider(base.ArtProvider):
    key = "fake"
    name = "Fake"

    def __init__(self, candidates):
        self._candidates = candidates

    async def async_candidates(self, session, cache, request, count):
        return self._candidates[:count]


def _candidate(item_id: str, url: str, width=None, height=None):
    return base.ArtCandidate(
        provider="fake", item_id=item_id, image_url=url, title=item_id,
        width=width, height=height,
    )


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


async def _dims_from_png(data: bytes) -> tuple[int, int]:
    import io

    from PIL import Image

    with Image.open(io.BytesIO(data)) as img:
        return img.size


def _png(width: int, height: int) -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (width, height), (200, 100, 50)).save(buf, format="PNG")
    return buf.getvalue()


REQUEST = base.FetchRequest(target_width=1600, target_height=1200)


class SpyCache(cache_mod.ProviderCache):
    def __init__(self) -> None:
        super().__init__()
        self.throttles: list[tuple[str, float]] = []

    async def async_throttle(self, key: str, min_interval: float) -> None:
        self.throttles.append((key, min_interval))


def test_engine_returns_first_acceptable_candidate() -> None:
    session = FakeSession()
    session.add("https://x/big.png", FakeResponse(body=_png(2000, 1500)))
    provider = _Provider([_candidate("a", "https://x/big.png")])
    image = _run(
        engine.async_pick_and_download(
            provider, session, cache_mod.ProviderCache(), REQUEST, dims_of=_dims_from_png
        )
    )
    assert image.candidate.item_id == "a"


def test_engine_skips_bad_metadata_dims_without_downloading() -> None:
    session = FakeSession()
    session.add("https://x/good.png", FakeResponse(body=_png(2000, 1500)))
    provider = _Provider(
        [
            _candidate("panorama", "https://x/pano.png", width=6000, height=1000),
            _candidate("good", "https://x/good.png"),
        ]
    )
    image = _run(
        engine.async_pick_and_download(
            provider, session, cache_mod.ProviderCache(), REQUEST, dims_of=_dims_from_png
        )
    )
    assert image.candidate.item_id == "good"
    assert all("pano" not in url for url in session.requests)


def test_engine_accepts_wide_metadata_dims_for_contain_fit() -> None:
    session = FakeSession()
    session.add("https://x/wide.png", FakeResponse(body=_png(3840, 2160)))
    provider = _Provider(
        [_candidate("wide", "https://x/wide.png", width=3840, height=2160)]
    )
    request = base.FetchRequest(
        target_width=1200, target_height=1600, fit="contain"
    )

    image = _run(
        engine.async_pick_and_download(
            provider, session, cache_mod.ProviderCache(), request, dims_of=_dims_from_png
        )
    )

    assert image.candidate.item_id == "wide"


def test_engine_falls_back_to_best_scored_download() -> None:
    # Both candidates decode too small; the better-scoring one must win.
    session = FakeSession()
    session.add("https://x/small_ok_aspect.png", FakeResponse(body=_png(800, 600)))
    session.add("https://x/small_bad_aspect.png", FakeResponse(body=_png(800, 200)))
    provider = _Provider(
        [
            _candidate("ok", "https://x/small_ok_aspect.png"),
            _candidate("bad", "https://x/small_bad_aspect.png"),
        ]
    )
    image = _run(
        engine.async_pick_and_download(
            provider, session, cache_mod.ProviderCache(), REQUEST, dims_of=_dims_from_png
        )
    )
    assert image.candidate.item_id == "ok"


def test_engine_skips_candidate_when_dimension_probe_raises() -> None:
    session = FakeSession()
    session.add("https://x/bad.png", FakeResponse(body=b"bad"))
    session.add("https://x/good.png", FakeResponse(body=_png(2000, 1500)))
    provider = _Provider(
        [
            _candidate("bad", "https://x/bad.png"),
            _candidate("good", "https://x/good.png"),
        ]
    )

    async def dims_of(data: bytes) -> tuple[int, int]:
        if data == b"bad":
            raise RuntimeError("decode failed")
        return await _dims_from_png(data)

    image = _run(
        engine.async_pick_and_download(
            provider, session, cache_mod.ProviderCache(), REQUEST, dims_of=dims_of
        )
    )

    assert image.candidate.item_id == "good"


def test_engine_skips_candidate_over_source_pixel_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    session.add("https://x/huge.png", FakeResponse(body=b"huge"))
    session.add("https://x/good.png", FakeResponse(body=_png(2000, 1500)))
    provider = _Provider(
        [
            _candidate("huge", "https://x/huge.png"),
            _candidate("good", "https://x/good.png"),
        ]
    )
    monkeypatch.setattr(engine, "MAX_SOURCE_PIXELS", 3_500_000)

    async def dims_of(data: bytes) -> tuple[int, int]:
        if data == b"huge":
            return (2_000, 2_000)
        return await _dims_from_png(data)

    image = _run(
        engine.async_pick_and_download(
            provider, session, cache_mod.ProviderCache(), REQUEST, dims_of=dims_of
        )
    )

    assert image.candidate.item_id == "good"


def test_engine_raises_when_nothing_downloads() -> None:
    session = FakeSession()
    session.add("https://x/", FakeResponse(status=404))
    provider = _Provider([_candidate("a", "https://x/a.png")])
    with pytest.raises(base.ArtFetchError):
        _run(
            engine.async_pick_and_download(
                provider, session, cache_mod.ProviderCache(), REQUEST,
                dims_of=_dims_from_png,
            )
        )


def test_engine_raises_on_empty_candidates() -> None:
    with pytest.raises(base.ArtFetchError):
        _run(
            engine.async_pick_and_download(
                _Provider([]), FakeSession(), cache_mod.ProviderCache(), REQUEST,
                dims_of=_dims_from_png,
            )
        )


def test_engine_wraps_body_read_failures() -> None:
    class BrokenResponse(FakeResponse):
        async def read(self, _n=-1):
            raise RuntimeError("stream broke")

    session = FakeSession()
    session.add("https://x/broken.png", BrokenResponse())

    with pytest.raises(base.ArtFetchError, match="stream broke"):
        _run(engine.async_download(session, "https://x/broken.png", {}))


def test_met_provider_retries_past_imageless_objects() -> None:
    session = FakeSession()
    search = _fixture("met_search.json")
    session.add(
        "https://collectionapi.metmuseum.org/public/collection/v1/search",
        FakeResponse(payload={"total": 2, "objectIDs": [1, 436535]}),
    )
    session.add(
        "https://collectionapi.metmuseum.org/public/collection/v1/objects/1",
        FakeResponse(payload=_fixture("met_object_no_image.json")),
    )
    session.add(
        "https://collectionapi.metmuseum.org/public/collection/v1/objects/436535",
        FakeResponse(payload=_fixture("met_object.json")),
    )
    provider = met.MetProvider()
    provider.min_interval = 0  # no throttling in tests
    candidates = _run(
        provider.async_candidates(session, cache_mod.ProviderCache(), REQUEST, 2)
    )
    assert [c.title for c in candidates] == ["Wheat Field with Cypresses"]
    assert search["total"] > 0  # fixture sanity


def test_apod_uses_encoded_params_and_conservative_demo_key_throttle() -> None:
    session = FakeSession()
    session.add(apod.APOD_URL, FakeResponse(payload=[_fixture("apod.json")]))
    cache = SpyCache()
    provider = apod.ApodProvider()
    provider.min_interval = 0

    candidates = _run(provider.async_candidates(session, cache, REQUEST, 1))

    assert len(candidates) == 1
    assert session.calls[0]["url"] == apod.APOD_URL
    assert session.calls[0]["params"] == {"api_key": apod.DEMO_KEY, "count": 4}
    assert cache.throttles == [(provider.key, 0)]

    cached = _run(provider.async_candidates(session, cache, REQUEST, 1))

    assert cached == candidates
    assert len(session.calls) == 1


def test_apod_personal_key_keeps_normal_provider_throttle() -> None:
    session = FakeSession()
    session.add(apod.APOD_URL, FakeResponse(payload=[_fixture("apod.json")]))
    cache = SpyCache()
    provider = apod.ApodProvider()
    provider.min_interval = 0
    request = base.FetchRequest(
        target_width=REQUEST.target_width,
        target_height=REQUEST.target_height,
        api_key="abc&123",
    )

    candidates = _run(provider.async_candidates(session, cache, request, 1))

    assert len(candidates) == 1
    assert session.calls[0]["params"] == {"api_key": "abc&123", "count": 4}
    assert cache.throttles == [(provider.key, 0)]


# --- cache -------------------------------------------------------------


def test_cache_ttl_with_fake_clock() -> None:
    clock = {"t": 0.0}
    cache = cache_mod.ProviderCache(clock=lambda: clock["t"])
    cache.set("k", [1, 2, 3])
    assert cache.get("k", ttl=100) == [1, 2, 3]
    clock["t"] = 101
    assert cache.get("k", ttl=100) is None


# --- media ids + caption ------------------------------------------------


def test_media_id_roundtrip() -> None:
    media_id = providers_pkg.build_media_id("met", "436535")
    assert media_id == "fraimic-online://met/436535"
    assert providers_pkg.parse_media_id(media_id) == ("met", "436535")
    assert providers_pkg.parse_media_id("media-source://other") is None
    assert providers_pkg.parse_media_id("fraimic-online://noslash") is None


def test_caption_strip_is_palette_pure_and_composite_sizes() -> None:
    import io

    import numpy as np
    from PIL import Image

    caption = load("providers.caption")
    const = load("const")

    strip = caption.caption_strip_png("Wheat Field — Van Gogh, The Met", 800, 48)
    arr = np.asarray(Image.open(io.BytesIO(strip)).convert("RGB")).reshape(-1, 3)
    palette = np.array(const.SPECTRA6_RGB, dtype=np.uint8)
    exact = np.zeros(arr.shape[0], dtype=bool)
    for color in palette:
        exact |= (arr == color).all(axis=1)
    assert exact.mean() == 1.0

    composed = caption.composite_with_caption(_png(1000, 700), "Some credit", 800, 480)
    with Image.open(io.BytesIO(composed)) as img:
        assert img.size == (800, 480)


def test_caption_composite_preserves_contain_fit() -> None:
    import io

    from PIL import Image

    caption = load("providers.caption")
    composed = caption.composite_with_caption(
        _png(1000, 100), "Some credit", 800, 480, "contain"
    )

    with Image.open(io.BytesIO(composed)).convert("RGB") as img:
        assert img.getpixel((10, 10)) == (255, 255, 255)
        assert img.size == (800, 480)


def test_caption_composite_rejects_oversized_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    caption = load("providers.caption")
    monkeypatch.setattr(caption, "MAX_SOURCE_PIXELS", 1)

    with pytest.raises(ValueError, match="too large"):
        caption.composite_with_caption(_png(2, 2), "Some credit", 800, 480)


def test_shuffle_and_availability() -> None:
    from types import SimpleNamespace

    entry = SimpleNamespace(options={})
    keys = providers_pkg.available_provider_keys(entry)
    assert set(providers_pkg.MUSEUM_KEYS) <= set(keys)
    # Keyed providers hidden without keys, shown with them.
    assert "unsplash" not in keys
    assert "pexels" not in keys
    keyed = SimpleNamespace(
        options={"unsplash_access_key": "abc", "pexels_api_key": "def"}
    )
    keyed_keys = providers_pkg.available_provider_keys(keyed)
    assert "unsplash" in keyed_keys
    assert "pexels" in keyed_keys


def test_parse_unsplash_photo() -> None:
    unsplash = load("providers.unsplash")

    item = _fixture("unsplash_random.json")[0]
    candidate = unsplash.parse_unsplash_photo(item, 3200)
    assert candidate is not None
    assert candidate.image_url.startswith("https://images.unsplash.com/")
    assert "w=3200" in candidate.image_url and "fm=jpg" in candidate.image_url
    assert candidate.attribution == "Photo by Jeff Sheldon on Unsplash"
    assert candidate.extra["download_location"].endswith("download?ixid=abc123")
    assert candidate.title == "A man drinking a coffee."


def test_parse_pexels_photo() -> None:
    pexels = load("providers.pexels")

    photos = _fixture("pexels_search.json")["photos"]
    candidate = pexels.parse_pexels_photo(photos[0])
    assert candidate is not None
    assert candidate.image_url.startswith("https://images.pexels.com/")
    assert candidate.attribution == "Photo by Joey Farina on Pexels"
    assert candidate.width == 3024
    # Item without src urls is rejected.
    assert pexels.parse_pexels_photo(photos[1]) is None
