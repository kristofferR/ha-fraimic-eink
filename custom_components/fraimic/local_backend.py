"""Opt-in companion delivery and a narrowly authenticated recorded-voice bridge."""

from __future__ import annotations

import asyncio
import base64
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
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    CONF_HEIGHT, CONF_ROTATION, CONF_WIDTH, DEFAULT_HEIGHT, DEFAULT_ROTATION,
    DEFAULT_WIDTH, DOMAIN,
)
from .backend_errors import BackendBusy, BackendExpired, BackendUnauthorized, BackendUnavailable
from .helpers import loaded_fraimic_entries
from .image_convert import bin_to_png

if TYPE_CHECKING:
    from .coordinator import FraimicConfigEntry
    from .backend_voice import VoiceJobs

CONF_BACKEND_URL = "backend_url"
CONF_BACKEND_TOKEN = "backend_token"
# Former voice options, read once to move them into the AI art settings
# (``ai_manager``), which the panel edits without reloading the frame.
CONF_VOICE_MODE = "backend_voice_mode"
CONF_VOICE_IMAGE = "backend_voice_image"
CONF_VOICE_STT = "backend_voice_stt"
CONF_VOICE_LANGUAGE = "backend_voice_language"
CONF_VOICE_AI = "backend_voice_ai"
CONF_VOICE_AGENT = "backend_voice_agent"
BACKEND_OPTIONS = (CONF_BACKEND_URL, CONF_BACKEND_TOKEN)


def validate_backend_url(value: str) -> str:
    parsed = urlsplit(value)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname
        or parsed.username or parsed.password or parsed.path not in ("", "/")
        or parsed.query or parsed.fragment or len(value) > 512):
        raise ValueError("Use the companion's HTTP(S) origin without a path")
    return value.rstrip("/")


# A published wake that passes this long without a frame poll counts as missed.
MISSED_WAKE_GRACE = 15 * 60
# Stock timers can wake the frame a little before the published time.
EARLY_WAKE_SLACK = 5 * 60

# Companion job state -> the summary the status sensor and panel show.
SUMMARY_STATES = {
    "ready": "waiting", "transferring": "transferring", "served": "served",
    "uploading": "listening", "uploaded": "working", "processing": "working",
    "failed": "failed", "uncertain": "failed", "expired": "expired",
    "cancelled": "idle",
}
SUMMARY_OPTIONS = ["idle", "waiting", "transferring", "served", "listening",
                   "working", "expired", "failed", "offline"]


