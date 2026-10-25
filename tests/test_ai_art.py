"""AI art core: prompt templates, frame-shaped sizes, pricing and clients (HA-free)."""

from __future__ import annotations

import asyncio
import base64
import sys
import types

import pytest
import voluptuous as vol
from conftest import load

# A stub only for this import: other suites install their own fuller aiohttp
# stub when none is registered, so this one must not stay in sys.modules.
_installed = "aiohttp" not in sys.modules
if _installed:
    stub = types.ModuleType("aiohttp")
    stub.ClientTimeout = lambda **_kwargs: None
    stub.ClientError = OSError
    sys.modules["aiohttp"] = stub
ai_art = load("ai_art")
if _installed:
    del sys.modules["aiohttp"]

PNG = b"\x89PNG\r\n\x1a\nrest"
JPEG = b"\xff\xd8\xff\xe0rest"


class FakeResponse:
    def __init__(self, status: int, body) -> None:
        self.status = status
        self._body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def json(self, content_type=None):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


class FakeSession:
    """Answers by URL suffix and records every request."""

    def __init__(self, routes: dict[str, tuple[int, object]]) -> None:
        self.routes = routes
        self.calls: list[tuple[str, str, dict]] = []

    def request(self, method, url, timeout=None, **kwargs):
        self.calls.append((method, url, kwargs))
        for suffix, (status, body) in self.routes.items():
            if url.endswith(suffix):
                return FakeResponse(status, body)
        return FakeResponse(404, {"error": {"message": "not found"}})


def run(coro):
    return asyncio.run(coro)


def test_template_wraps_request_and_appends_without_placeholder() -> None:
    assert (
        ai_art.apply_template("Poster of {prompt}. No text.", "  a fox\nreading. ")
        == "Poster of a fox reading. No text."
    )
    assert ai_art.apply_template("Moody ink drawing.", "a fox") == "Moody ink drawing. a fox"
    assert ai_art.apply_template("{prompt}", "a fox") == "a fox"


def test_settings_merge_styles_keep_builtins_and_fall_back_to_default() -> None:
    settings = ai_art.AiSettings().updated(
        {
            "styles": [
                {"id": "mine", "name": "Mine", "template": "Linocut of {prompt}"},
                {"id": "woodcut", "name": "Woodcut", "template": "Changed {prompt}"},
            ],
            "style": "mine",
        }
    )
    ids = [style.id for style in settings.styles]
    assert ids[:2] == ["mine", "woodcut"]
    assert set(ai_art.BUILTIN_BY_ID) <= set(ids)
    assert settings.style_for(None).id == "mine"
    assert settings.style_for("WOODCUT").template == "Changed {prompt}"
    # Removing the selected custom style falls back to the default one.
    assert settings.updated({"styles": []}).style == ai_art.DEFAULT_STYLE

    with pytest.raises(vol.Invalid):
        settings.updated({"styles": [{"id": "Bad Id", "name": "x", "template": "y"}]})
    with pytest.raises(vol.Invalid):
        settings.updated(
            {"styles": [{"id": "a", "name": "A", "template": "x"}] * 2}
        )


def test_settings_configured_and_round_trip() -> None:
    settings = ai_art.AiSettings().updated(
        {"provider": "local", "local_url": "http://10.0.0.5:7860/v1/"}
    )
    assert settings.local_url == "http://10.0.0.5:7860"
    assert not settings.configured  # the API is only known after connecting
    settings = settings.updated(
        {"local_api": "sdwebui", "voice": {"e1": {"mode": "art", "stt": "stt.whisper"}}}
    )
    assert settings.configured
    loaded = ai_art.AiSettings.from_dict(settings.to_dict())
    assert loaded == settings
    custom = settings.updated(
        {"styles": [{"id": "mine", "name": "Mine", "template": "{prompt}"}], "style": "mine"}
    )
    assert ai_art.AiSettings.from_dict(custom.to_dict()).style == "mine"
    assert loaded.voice["e1"].mode == "art"
    # Stored junk is dropped field by field instead of losing everything.
    assert ai_art.AiSettings.from_dict({"provider": "nope", "style": "woodcut"}).style == "woodcut"
    with pytest.raises(vol.Invalid):
        ai_art.AiSettings().updated({"local_url": "ftp://x"})


