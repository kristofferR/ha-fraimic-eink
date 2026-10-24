"""fraimic.import_creations against a real library, with the account mocked."""

from __future__ import annotations

import io
import shutil
from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from PIL import Image
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fraimic.api import FraimicClient
from custom_components.fraimic.cloud import FraimicCloudClient
from custom_components.fraimic.const import (
    CONF_CLOUD_EMAIL,
    CONF_CLOUD_PASSWORD,
    DOMAIN,
    LIBRARY_ALBUM_DEFAULT,
    LIBRARY_DIR,
)
from custom_components.fraimic.library import get_library

from .conftest import setup_entry


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (12, 16), "teal").save(buffer, "PNG")
    return buffer.getvalue()


ITEM = {
    "upload_id": "v1",
    "upload_type": "audio",
    "created_at": "2026-10-21T18:52:44",
    "transcript": "a lighthouse at dusk",
    "style_name": "Watercolor",
    "original_url": "https://s3.example/v1.png?sig=1",
    "metadata": None,
    "orientation": None,
    "crop_params": None,
}


@pytest.fixture(autouse=True)
def empty_library(hass: HomeAssistant) -> Generator[None]:
    """The harness config dir is shared across runs; start and end with no library."""
    path = hass.config.path(LIBRARY_DIR)
    shutil.rmtree(path, ignore_errors=True)
    yield
    shutil.rmtree(path, ignore_errors=True)


@pytest.mark.usefixtures("frame_client")
async def test_import_adds_creations_once_without_showing_them(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=config_entry.version,
        unique_id=config_entry.unique_id,
        data=config_entry.data,
        options={
            **config_entry.options,
            CONF_CLOUD_EMAIL: "owner@example.com",
            CONF_CLOUD_PASSWORD: "secret",
        },
    )
    await setup_entry(hass, entry)
    upload = AsyncMock()
    with patch.multiple(
        FraimicCloudClient,
        async_account_id=AsyncMock(return_value="user-1"),
        async_gallery_page=AsyncMock(return_value={"items": [ITEM], "has_next": False}),
        async_download=AsyncMock(return_value=(_png(), "image/png")),
    ), patch.object(FraimicClient, "upload_image", upload):
        first = await hass.services.async_call(
            DOMAIN, "import_creations", {}, blocking=True, return_response=True
        )
        second = await hass.services.async_call(
            DOMAIN, "import_creations", {}, blocking=True, return_response=True
        )

    assert first == {"imported": 1, "skipped": 0, "failed": 0}
    assert second == {"imported": 0, "skipped": 1, "failed": 0}
    library = get_library(hass)
    assert library is not None
    (image,) = library.images.values()
    assert image.normalized_albums() == [LIBRARY_ALBUM_DEFAULT]
    assert (image.width, image.height) == (12, 16)
    assert image.creation is not None and image.creation.style == "Watercolor"
    data, _ = await library.async_get_original(image.image_id)
    assert data == _png()
    upload.assert_not_called()


async def test_import_needs_a_signed_in_account(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    with pytest.raises(ServiceValidationError, match="Sign in"):
        await hass.services.async_call(
            DOMAIN, "import_creations", {}, blocking=True, return_response=True
        )