async def async_bridge_request(
    hass: HomeAssistant, url: str, token: str, method: str, path: str, *,
    data: bytes | None = None, payload: dict[str, object] | None = None,
    job_id: str | None = None, expires_at: float | None = None,
) -> dict[str, Any]:
    """One authenticated companion bridge call with a bounded JSON reply."""
    headers = {"Authorization": f"Bearer {token}"}
    if job_id is not None:
        headers["X-Fraimic-Job"] = job_id
    if expires_at is not None:
        headers["X-Fraimic-Expires"] = str(int(expires_at))
    if data is not None:
        headers["Content-Type"] = "application/octet-stream"
    try:
        async with async_get_clientsession(hass).request(
            method, f"{url}{path}", headers=headers, data=data, json=payload,
            timeout=aiohttp.ClientTimeout(total=30), allow_redirects=False,
        ) as reply:
            if reply.status == 401:
                raise BackendUnauthorized("The local backend rejected the bridge token")
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
        # The earliest unacknowledged wake, kept across rescheduling.
        self.last_due: int | None = None
        # Whether the last bridge status call worked; None until tried.
        self.online: bool | None = None
        self.checked_at: float | None = None
        # The latest handed-off picture: {"job", "title", "source", "at"}.
        # Shown as waiting/served, never as confirmed on the panel.
        self.preview: dict[str, Any] | None = None
        self.preview_png: bytes | None = None

    async def async_setup(self) -> None:
        from .backend_voice import VoiceJobs

        data = await self.store.async_load() or {}
        self.pending = data.get("pending")
        self.next_wake = data.get("next_wake")
        self.schedule_pending = data.get("schedule_pending", False)
        self.acceptance_pending = data.get("acceptance_pending", False)
        self.last_due = data.get("last_due")
        preview = data.get("preview")
        if isinstance(preview, dict):
            try:
                self.preview_png = base64.b64decode(preview.pop("png", "") or "", validate=True) or None
            except ValueError:
                self.preview_png = None
            self.preview = preview
        self.voice = VoiceJobs(self.hass, self.entry)
        await self.voice.async_setup()
        self.entry.async_on_unload(self.voice.shutdown)

    async def request(self, method: str, path: str, *, data: bytes | None = None,
                      payload: dict[str, object] | None = None,
                      job_id: str | None = None, expires_at: float | None = None) -> dict[str, Any]:
        return await async_bridge_request(
            self.hass, self.url, self.token, method, path, data=data,
            payload=payload, job_id=job_id, expires_at=expires_at,
        )

    async def async_status(self) -> dict[str, Any]:
        before = (self.online, self.status)
        try:
            await self.async_resume_delivery()
            if self.schedule_pending:
                deadline = self.next_wake
                if deadline is not None and deadline <= time.time() + 30:
                    deadline = int(time.time() + 60)
                await self.async_schedule(deadline)
            self.status = await self.request("GET", "/bridge/state")
            self.online = True
        except BackendUnavailable:
            self.online = False
            raise
        finally:
            self.checked_at = time.time()
            if (self.online, self.status) != before:
                self._changed()
        self.entry.runtime_data.coordinator.async_backend_contact(self.status.get("device", {}))
        return self.status

    def _changed(self) -> None:
        """Entities and the panel read backend state directly; nudge them."""
        coordinator = getattr(self.entry.runtime_data, "coordinator", None)
        if coordinator is not None:
            coordinator.async_update_listeners()

    def summary(self) -> str:
        """One user-facing state for the latest companion or voice job."""
        if self.online is False:
            return "offline"
        if self.voice is not None and self.voice.tasks:
            return "working"
        jobs = self.status.get("jobs") or []
        if not jobs:
            return "idle"
        latest = max(jobs, key=lambda job: job.get("created_at") or 0)
        return SUMMARY_STATES.get(str(latest.get("state")), "idle")

    def job_status(self, ident: str | None) -> dict[str, Any] | None:
        """The companion's latest report for one job, if still listed."""
        return next((job for job in self.status.get("jobs") or []
                     if ident is not None and job.get("job_id") == ident), None)

    def missed_wake(self, last_seen: float | None) -> int | None:
        """The earliest due wake the frame has not acknowledged."""
        now = time.time()
        # A wake that came due without being replaced yet counts too.
        due = min((wake for wake in (self.last_due, self.next_wake)
                   if wake is not None and wake <= now
                   and (last_seen is None or last_seen < wake - EARLY_WAKE_SLACK)), default=None)
        if due is None or now < due + MISSED_WAKE_GRACE:
            return None
        return due

    def diagnostics(self) -> dict[str, Any]:
        jobs = self.voice.jobs if self.voice is not None else {}
        return {
            "summary": self.summary(), "online": self.online, "checked_at": self.checked_at,
            "next_wake": self.next_wake, "last_due": self.last_due, "status": self.status,
            # Transcripts stay private library metadata; share only the lifecycle.
            "voice": [{key: job.get(key) for key in ("created", "state", "outcome", "mode")}
                      for job in jobs.values()],
        }

    @callback
    def set_preview(self, ident: str, png: bytes | None, *, title: str,
                    source: dict[str, Any] | None = None) -> None:
        """Remember what was handed off last so the player can show it.

        Best effort: a failed write must never fail the handoff it describes.
        """
        self.preview = {"job": ident, "title": title, "source": source, "at": time.time()}
        self.preview_png = png
        self.store.async_delay_save(self._payload, 1)
        self._changed()

    async def async_schedule(self, timestamp: int | None) -> None:
        last_seen = self.entry.runtime_data.coordinator.last_seen
        self.last_due = min((wake for wake in (self.last_due, self.next_wake)
                             if wake is not None and wake <= time.time() + 30
                             and (last_seen is None or last_seen < wake - EARLY_WAKE_SLACK)),
                            default=None)
        self.next_wake = timestamp
        self._changed()
        self.schedule_pending = True
        await self._save()
        await self.request("PUT", "/bridge/schedule", payload={"next_image_utc": timestamp})
        self.schedule_pending = False
        await self._save()

    def _payload(self) -> dict[str, Any]:
        preview = None
        if self.preview is not None:
            png = base64.b64encode(self.preview_png).decode("ascii") if self.preview_png else None
            preview = {**self.preview, "png": png}
        return {"pending": self.pending, "next_wake": self.next_wake,
                "schedule_pending": self.schedule_pending,
                "acceptance_pending": self.acceptance_pending,
                "last_due": self.last_due, "preview": preview}

    async def _save(self) -> None:
        await self.store.async_save(self._payload())

    async def async_deliver(self, packed: bytes, *, expires_at: float | None = None,
                            title: str | None = None, preview_png: bytes | None = None,
                            source: dict[str, Any] | None = None) -> None:
        """Persist the request identity before an ambiguous HTTP exchange."""
        digest = hashlib.sha256(packed).hexdigest()
        pending_expiry = self.pending.get("expires_at") if self.pending is not None else None
        if (self.pending is None or self.pending["hash"] != digest
            or pending_expiry is not None and (
                pending_expiry <= time.time()
                or (expires_at is not None and int(pending_expiry) != int(expires_at))
            )):
            self.pending = {"id": uuid.uuid4().hex, "hash": digest}
            await self._save()
        try:
            accepted = await self.request("POST", "/bridge/delivery", data=packed,
                                          job_id=self.pending["id"], expires_at=expires_at)
        except BackendExpired:
            # A definitive tombstone permits a new delivery of the same art.
            # Connection failures keep the old ID; they never enter this path.
            self.pending = {"id": uuid.uuid4().hex, "hash": digest}
            await self._save()
            accepted = await self.request("POST", "/bridge/delivery", data=packed,
                                          job_id=self.pending["id"], expires_at=expires_at)
        if "expires_at" in accepted:
            self.pending["expires_at"] = accepted["expires_at"]
        # The reply is one job; keep the cached state's shape until the next poll.
        jobs = [job for job in self.status.get("jobs") or []
                if job.get("job_id") != accepted.get("job_id")]
        self.status = {**self.status, "jobs": [*jobs, accepted][-8:]}
        self.acceptance_pending = True
        await self._save()
        if preview_png is None:
            # Queued LAN buffers migrate without their preview.
            try:
                preview_png = await self.hass.async_add_executor_job(
                    bin_to_png, packed,
                    self.entry.data.get(CONF_WIDTH, DEFAULT_WIDTH),
                    self.entry.data.get(CONF_HEIGHT, DEFAULT_HEIGHT),
                    (-self.entry.options.get(CONF_ROTATION, DEFAULT_ROTATION)) % 360,
                )
            except ValueError:
                preview_png = None
        self.set_preview(self.pending["id"], preview_png, title=title or "Artwork", source=source)
        # Keep the accepted identity through scheduler persistence. Deduplicate
        # repeated content unless its accepted expiry changes or elapses.
        await self.async_resume_delivery()

    async def async_resume_delivery(self) -> None:
        """Protect accepted artwork once the startup scheduler is available."""
        scheduler = self.entry.runtime_data.scheduler
        if self.acceptance_pending and scheduler is not None:
            await scheduler.async_backend_delivery_accepted()
            self.acceptance_pending = False
            await self._save()


