"""Pure-logic tests for cloud delivery: auth quirks, album cadence, PNG shape."""

from __future__ import annotations

import io
import sys
import types

import numpy as np
import pytest
from conftest import load


@pytest.fixture(scope="module")
def cloud():
    """Load ``cloud`` with aiohttp stubbed so no network stack is needed."""
    if "aiohttp" not in sys.modules:
        stub = types.ModuleType("aiohttp")

        class _Timeout:
            def __init__(self, **_kwargs) -> None:
                pass

        stub.ClientTimeout = _Timeout
        stub.ClientError = Exception
        stub.ClientSession = object
        stub.FormData = object
        sys.modules["aiohttp"] = stub
    return load("cloud")


const = load("const")
ic = load("image_convert")


def test_password_variants_prefer_raw_then_form_encoded(cloud):
    assert cloud.password_variants("plain123") == ("plain123",)
    assert cloud.password_variants("a b&c") == ("a b&c", "a+b%26c")


def test_album_interval_adds_lead_and_rounds_up(cloud):
    lead = const.CLOUD_SLOT_LEAD_MINUTES
    assert cloud.album_interval_minutes(600) == 10 + lead
    assert cloud.album_interval_minutes(601) == 11 + lead
    assert cloud.album_interval_minutes(1) == 1 + lead


def test_album_schedule_uses_largest_whole_unit(cloud):
    assert cloud.album_schedule(57 * 60)["interval_unit"] == "hours"
    assert cloud.album_schedule(57 * 60)["interval_value"] == 1
    assert cloud.album_schedule((1440 - const.CLOUD_SLOT_LEAD_MINUTES) * 60) == {
        "type": "interval",
        "interval_value": 1,
        "interval_unit": "days",
    }
    assert cloud.album_schedule(300)["interval_unit"] == "minutes"


def test_settings_payload_sends_every_key(cloud):
    payload = cloud.device_settings_payload({"style": "NONE"}, keep_awake=False)
    assert payload == {
        "voiceRecordingEnabled": True,
        "keepAwakeEnabled": False,
        "chargingLedEnabled": True,
        "style": "NONE",
    }


@pytest.mark.parametrize("resolution", [(1600, 1200), (1440, 2560)])
def test_unpack_bin_inverts_pack(resolution):
    width, height = resolution
    indices = np.random.default_rng(7).integers(0, 6, size=width * height, dtype=np.uint8)
    packed = ic._pack_nibbles(indices, width, height)
    assert np.array_equal(ic.unpack_bin(packed, width, height).reshape(-1), indices)


def test_cloud_png_is_pure_primaries_in_viewed_orientation():
    from PIL import Image

    width, height = 1440, 2560
    indices = np.tile(np.arange(6, dtype=np.uint8), width * height // 6)
    png = ic.indices_to_cloud_png(indices, width, height, 90)
    image = Image.open(io.BytesIO(png)).convert("RGB")
    assert image.size == (2560, 1440)
    colours = {colour for _count, colour in image.getcolors(16)}
    assert colours == set(ic._OFFICIAL_PALETTE_RGB)


def test_cloud_png_rotation_is_clockwise_like_the_preview():
    from PIL import Image

    width, height = 1600, 1200
    indices = np.ones(width * height, dtype=np.uint8)  # white
    indices[:width] = 0  # black top row of the native buffer
    # A frame mounted with base rotation 90 shows the native buffer turned
    # back by 270 clockwise, so its top row ends up on the left edge.
    png = ic.indices_to_cloud_png(indices, width, height, (-90) % 360)
    image = Image.open(io.BytesIO(png)).convert("RGB")
    assert image.size == (1200, 1600)
    assert image.getpixel((0, 800)) == (0, 0, 0)
    assert image.getpixel((1199, 800)) == (255, 255, 255)
