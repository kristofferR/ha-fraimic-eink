"""AI art: prompt styles, frame-shaped sizes and image-service clients.

No Home Assistant imports, so the pure parts stay unit-testable. Pictures
come from OpenRouter's image API or a local server speaking the OpenAI images
API or the Stable Diffusion WebUI API; ``ai_manager`` adds HA AI Task
entities and the storage around them.

OpenRouter facts verified live on 2026-10-25: ``POST /api/v1/images`` takes
``aspect_ratio`` and ``resolution`` and answers ``data[].b64_json`` plus
``usage.cost`` in USD; per-picture prices live on each model's endpoints.
"""

from __future__ import annotations

import base64
import binascii
import math
import re
import time
from dataclasses import dataclass, field, replace
from typing import Any
from urllib.parse import quote, urlsplit

import aiohttp
import voluptuous as vol

PROVIDER_OPENROUTER = "openrouter"
PROVIDER_LOCAL = "local"
PROVIDER_AI_TASK = "ai_task"
PROVIDERS = (PROVIDER_OPENROUTER, PROVIDER_LOCAL, PROVIDER_AI_TASK)

LOCAL_OPENAI = "openai"
LOCAL_SDWEBUI = "sdwebui"
LOCAL_APIS = (LOCAL_OPENAI, LOCAL_SDWEBUI)

VOICE_MODES = ("fixed", "art", "assist")

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
OPENROUTER_HEADERS = {
    "HTTP-Referer": "https://github.com/kristofferR/ha-fraimic-eink",
    "X-Title": "Fraimic for Home Assistant",
}
DEFAULT_OPENROUTER_MODEL = "black-forest-labs/flux-3-image-klein"
# Shown first in settings, with prices; every other image model is listed too.
RECOMMENDED_MODELS: dict[str, str] = {
    "black-forest-labs/flux-3-image-klein": "Fast, clean detail",
    "recraft/recraft-v4.1-flash": "Flat illustration, dithers cleanly on e-ink",
    "google/gemini-3.1-flash-lite-image": "Follows long, detailed prompts",
    "openai/gpt-image-2": "Finest detail, slower",
}

# Seconds, wrapped in ``aiohttp.ClientTimeout`` per request so importing this
# module never touches aiohttp (tests stub it). A local GPU can take minutes.
TIMEOUT = 20
GENERATE_TIMEOUT = 300
# Long edge for local servers; the library scales it to the panel.
LOCAL_LONG_EDGE = 1536
MAX_REQUEST = 2000
MAX_TEMPLATE = 2000
MAX_PROMPT = 4000
MAX_STYLES = 24
PROMPT_TOKEN = "{prompt}"
DEFAULT_STYLE = "eink_poster"


class AiArtError(Exception):
    """An image service failed; the message is shown to the user."""


@dataclass(frozen=True)
class Style:
    """A named prompt template; ``{prompt}`` marks where the request goes."""

    id: str
    name: str
    template: str

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "name": self.name, "template": self.template}


BUILTIN_STYLES: tuple[Style, ...] = (
    Style(
        "eink_poster",
        "E-ink poster",
        "Bold flat-colour poster illustration of {prompt}. Large simple shapes, "
        "strong black outlines, flat areas of white, yellow, red, blue and green, "
        "no gradients, no text.",
    ),
    Style(
        "woodcut",
        "Woodcut",
        "Woodcut print of {prompt}. Bold carved black lines on white paper, a few "
        "flat areas of red and yellow, high contrast, no text.",
    ),
    Style(
        "watercolour",
        "Watercolour",
        "Watercolour painting of {prompt}. Clear shapes, soft edges, a bright "
        "limited palette and white paper showing through, no text.",
    ),
    Style(
        "ink",
        "Ink drawing",
        "Black ink drawing of {prompt}. Confident lines and fine hatching on white "
        "paper, strong contrast, no text.",
    ),
    Style(
        "photo",
        "Photo",
        "Photograph of {prompt}. Natural light, strong composition, vivid colour, "
        "sharp focus.",
    ),
    Style("none", "None", PROMPT_TOKEN),
)
BUILTIN_BY_ID = {style.id: style for style in BUILTIN_STYLES}

REWRITE_INSTRUCTIONS = (
    "Rewrite this request as one detailed English prompt for an image "
    "generator. Keep the subject and anything the person asked for, add a "
    "clear composition and setting, and leave out any art style. Reply with "
    "the prompt only, in one or two sentences.\n\nRequest: {request}"
)