class BackendStatusView(HomeAssistantView):
    """Companion health and recent voice requests for the panel."""

    url = "/api/fraimic/backend/status/{entry_id}"
    name = "api:fraimic:backend:status"

    async def get(self, request: web.Request, entry_id: str) -> web.Response:
        from .ai_manager import get_ai_manager
        from .http_helpers import require_loaded_entry
        from .library import get_library

        if not getattr(request.get("hass_user"), "is_admin", False):
            # Transcripts are private library metadata.
            raise web.HTTPForbidden(text="Admin access required")
        hass: HomeAssistant = request.app[KEY_HASS]
        entry = require_loaded_entry(hass, entry_id)
        backend: LocalBackend | None = entry.runtime_data.backend
        if backend is None:
            raise web.HTTPNotFound(text="This frame does not use the local backend")
        coordinator = entry.runtime_data.coordinator

        def iso(epoch: float | None) -> str | None:
            return dt_util.utc_from_timestamp(epoch).isoformat() if epoch is not None else None

        library = get_library(hass)
        manager = get_ai_manager(hass)
        voice = backend.voice
        requests = []
        cutoff = time.time() - 86400
        jobs = sorted(((ident, job) for ident, job in (voice.jobs if voice is not None else {}).items()
                       if job["created"] >= cutoff),
                      key=lambda item: item[1]["created"], reverse=True)
        for ident, job in jobs:
            if "transcript" not in job and "mode" not in job and job["state"] == "expired":
                continue  # A replay tombstone keeps no request details.
            companion = backend.job_status(ident) or {}
            image_id = job.get("library_image")
            image = library.images.get(image_id) if library is not None and image_id else None
            metadata = (image.creation.metadata if image is not None and image.creation else None) or {}
            if job.get("outcome") == "uncertain":
                status = "uncertain"
            elif job["state"] == "failed":
                status = "failed"
            elif companion.get("served_at") is not None:
                status = "served"
            elif job["state"] == "ready":
                status = "ready"
            else:
                status = "working"
            requests.append({
                "id": ident, "created": iso(job["created"]), "status": status,
                "mode": job.get("mode"), "transcript": job.get("transcript"),
                "image_id": image_id if image is not None else None,
                "style": metadata.get("style"), "cost": metadata.get("cost"),
                "served_at": iso(companion.get("served_at")),
            })
            if len(requests) == 20:
                break
        data = coordinator.data or {}
        return self.json({
            "summary": backend.summary(),
            "online": backend.online,
            "checked_at": iso(backend.checked_at),
            "last_seen": iso(coordinator.last_seen),
            "battery": (data.get("battery") or {}).get("percent"),
            "next_wake": iso(backend.next_wake),
            "missed_wake": iso(backend.missed_wake(coordinator.last_seen)),
            "voice_mode": manager.voice(entry.entry_id).mode if manager is not None else None,
            "requests": requests,
        })


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
