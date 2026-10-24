"""Voice-creation import from the Fraimic account gallery (HA-free)."""

from __future__ import annotations

import asyncio
import sys
import types

import pytest
from conftest import load

if "aiohttp" not in sys.modules:
    stub = types.ModuleType("aiohttp")
    stub.ClientTimeout = lambda **_kwargs: None
    stub.ClientError = Exception
    stub.ClientSession = object
    stub.FormData = object
    sys.modules["aiohttp"] = stub

cloud = load("cloud")
creations = load("creations")
library_model = load("library_model")

PNG = b"\x89PNG fake"


def _item(upload_id: str, **fields) -> dict:
    return {
        "upload_id": upload_id,
        "upload_type": "audio",
        "created_at": "2026-10-21T18:52:44.626",
        "metadata": None,
        "transcript": f"a lighthouse at dusk {upload_id}",
        "style_name": None,
        "original_url": f"https://s3.example/{upload_id}.png?sig=1",
        "orientation": None,
        "crop_params": None,
        **fields,
    }


class FakeCloud:
    def __init__(self, pages: list[list[dict]], account_id: str = "user-1") -> None:
        self.pages = pages
        self.account_id = account_id
        self.bodies: dict[str, bytes | Exception] = {}
        self.fresh: dict[str, dict] = {}
        self.page_errors: dict[int, Exception] = {}

    async def async_account_id(self) -> str:
        return self.account_id

    async def async_gallery_page(self, page: int) -> dict:
        if page in self.page_errors:
            raise self.page_errors[page]
        return {"items": self.pages[page - 1], "has_next": page < len(self.pages)}

    async def async_gallery_item(self, upload_id: str) -> dict:
        return self.fresh[upload_id]

    async def async_download(self, url: str, max_bytes: int):
        body = self.bodies.get(url, PNG)
        if isinstance(body, Exception):
            raise body
        return body, "image/png"


class FakeLibrary:
    def __init__(self, images: dict | None = None) -> None:
        self.images = images or {}
        self.import_lock = asyncio.Lock()

    async def async_add_image(self, data, filename, *, albums=None, creation=None):
        if not data.startswith(b"\x89PNG"):
            raise ValueError("Not a supported image")
        image_id = f"img{len(self.images)}"
        image = library_model.LibraryImage(
            image_id=image_id,
            filename=filename,
            content_type="image/png",
            uploaded_at=0.0,
            albums=albums,
            creation=creation,
        )
        self.images[image_id] = image
        return image


def _run(library, fake):
    return asyncio.run(creations.async_import_creations(library, fake))


def test_imports_voice_items_across_pages_and_skips_them_next_time():
    crop = {"x": 0, "y": 10, "unit": "%", "width": 100, "height": 80}
    fake = FakeCloud(
        [
            [
                _item("v1", style_name="Watercolor", crop_params=crop, metadata={"k": 1}),
                {**_item("i1"), "upload_type": "image"},
            ],
            [_item("v2", transcript=None, style_name=None)],
        ]
    )
    library = FakeLibrary()

    assert _run(library, fake).as_dict() == {"imported": 2, "skipped": 0, "failed": 0}

    first, second = library.images.values()
    assert first.albums == ["Creations"]
    assert first.filename == "a lighthouse at dusk v1.png"
    assert first.creation.to_dict() == {
        "account_id": "user-1",
        "upload_id": "v1",
        "created_at": 1792608764.626,
        "transcript": "a lighthouse at dusk v1",
        "style": "Watercolor",
        "orientation": None,
        "crop": crop,
        "metadata": {"k": 1},
    }
    # Nothing invented when the vendor left fields out.
    assert second.creation.transcript is None and second.creation.style is None
    assert second.filename == "Voice creation 2026-10-21.png"

    # A restart reloads the manifest; the repeat run adds nothing.
    reloaded = library_model.manifest_from_dict(
        library_model.manifest_to_dict(library.images)
    )
    again = FakeLibrary(reloaded)
    assert _run(again, fake).as_dict() == {"imported": 0, "skipped": 2, "failed": 0}
    assert len(again.images) == 2