def apply_template(template: str, request: str) -> str:
    """Wrap a request in a style template.

    A template without ``{prompt}`` gets the request appended, so a plain
    style description still works.
    """
    request = " ".join(request.split())
    if PROMPT_TOKEN not in template:
        return f"{template.strip()} {request}".strip()
    return template.replace(PROMPT_TOKEN, request.rstrip(".")).strip()


def _style_id(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9_]{1,40}", value):
        raise vol.Invalid("Style ids use lowercase letters, digits and _")
    return value


def _http_url(value: Any) -> str:
    value = str(value or "").strip().rstrip("/")
    if not value:
        return ""
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise vol.Invalid("Use an http:// or https:// address")
    # People paste the OpenAI base URL; the client adds /v1 itself.
    return value.removesuffix("/v1")


STYLE_SCHEMA = vol.Schema(
    {
        vol.Required("id"): _style_id,
        vol.Required("name"): vol.All(str, vol.Strip, vol.Length(min=1, max=40)),
        vol.Required("template"): vol.All(
            str, vol.Strip, vol.Length(min=1, max=MAX_TEMPLATE)
        ),
    }
)
VOICE_SCHEMA = vol.Schema(
    {
        vol.Optional("mode", default="fixed"): vol.In(VOICE_MODES),
        vol.Optional("image", default=""): str,
        vol.Optional("stt", default=""): str,
        vol.Optional("language", default=""): str,
        vol.Optional("agent", default="homeassistant"): str,
    }
)
SETTINGS_SCHEMA = vol.Schema(
    {
        vol.Optional("provider"): vol.In(("", *PROVIDERS)),
        vol.Optional("openrouter_key"): vol.All(str, vol.Strip, vol.Length(max=200)),
        vol.Optional("openrouter_model"): vol.All(str, vol.Length(min=1, max=120)),
        vol.Optional("local_url"): _http_url,
        vol.Optional("local_api"): vol.In(("", *LOCAL_APIS)),
        vol.Optional("local_model"): vol.All(str, vol.Length(max=200)),
        vol.Optional("local_steps"): vol.Any(
            None, vol.All(vol.Coerce(int), vol.Range(min=1, max=150))
        ),
        vol.Optional("ai_task_entity"): str,
        vol.Optional("style"): str,
        vol.Optional("styles"): vol.All(
            [STYLE_SCHEMA], vol.Length(max=MAX_STYLES + len(BUILTIN_STYLES))
        ),
        vol.Optional("rewrite_entity"): str,
        vol.Optional("voice"): {str: VOICE_SCHEMA},
    }
)


@dataclass(frozen=True)
class VoiceSettings:
    """What one frame's voice button does (local backend delivery only)."""

    mode: str = "fixed"
    image: str = ""
    stt: str = ""
    language: str = ""  # "" means Home Assistant's language
    agent: str = "homeassistant"

    def to_dict(self) -> dict[str, str]:
        return {
            "mode": self.mode,
            "image": self.image,
            "stt": self.stt,
            "language": self.language,
            "agent": self.agent,
        }


@dataclass(frozen=True)
class AiSettings:
    """Shared AI art settings for every frame."""

    provider: str = ""  # "" until set up
    openrouter_key: str = ""
    openrouter_model: str = DEFAULT_OPENROUTER_MODEL
    local_url: str = ""
    local_api: str = ""  # detected on connect
    local_model: str = ""
    local_steps: int | None = None
    ai_task_entity: str = ""
    style: str = DEFAULT_STYLE
    styles: tuple[Style, ...] = BUILTIN_STYLES
    rewrite_entity: str = ""
    voice: dict[str, VoiceSettings] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "openrouter_key": self.openrouter_key,
            "openrouter_model": self.openrouter_model,
            "local_url": self.local_url,
            "local_api": self.local_api,
            "local_model": self.local_model,
            "local_steps": self.local_steps,
            "ai_task_entity": self.ai_task_entity,
            "style": self.style,
            "styles": [style.to_dict() for style in self.styles],
            "rewrite_entity": self.rewrite_entity,
            "voice": {key: value.to_dict() for key, value in self.voice.items()},
        }

    @classmethod
    def from_dict(cls, data: Any) -> AiSettings:
        """Load stored settings, dropping anything that no longer validates."""
        settings = cls()
        if not isinstance(data, dict):
            return settings
        # Styles first, so a saved custom default style still exists.
        for key, value in sorted(data.items(), key=lambda item: item[0] != "styles"):
            try:
                settings = settings.updated({key: value})
            except vol.Invalid:
                continue
        return settings

    def updated(self, patch: dict[str, Any]) -> AiSettings:
        """Apply a validated partial update; raises ``vol.Invalid``."""
        data = SETTINGS_SCHEMA(dict(patch))
        changes: dict[str, Any] = {
            key: value
            for key, value in data.items()
            if key not in ("styles", "voice")
        }
        if "styles" in data:
            changes["styles"] = _merge_styles(data["styles"])
        if "voice" in data:
            changes["voice"] = {
                **self.voice,
                **{key: VoiceSettings(**value) for key, value in data["voice"].items()},
            }
        settings = replace(self, **changes)
        if settings.style not in {style.id for style in settings.styles}:
            settings = replace(settings, style=DEFAULT_STYLE)
        return settings

    def style_for(self, style_id: str | None) -> Style:
        """The requested style (by id or name), else the default one."""
        if style_id:
            wanted = style_id.casefold()
            for style in self.styles:
                if wanted in (style.id, style.name.casefold()):
                    return style
        return next(
            (style for style in self.styles if style.id == self.style),
            BUILTIN_BY_ID[DEFAULT_STYLE],
        )

    @property
    def configured(self) -> bool:
        if self.provider == PROVIDER_OPENROUTER:
            return bool(self.openrouter_key and self.openrouter_model)
        if self.provider == PROVIDER_LOCAL:
            return bool(self.local_url and self.local_api)
        if self.provider == PROVIDER_AI_TASK:
            return bool(self.ai_task_entity)
        return False