def test_frame_shapes_pick_aspect_resolution_and_local_size() -> None:
    allowed = ["1:1", "3:4", "4:3", "9:16", "16:9", "auto"]
    assert ai_art.closest_aspect(1440, 2560, allowed) == "9:16"
    assert ai_art.closest_aspect(1200, 1600, allowed) == "3:4"
    assert ai_art.closest_aspect(1600, 1200, ["auto"]) is None

    resolutions = ["768", "1K", "1.5K", "2K", "4K"]
    assert ai_art.pick_resolution(1600, resolutions) == "1.5K"
    assert ai_art.pick_resolution(2560, resolutions) == "2K"
    assert ai_art.pick_resolution(5000, ["1K"]) == "1K"
    assert ai_art.pick_resolution(1600, []) is None

    assert ai_art.local_size(1440, 2560) == (896, 1536)
    assert ai_art.local_size(1600, 1200) == (1536, 1152)


def test_price_matches_resolution_variant_and_skips_token_pricing() -> None:
    per_image = [
        {"billable": "output_image", "unit": "image", "cost_usd": 0.009, "variant": "1k"},
        {"billable": "output_image", "unit": "image", "cost_usd": 0.014, "variant": "2k"},
    ]
    assert ai_art.price_for(per_image, "2K") == 0.014
    quality = [
        {"billable": "output_image", "unit": "image", "cost_usd": 0.04, "variant": "low_1k"},
        {"billable": "output_image", "unit": "image", "cost_usd": 0.06, "variant": "low_2k"},
    ]
    assert ai_art.price_for(quality, "2K") == 0.06
    assert ai_art.price_for([{"billable": "output_image", "unit": "image", "cost_usd": 0.007}], None) == 0.007
    assert ai_art.price_for([{"billable": "output_image", "unit": "token", "cost_usd": 3e-05}], "1K") is None


def test_openrouter_request_uses_only_supported_parameters() -> None:
    model = {"id": "m", "aspect_ratios": ["1:1", "9:16"], "resolutions": ["1K", "2K"]}
    assert ai_art.openrouter_request(model, "p", 1440, 2560) == {
        "model": "m", "prompt": "p", "aspect_ratio": "9:16", "resolution": "2K",
    }
    assert ai_art.openrouter_request({"id": "m"}, "p", 1440, 2560) == {"model": "m", "prompt": "p"}


def test_malformed_model_parameters_and_prices_do_not_break_the_catalog() -> None:
    session = FakeSession({"/images/models": (200, {"data": [
        {"id": "one", "supported_parameters": ["resolution"]},
        {"id": "two", "supported_parameters": {"resolution": "2K"}},
    ]})})
    models = run(ai_art.openrouter_models(session))
    assert [model["resolutions"] for model in models] == [[], []]
    rows = [None, "bad", *[
        {"billable": "output_image", "unit": "image", "cost_usd": value}
        for value in (None, "bad", float("nan"), float("inf"))
    ], {"billable": "output_image", "unit": "image"}]
    assert ai_art.price_for(rows, "2K") is None
    rows.append({"billable": "output_image", "unit": "image", "cost_usd": "0.007"})
    assert ai_art.price_for(rows, "2K") == 0.007


def test_openrouter_generate_decodes_picture_and_cost() -> None:
    session = FakeSession(
        {
            "/images": (
                200,
                {
                    "data": [{"b64_json": base64.b64encode(JPEG).decode(), "media_type": "image/jpeg"}],
                    "usage": {"cost": 0.014},
                },
            )
        }
    )
    model = {"id": "black-forest-labs/flux-3-image-klein", "aspect_ratios": ["9:16"], "resolutions": ["2K"]}
    image = run(ai_art.openrouter_generate(session, "key", model, "a fox", 1440, 2560))
    assert (image.data, image.mime_type, image.cost) == (JPEG, "image/jpeg", 0.014)
    method, url, kwargs = session.calls[0]
    assert (method, url) == ("POST", f"{ai_art.OPENROUTER_BASE}/images")
    assert kwargs["headers"]["Authorization"] == "Bearer key"
    assert kwargs["json"]["aspect_ratio"] == "9:16"