def test_same_upload_id_from_another_account_is_distinct():
    library = FakeLibrary()
    _run(library, FakeCloud([[_item("v1")]], account_id="user-1"))

    result = _run(library, FakeCloud([[_item("v1")]], account_id="user-2"))

    assert result.imported == 1
    assert {image.creation.key for image in library.images.values()} == {
        ("user-1", "v1"),
        ("user-2", "v1"),
    }


def test_expired_url_is_resigned_and_bad_items_dont_stop_the_rest():
    fake = FakeCloud([[_item("old"), _item("broken"), _item("notimage"), _item("ok")]])
    fake.bodies["https://s3.example/old.png?sig=1"] = cloud.FraimicCloudError(
        "Download failed: HTTP 403", status=403
    )
    fake.fresh["old"] = {"original_url": "https://s3.example/old.png?sig=2"}
    fake.bodies["https://s3.example/broken.png?sig=1"] = cloud.FraimicCloudError(
        "Download failed: HTTP 500", status=500
    )
    fake.bodies["https://s3.example/notimage.png?sig=1"] = b"<html>"
    library = FakeLibrary()

    result = _run(library, fake)

    assert result.as_dict() == {"imported": 2, "skipped": 0, "failed": 2}
    assert [image.creation.upload_id for image in library.images.values()] == ["old", "ok"]


def test_gallery_failure_after_page_one_keeps_finished_imports():
    fake = FakeCloud([[_item("v1")], [_item("v2")]])
    fake.page_errors[2] = cloud.FraimicCloudError("HTTP 502", status=502)
    library = FakeLibrary()

    with pytest.raises(creations.CreationImportError, match="1 imported so far"):
        _run(library, fake)

    assert len(library.images) == 1


def test_gallery_failure_on_page_one_raises_the_cloud_error():
    fake = FakeCloud([[_item("v1")]])
    fake.page_errors[1] = cloud.FraimicCloudAuthError("invalid_credentials")

    with pytest.raises(cloud.FraimicCloudAuthError):
        _run(FakeLibrary(), fake)


def test_auth_failure_while_resigning_an_item_stops_the_import():
    fake = FakeCloud([[_item("old"), _item("next")]])
    fake.bodies["https://s3.example/old.png?sig=1"] = cloud.FraimicCloudError(
        "Download failed: HTTP 403", status=403
    )

    async def rejected(_upload_id):
        raise cloud.FraimicCloudAuthError("invalid_credentials")

    fake.async_gallery_item = rejected
    library = FakeLibrary()

    with pytest.raises(cloud.FraimicCloudAuthError):
        _run(library, fake)

    assert library.images == {}


def test_hitting_the_page_cap_is_reported_not_treated_as_done(monkeypatch):
    monkeypatch.setattr(creations, "MAX_GALLERY_PAGES", 2)
    fake = FakeCloud([[_item("v1")], [_item("v2")], [_item("v3")]])
    library = FakeLibrary()

    with pytest.raises(creations.CreationImportError, match="after 2 pages"):
        _run(library, fake)

    assert len(library.images) == 2


def test_long_transcripts_are_cut_at_a_word():
    creation = library_model.Creation(
        account_id="a", upload_id="u", transcript="word " * 30
    )

    name = creations.creation_filename(creation, "image/jpeg", "https://x/y")

    assert name.endswith(".jpg")
    assert len(name) <= 64 and not name.startswith(" ")
    assert creations.creation_filename(
        library_model.Creation(account_id="a", upload_id="u"), None, "https://x/a.webp?s"
    ) == "Voice creation.webp"


def test_manifests_without_creations_still_load():
    images = library_model.manifest_from_dict(
        {"images": {"abc": {"filename": "cat.png", "uploaded_at": 1}}}
    )

    assert images["abc"].creation is None
    assert library_model.LibraryImage.from_dict(
        {"image_id": "x", "creation": {"upload_id": "u"}}
    ).creation is None