def _merge_styles(styles: list[dict[str, str]]) -> tuple[Style, ...]:
    """Validated styles in the given order; built-ins can't be removed."""
    merged: list[Style] = []
    seen: set[str] = set()
    for item in styles:
        if item["id"] in seen:
            raise vol.Invalid(f"Duplicate style {item['id']}")
        seen.add(item["id"])
        merged.append(Style(item["id"], item["name"], item["template"]))
    merged.extend(style for style in BUILTIN_STYLES if style.id not in seen)
    if len(merged) - len(BUILTIN_STYLES) > MAX_STYLES:
        raise vol.Invalid(f"Up to {MAX_STYLES} custom styles")
    return tuple(merged)


# ---------------------------------------------------------------- sizing


def _ratio(value: str) -> float | None:
    match = re.fullmatch(r"(\d+(?:\.\d+)?):(\d+(?:\.\d+)?)", value)
    if not match or float(match[2]) == 0:
        return None
    return float(match[1]) / float(match[2])


def closest_aspect(width: int, height: int, allowed: list[str]) -> str | None:
    """The supported ``W:H`` value nearest the frame's shape."""
    target = width / height
    ratios = [(value, ratio) for value in allowed if (ratio := _ratio(value))]
    if not ratios:
        return None
    return min(ratios, key=lambda item: abs(math.log(item[1] / target)))[0]


def _resolution_px(value: str) -> int | None:
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([kK]?)", value)
    if not match:
        return None
    return round(float(match[1]) * (1024 if match[2] else 1))


def pick_resolution(long_edge: int, allowed: list[str]) -> str | None:
    """The smallest supported resolution close to the panel's long edge.

    80% of the panel is plenty after dithering and keeps the price down: a
    1600 px Standard gets 1.5K, the 2560 px Large gets 2K.
    """
    sizes = sorted(
        (px, value) for value in allowed if (px := _resolution_px(value)) is not None
    )
    if not sizes:
        return None
    return next((value for px, value in sizes if px >= long_edge * 0.8), sizes[-1][1])


def local_size(width: int, height: int, long_edge: int = LOCAL_LONG_EDGE) -> tuple[int, int]:
    """Frame-shaped pixel size for local diffusion models (multiples of 64)."""

    def snap(value: float) -> int:
        return max(64, round(value / 64) * 64)

    if width >= height:
        return snap(long_edge), snap(long_edge * height / width)
    return snap(long_edge * width / height), snap(long_edge)


def price_for(pricing: list[dict[str, Any]], resolution: str | None) -> float | None:
    """Per-picture USD price from an OpenRouter endpoint, if priced per image.

    Token-priced models return None; their real cost is recorded after each
    picture instead.
    """
    rows = [
        row
        for row in pricing
        if row.get("billable") == "output_image" and row.get("unit") == "image"
    ]
    if not rows:
        return None
    wanted = (resolution or "").lower()
    for row in rows:
        variant = str(row.get("variant") or "").lower()
        if wanted and (variant == wanted or variant.endswith(f"_{wanted}")):
            return float(row["cost_usd"])
    plain = [row for row in rows if not row.get("variant")]
    return float((plain or rows)[0]["cost_usd"])