@pytest.mark.parametrize(
    ("status", "message"),
    [(401, "rejected the API key"), (402, "out of credits"), (500, "answered 500: boom")],
)
def test_openrouter_errors_are_readable(status: int, message: str) -> None:
    session = FakeSession({"/images": (status, {"error": {"message": "boom"}})})
    with pytest.raises(ai_art.AiArtError, match=message):
        run(ai_art.openrouter_generate(session, "key", {"id": "m"}, "p", 100, 100))


def test_credits_and_model_catalog() -> None:
    session = FakeSession(
        {
            "/credits": (200, {"data": {"total_credits": 20, "total_usage": 16.65}}),
            "/images/models": (
                200,
                {
                    "data": [
                        {
                            "id": "recraft/recraft-v4.1-flash",
                            "name": "Recraft: Recraft V4.1 Flash",
                            "supported_parameters": {"aspect_ratio": {"type": "enum", "values": ["3:4"]}},
                        },
                        {"name": "missing id"},
                    ]
                },
            ),
        }
    )
    assert run(ai_art.openrouter_credits(session, "key")) == 3.35
    session.routes["/endpoints"] = (
        200,
        {
            "id": "recraft/recraft-v4.1-flash",
            "endpoints": [
                {"pricing": [{"billable": "output_image", "unit": "image", "cost_usd": 0.007}]}
            ],
        },
    )
    pricing = run(ai_art.openrouter_pricing(session, "recraft/recraft-v4.1-flash"))
    assert ai_art.price_for(pricing, None) == 0.007
    assert session.calls[-1][1].endswith("/images/models/recraft/recraft-v4.1-flash/endpoints")
    assert run(ai_art.openrouter_models(session)) == [
        {"id": "recraft/recraft-v4.1-flash", "name": "Recraft V4.1 Flash", "aspect_ratios": ["3:4"], "resolutions": []}
    ]


def test_local_detects_openai_then_sdwebui() -> None:
    openai = FakeSession({"/v1/models": (200, {"data": [{"id": "flux-3-klein"}]})})
    assert run(ai_art.local_detect(openai, "http://gpu:8080")) == ("openai", ["flux-3-klein"])

    sdwebui = FakeSession({"/sdapi/v1/sd-models": (200, [{"title": "flux1-schnell-fp8", "model_name": "x"}])})
    assert run(ai_art.local_detect(sdwebui, "http://gpu:7860")) == ("sdwebui", ["flux1-schnell-fp8"])

    with pytest.raises(ai_art.AiArtError, match="No OpenAI-style"):
        run(ai_art.local_detect(FakeSession({}), "http://gpu:1"))


def test_local_generate_sends_frame_size_and_reads_both_apis() -> None:
    encoded = base64.b64encode(PNG).decode()
    session = FakeSession({"/sdapi/v1/txt2img": (200, {"images": [encoded]})})
    image = run(ai_art.local_generate(session, "http://gpu:7860", "sdwebui", "flux", "p", 1440, 2560, 4))
    assert (image.data, image.mime_type, image.cost) == (PNG, "image/png", 0.0)
    body = session.calls[0][2]["json"]
    assert (body["width"], body["height"], body["steps"]) == (896, 1536, 4)
    assert body["override_settings"] == {"sd_model_checkpoint": "flux"}

    session = FakeSession({"/v1/images/generations": (200, {"data": [{"b64_json": f"data:image/png;base64,{encoded}"}]})})
    image = run(ai_art.local_generate(session, "http://gpu:8080", "openai", "", "p", 1600, 1200, None))
    assert image.data == PNG
    body = session.calls[0][2]["json"]
    assert body == {"prompt": "p", "size": "1536x1152", "n": 1, "response_format": "b64_json"}


def test_rejects_non_pictures() -> None:
    with pytest.raises(ai_art.AiArtError, match="not a picture"):
        ai_art.parse_openai_images({"data": [{"b64_json": base64.b64encode(b"hello").decode()}]})
    with pytest.raises(ai_art.AiArtError, match="no picture"):
        ai_art.parse_sdwebui_images({"images": []})
