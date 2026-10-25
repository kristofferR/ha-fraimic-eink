"""Opt-in companion delivery and a narrowly authenticated recorded-voice bridge."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
import uuid
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

import aiohttp
from aiohttp import web
from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .backend_errors import BackendBusy, BackendExpired, BackendUnavailable
from .helpers import loaded_fraimic_entries

if TYPE_CHECKING:
    from .coordinator import FraimicConfigEntry
    from .backend_voice import VoiceJobs

CONF_BACKEND_URL = "backend_url"
CONF_BACKEND_TOKEN = "backend_token"
CONF_VOICE_MODE = "backend_voice_mode"
CONF_VOICE_IMAGE = "backend_voice_image"
CONF_VOICE_STT = "backend_voice_stt"
CONF_VOICE_LANGUAGE = "backend_voice_language"
CONF_VOICE_AI = "backend_voice_ai"
CONF_VOICE_AGENT = "backend_voice_agent"
BACKEND_OPTIONS = (CONF_BACKEND_URL, CONF_BACKEND_TOKEN, CONF_VOICE_MODE,
                   CONF_VOICE_IMAGE, CONF_VOICE_STT, CONF_VOICE_LANGUAGE,
                   CONF_VOICE_AI, CONF_VOICE_AGENT)


def validate_backend_url(value: str) -> str:
    parsed = urlsplit(value)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname
        or parsed.username or parsed.password or parsed.path not in ("", "/")
        or parsed.query or parsed.fragment or len(value) > 512):
        raise ValueError("Use the companion's HTTP(S) origin without a path")
    return value.rstrip("/")


class LocalBackend:
    def __init__(self, hass: HomeAssistant, entry: FraimicConfigEntry) -> None:
        self.hass, self.entry = hass, entry
        self.url = validate_backend_url(entry.options[CONF_BACKEND_URL])
        self.token: str = entry.options[CONF_BACKEND_TOKEN]
        if len(self.token) < 32:
            raise ValueError("A separate bridge token of at least 32 characters is required")
        self.store: Store[dict[str, Any]] = Store(hass, 1, f"{DOMAIN}.backend.{entry.entry_id}")
        self.pending: dict[str, Any] | None = None
        self.status: dict[str, Any] = {}
        self.next_wake: int | None = None
        self.schedule_pending = False
        self.acceptance_pending = False
        self.voice: VoiceJobs | None = None

    async def async_setup(self) -> None:
        from .backend_voice import VoiceJobs

        data = await self.store.async_load() or {}
        self.pending = data.get("pending")
        self.next_wake = data.get("next_wake")
        self.schedule_pending = data.get("schedule_pending", False)
        self.acceptance_pending = data.get("acceptance_pending", False)
        self.voice = VoiceJobs(self.hass, self.entry)
        await self.voice.async_setup()
        self.entry.async_on_unload(self.voice.shutdown)

    async def request(self, method: str, path: str, *, data: bytes | None = None,
                      payload: dict[str, object] | None = None,
                      job_id: str | None = None, expires_at: float | None = None) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.token}"}
        if job_id is not None:
            headers["X-Fraimic-Job"] = job_id
        if expires_at is not None:
            headers["X-Fraimic-Expires"] = str(int(expires_at))
        if data is not None:
            headers["Content-Type"] = "application/octet-stream"
        try:
            async with async_get_clientsession(self.hass).request(
                method, f"{self.url}{path}", headers=headers, data=data, json=payload,
                timeout=aiohttp.ClientTimeout(total=30), allow_redirects=False,
            ) as reply:
                if reply.status == 409:
                    raise BackendBusy("The local backend is handling another delivery or voice request")
                if reply.status == 410:
                    raise BackendExpired("The previous local delivery has expired")
                if reply.status != 200:
                    raise BackendUnavailable("The local backend rejected the request")
                raw = bytearray()
                async for chunk in reply.content.iter_chunked(4096):
                    raw.extend(chunk)
                    if len(raw) > 4095:
                        raise BackendUnavailable("The local backend returned an oversized response")
                result = json.loads(raw)
                if not isinstance(result, dict):
                    raise BackendUnavailable("The local backend returned invalid state")
                return result
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise BackendUnavailable("The local backend is unavailable") from err

    async def async_status(self) -> dict[str, Any]:
        await self.async_resume_delivery()
        if self.schedule_pending:
            deadline = self.next_wake
            if deadline is not None and deadline <= time.time() + 30:
                deadline = int(time.time() + 60)
            await self.async_schedule(deadline)
        self.status = await self.request("GET", "/bridge/state")
        self.entry.runtime_data.coordinator.async_backend_contact(self.status.get("device", {}))
        return self.status

    async def async_schedule(self, timestamp: int | None) -> None:
        self.next_wake = timestamp
        self.schedule_pending = True
        await self._save()
        await self.request("PUT", "/bridge/schedule", payload={"next_image_utc": timestamp})
        self.schedule_pending = False
        await self._save()

    async def _save(self) -> None:
        await self.store.async_save({"pending": self.pending, "next_wake": self.next_wake,
                                     "schedule_pending": self.schedule_pending,
                                     "acceptance_pending": self.acceptance_pending})

    async def async_deliver(self, packed: bytes, *, expires_at: float | None = None) -> None:
        """Persist the request identity before an ambiguous HTTP exchange."""
        digest = hashlib.sha256(packed).hexdigest()
        if (self.pending is None or self.pending["hash"] != digest
            or self.pending.get("expires_at", float("inf")) <= time.time()):
            self.pending = {"id": uuid.uuid4().hex, "hash": digest}
            await self._save()
        try:
            self.status = await self.request("POST", "/bridge/delivery", data=packed,
                                             job_id=self.pending["id"], expires_at=expires_at)
        except BackendExpired:
            # A definitive tombstone permits a new delivery of the same art.
            # Connection failures keep the old ID; they never enter this path.
            self.pending = {"id": uuid.uuid4().hex, "hash": digest}
            await self._save()
            self.status = await self.request("POST", "/bridge/delivery", data=packed,
                                             job_id=self.pending["id"], expires_at=expires_at)
        if "expires_at" in self.status:
            self.pending["expires_at"] = self.status["expires_at"]
        self.acceptance_pending = True
        await self._save()
        # Keep the accepted identity through scheduler persistence. Repeated same
        # content is intentionally deduplicated until a different image is sent.
        await self.async_resume_delivery()

    async def async_resume_delivery(self) -> None:
        """Protect accepted artwork once the startup scheduler is available."""
        scheduler = self.entry.runtime_data.scheduler
        if self.acceptance_pending and scheduler is not None:
            await scheduler.async_backend_delivery_accepted()
            self.acceptance_pending = False
            await self._save()


class BackendVoiceView(HomeAssistantView):
    """Only the configured companion credential can enter this one bridge view."""

    url = "/api/fraimic/backend/voice"
    name = "api:fraimic:backend:voice"
    requires_auth = False

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app[KEY_HASS]
        authorization = request.headers.get("Authorization", "").encode("utf-8", "surrogateescape")
        backend = next((entry.runtime_data.backend for entry in loaded_fraimic_entries(hass)
                        if entry.runtime_data.backend is not None and hmac.compare_digest(
                            authorization, f"Bearer {entry.runtime_data.backend.token}".encode())), None)
        if backend is None or backend.voice is None:
            raise web.HTTPUnauthorized()
        ident = request.headers.get("X-Fraimic-Job", "")
        orientation = request.headers.get("X-Fraimic-Orientation", "")
        if (len(ident) != 32 or any(c not in "0123456789abcdef" for c in ident)
            or orientation not in ("portrait", "landscape")):
            raise web.HTTPBadRequest()
        audio = bytearray()
        try:
            async with asyncio.timeout(30):
                async for chunk in request.content.iter_chunked(65536):
                    audio.extend(chunk)
                    if len(audio) > 2_128_192:
                        raise web.HTTPRequestEntityTooLarge(max_size=2_128_192, actual_size=len(audio))
            packed = await backend.voice.async_process(ident, bytes(audio), orientation)
        except (HomeAssistantError, ValueError, TimeoutError):
            # Exception messages can contain transcript/provider URLs.
            return web.Response(status=503, text="voice_job_failed")
        return web.Response(body=packed, content_type="application/octet-stream",
                            headers={"Cache-Control": "no-store"})