# ---------------------------------------------------------------- responses


@dataclass(frozen=True)
class GeneratedImage:
    data: bytes
    mime_type: str
    model: str | None
    cost: float | None = None  # USD, when the service reports it


def sniff_mime(data: bytes) -> str:
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    raise AiArtError("The image service returned something that is not a picture")


def decode_image(value: Any) -> bytes:
    """Base64 or data-URI image text to bytes."""
    if not isinstance(value, str) or not value:
        raise AiArtError("The image service returned no picture")
    if value.startswith("data:"):
        value = value.partition(",")[2]
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as err:
        raise AiArtError("The image service returned a damaged picture") from err


def parse_openai_images(body: Any) -> tuple[bytes, str]:
    """``data[0]`` of an OpenAI-style images response (OpenRouter included)."""
    items = body.get("data") if isinstance(body, dict) else None
    if not isinstance(items, list) or not items or not isinstance(items[0], dict):
        raise AiArtError("The image service returned no picture")
    item = items[0]
    data = decode_image(item.get("b64_json") or item.get("url"))
    return data, sniff_mime(data)


def parse_sdwebui_images(body: Any) -> tuple[bytes, str]:
    items = body.get("images") if isinstance(body, dict) else None
    if not isinstance(items, list) or not items:
        raise AiArtError("The image server returned no picture")
    data = decode_image(items[0])
    return data, sniff_mime(data)


def _error_text(body: Any) -> str:
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])
        for key in ("message", "detail", "error"):
            if isinstance(body.get(key), str):
                return str(body[key])
    return ""


def _status_error(service: str, status: int, body: Any) -> AiArtError:
    detail = _error_text(body)
    if status in (401, 403):
        return AiArtError(f"{service} rejected the API key")
    if status == 402:
        return AiArtError(f"{service} is out of credits")
    if status == 429:
        return AiArtError(f"{service} is rate limiting requests; try again shortly")
    return AiArtError(f"{service} answered {status}{f': {detail}' if detail else ''}")


async def _call(
    session: Any,
    method: str,
    url: str,
    service: str,
    *,
    timeout: int = TIMEOUT,
    **kwargs: Any,
) -> Any:
    try:
        async with session.request(
            method, url, timeout=aiohttp.ClientTimeout(total=timeout), **kwargs
        ) as response:
            try:
                body = await response.json(content_type=None)
            except ValueError:
                body = None
            if response.status >= 400:
                raise _status_error(service, response.status, body)
            if body is None:
                raise AiArtError(f"{service} sent a reply that is not JSON")
            return body
    except TimeoutError as err:
        raise AiArtError(f"{service} did not answer in time") from err
    except aiohttp.ClientError as err:
        raise AiArtError(f"Could not reach {service}: {err}") from err


# ---------------------------------------------------------------- OpenRouter


def _openrouter_headers(api_key: str) -> dict[str, str]:
    return {**OPENROUTER_HEADERS, "Authorization": f"Bearer {api_key}"}


async def openrouter_credits(session: Any, api_key: str) -> float | None:
    """USD credit left on the account, or None when unknown."""
    body = await _call(
        session, "GET", f"{OPENROUTER_BASE}/credits", "OpenRouter",
        headers=_openrouter_headers(api_key),
    )
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict):
        return None
    try:
        return round(float(data["total_credits"]) - float(data["total_usage"]), 4)
    except (KeyError, TypeError, ValueError):
        return None


async def openrouter_models(session: Any) -> list[dict[str, Any]]:
    """Image models with the parameters each one accepts."""
    body = await _call(session, "GET", f"{OPENROUTER_BASE}/images/models", "OpenRouter")
    rows = body.get("data") if isinstance(body, dict) else body
    models = []
    for row in rows if isinstance(rows, list) else ():
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            continue
        params = row.get("supported_parameters") or {}

        def values(name: str, params: dict[str, Any] = params) -> list[str]:
            found = (params.get(name) or {}).get("values")
            return [str(value) for value in found] if isinstance(found, list) else []

        models.append(
            {
                "id": row["id"],
                "name": str(row.get("name") or row["id"]).split(": ", 1)[-1],
                "aspect_ratios": values("aspect_ratio"),
                "resolutions": values("resolution"),
            }
        )
    return models


async def openrouter_pricing(session: Any, model_id: str) -> list[dict[str, Any]]:
    body = await _call(
        session,
        "GET",
        f"{OPENROUTER_BASE}/images/models/{quote(model_id, safe='/')}/endpoints",
        "OpenRouter",
    )
    # Answered as ``{"id": ..., "endpoints": [...]}``, without a data wrapper.
    data = body.get("data", body) if isinstance(body, dict) else body
    endpoints = data.get("endpoints") if isinstance(data, dict) else data
    if not isinstance(endpoints, list) or not endpoints:
        return []
    pricing = endpoints[0].get("pricing") if isinstance(endpoints[0], dict) else None
    return pricing if isinstance(pricing, list) else []


def openrouter_request(
    model: dict[str, Any], prompt: str, width: int, height: int
) -> dict[str, Any]:
    """Request body shaped to the frame, using only parameters the model takes."""
    body: dict[str, Any] = {"model": model["id"], "prompt": prompt}
    if aspect := closest_aspect(width, height, model.get("aspect_ratios") or []):
        body["aspect_ratio"] = aspect
    if resolution := pick_resolution(max(width, height), model.get("resolutions") or []):
        body["resolution"] = resolution
    return body


async def openrouter_generate(
    session: Any, api_key: str, model: dict[str, Any], prompt: str, width: int, height: int
) -> GeneratedImage:
    body = await _call(
        session,
        "POST",
        f"{OPENROUTER_BASE}/images",
        "OpenRouter",
        timeout=GENERATE_TIMEOUT,
        headers=_openrouter_headers(api_key),
        json=openrouter_request(model, prompt, width, height),
    )
    data, mime = parse_openai_images(body)
    usage = body.get("usage") if isinstance(body, dict) else None
    cost = usage.get("cost") if isinstance(usage, dict) else None
    return GeneratedImage(
        data, mime, model["id"], float(cost) if isinstance(cost, int | float) else None
    )


# ---------------------------------------------------------------- local server


async def local_detect(session: Any, url: str) -> tuple[str, list[str]]:
    """Which image API a local server speaks, and the models it lists."""
    errors: list[str] = []
    try:
        body = await _call(session, "GET", f"{url}/v1/models", "The local server")
        rows = body.get("data") if isinstance(body, dict) else None
        if isinstance(rows, list):
            return LOCAL_OPENAI, [
                str(row["id"]) for row in rows if isinstance(row, dict) and row.get("id")
            ]
    except AiArtError as err:
        errors.append(str(err))
    try:
        rows = await _call(session, "GET", f"{url}/sdapi/v1/sd-models", "The local server")
        if isinstance(rows, list):
            return LOCAL_SDWEBUI, [
                str(row.get("title") or row.get("model_name"))
                for row in rows
                if isinstance(row, dict) and (row.get("title") or row.get("model_name"))
            ]
    except AiArtError as err:
        errors.append(str(err))
    detail = f" ({errors[-1]})" if errors else ""
    raise AiArtError(
        "No OpenAI-style or Stable Diffusion WebUI image API answered at "
        f"{url}{detail}"
    )


def local_request(
    api: str, model: str, prompt: str, width: int, height: int, steps: int | None
) -> tuple[str, dict[str, Any]]:
    """Path and body for one local generation."""
    w, h = local_size(width, height)
    if api == LOCAL_SDWEBUI:
        body: dict[str, Any] = {"prompt": prompt, "width": w, "height": h, "batch_size": 1}
        if steps:
            body["steps"] = steps
        if model:
            body["override_settings"] = {"sd_model_checkpoint": model}
        return "/sdapi/v1/txt2img", body
    body = {"prompt": prompt, "size": f"{w}x{h}", "n": 1, "response_format": "b64_json"}
    if model:
        body["model"] = model
    return "/v1/images/generations", body


async def local_generate(
    session: Any,
    url: str,
    api: str,
    model: str,
    prompt: str,
    width: int,
    height: int,
    steps: int | None,
) -> GeneratedImage:
    path, payload = local_request(api, model, prompt, width, height, steps)
    body = await _call(
        session, "POST", f"{url}{path}", "The local server",
        timeout=GENERATE_TIMEOUT, json=payload,
    )
    parse = parse_sdwebui_images if api == LOCAL_SDWEBUI else parse_openai_images
    data, mime = parse(body)
    return GeneratedImage(data, mime, model or None, 0.0)


def month_start(now: float | None = None) -> float:
    """Epoch of the first moment of the current local month."""
    local = time.localtime(now)
    return time.mktime((local.tm_year, local.tm_mon, 1, 0, 0, 0, 0, 0, -1))
