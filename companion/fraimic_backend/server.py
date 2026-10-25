"""An allowlisted stock protocol listener with a per-frame HA bridge."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import secrets
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

import aiohttp
from aiohttp import web

from .model import (
    ART_TTL, ASSET_TTL, JOB_TTL, MAX_AUDIO, MAX_JOBS, MAX_JSON, MAX_PANEL,
    MAX_STORAGE, TERMINAL, Device, Job, origin, validate_panel, validate_wav,
)
from .store import Store

VoiceProcessor = Callable[[Device, Job], Awaitable[bytes]]
_NO_USER = object()
_LOGGER = logging.getLogger(__name__)


def response(body: object, status: int = 200) -> web.Response:
    encoded = json.dumps(body, separators=(",", ":"), allow_nan=False).encode()
    if len(encoded) > MAX_JSON:
        raise ValueError("Stock response exceeds its read buffer")
    return web.Response(body=encoded, status=status, content_type="application/json",
                        headers={"Cache-Control": "no-store"})


@web.middleware
async def errors(request: web.Request, handler: Callable[[web.Request], Awaitable[web.StreamResponse]]) -> web.StreamResponse:
    try:
        return await handler(request)
    except web.HTTPException as err:
        return response({"error": err.reason}, err.status)
    except (ValueError, KeyError, TypeError):
        return response({"error": "invalid_request"}, 400)
    except (aiohttp.ClientError, TimeoutError, OSError):
        # Never log request paths, signed URLs, provider messages or payloads.
        return response({"error": "backend_unavailable"}, 503)
    except Exception:
        # aiohttp's default exception logger can include a credential-bearing
        # request path. Keep even unexpected failures inside this boundary.
        return response({"error": "internal_error"}, 500)


async def read_limited(request: web.Request, limit: int) -> bytes:
    if request.content_length is not None and request.content_length > limit:
        raise web.HTTPRequestEntityTooLarge(max_size=limit, actual_size=request.content_length)
    result = bytearray()
    async with asyncio.timeout(30):
        async for chunk in request.content.iter_chunked(65536):
            result.extend(chunk)
            if len(result) > limit:
                raise web.HTTPRequestEntityTooLarge(max_size=limit, actual_size=len(result))
    return bytes(result)


async def json_body(request: web.Request) -> dict[str, object]:
    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        if len({key.lower() for key, _ in pairs}) != len(pairs):
            raise ValueError("Duplicate JSON member")
        return dict(pairs)

    data = json.loads(await read_limited(request, MAX_JSON), object_pairs_hook=unique)
    if not isinstance(data, dict):
        raise ValueError("Expected an object")
    return data


class Backend:
    def __init__(self, devices: list[Device], public_url: str, database: Path,
                 *, process_voice: VoiceProcessor | None = None,
                 clock: Callable[[], float] = time.time) -> None:
        self.devices = {device.id: device for device in devices}
        if (not devices or len(self.devices) != len(devices)
            or len({d.device_key for d in devices}) != len(devices)
            or len({d.bridge_token for d in devices}) != len(devices)):
            raise ValueError("Device IDs, keys and bridge tokens must be unique")
        self.public_url = origin(public_url)
        self.store = Store(database)
        self.clock = clock
        self.jobs: dict[str, Job] = {}
        self.wakes: dict[str, int | None] = {}
        self.telemetry: dict[str, dict[str, object]] = {}
        self.lock = asyncio.Lock()
        self.tasks: dict[str, asyncio.Task[None]] = {}
        self.session: aiohttp.ClientSession | None = None
        self.process_voice = process_voice or self._ha_voice

    async def _save(self, job: Job) -> None:
        await asyncio.to_thread(self.store.save, job)

    async def setup(self) -> None:
        self.jobs, self.wakes, self.telemetry = await asyncio.to_thread(self.store.load)
        for device in self.devices.values():
            binding = hashlib.sha256(f"{device.device_key}\0{device.user_id}\0{device.display_type}".encode()).hexdigest()
            await asyncio.to_thread(self.store.enroll, device.id, binding)
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=500))
        async with self.lock:
            for job in self.jobs.values():
                if job.state == "processing":
                    # The HA journal decides whether a same-ID request can resume.
                    job.state = "uploaded"
                    await self._save(job)
                elif job.state == "transferring":
                    job.state = "ready"
                    await self._save(job)
            await self._expire()

    async def close(self) -> None:
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if self.session:
            await self.session.close()

    async def _expire(self) -> None:
        now = self.clock()
        for job in list(self.jobs.values()):
            if job.expires <= now and job.state not in TERMINAL:
                job.state = "expired"
                job.audio = job.asset = b""
                await self._save(job)
            if job.state in TERMINAL and job.expires + 86400 <= now:
                await asyncio.to_thread(self.store.delete, job.id)
                del self.jobs[job.id]

    def _capacity(self, extra: int = 0) -> None:
        active = [j for j in self.jobs.values() if j.state not in TERMINAL]
        if (len(active) >= MAX_JOBS or len(self.tasks) >= MAX_JOBS
            or sum(len(j.audio) + len(j.asset) for j in active) + extra > MAX_STORAGE):
            raise web.HTTPServiceUnavailable(reason="capacity_exceeded")

    def _device(self, key: object, user: object = _NO_USER) -> Device:
        if isinstance(key, str):
            for device in self.devices.values():
                if hmac.compare_digest(key.encode(), device.device_key.encode()):
                    if user is not _NO_USER and user != device.user_id:
                        break
                    return device
        raise web.HTTPUnauthorized()

    def _bridge(self, request: web.Request) -> Device:
        token = request.headers.get("Authorization", "")
        for device in self.devices.values():
            if hmac.compare_digest(token.encode(), f"Bearer {device.bridge_token}".encode()):
                return device
        raise web.HTTPUnauthorized()

    def _ticket(self, ticket: str, purpose: str) -> Job:
        for job in self.jobs.values():
            expected = job.upload_ticket if purpose == "upload" else job.asset_ticket
            if expected and hmac.compare_digest(ticket, expected):
                if job.device not in self.devices or job.expires <= self.clock() or job.state in TERMINAL:
                    raise web.HTTPGone()
                return job
        raise web.HTTPNotFound()

    def _busy(self, device: Device, *, except_job: str = "") -> bool:
        return any(j.device == device.id and j.id != except_job and j.busy(self.clock())
                   for j in self.jobs.values())

    def _asset_url(self, job: Job) -> str:
        return f"{self.public_url}/panel/{job.asset_ticket}"

    async def poll(self, request: web.Request) -> web.Response:
        device = self._device(request.match_info["key"])
        if request.query.get("display_type", device.display_type) != device.display_type:
            raise web.HTTPConflict(reason="panel_model_mismatch")
        # All other query fields are telemetry, never identity or settings authority.
        async with self.lock:
            await self._expire()
            telemetry: dict[str, object] = {"last_seen": self.clock()}
            for key in ("current_version", "orientation", "is_periodic_poll"):
                if value := request.query.get(key):
                    telemetry[key] = value[:64]
            for key in ("battery_pct", "battery_percentage", "battery_percent"):
                try:
                    percent = int(request.query[key])
                except (KeyError, ValueError):
                    continue
                if 0 <= percent <= 100:
                    telemetry["battery_percent"] = percent
            self.telemetry[device.id] = telemetry
            await asyncio.to_thread(self.store.telemetry, device.id, telemetry)
            body: dict[str, object] = {
                "has_new_upload": False, "presigned_url": None, "firmware": None,
                "next_image_utc": self._next_wake(device),
            }
            if device.settings is not None:
                body["device_settings"] = device.settings
            if device.email_verified is not None:
                body["account"] = {"email_verified": device.email_verified}
            if not self._busy(device):
                for job in reversed(list(self.jobs.values())):
                    if job.device == device.id and job.kind == "art" and job.state == "ready":
                        job.offered_at = self.clock()
                        # Polling can otherwise preempt recording before presign.
                        job.busy_until = self.clock() + 180
                        await self._save(job)
                        body.update(has_new_upload=True, presigned_url=self._asset_url(job))
                        break
            return response(body)

    def _next_wake(self, device: Device) -> int | None:
        wake = self.wakes.get(device.id)
        return wake if wake is not None and wake > self.clock() + 30 else None

    async def albums(self, request: web.Request) -> web.Response:
        device = self._device(request.match_info["key"])
        # HA owns the queue. This is its read-only projection for the stock UI.
        async with self.lock:
            await self._expire()
            images = [{"upload_id": j.id} for j in self.jobs.values()
                      if j.device == device.id and j.kind == "art" and j.state not in TERMINAL]
            return response({"albums": [{"id": f"ha-{device.id}", "name": "Home Assistant",
                             "active": True, "images": images[-1:], "image_count": int(bool(images)),
                             "next_image_utc": self._next_wake(device)}]})

    async def presign(self, request: web.Request) -> web.Response:
        body = await json_body(request)
        device = self._device(body["device_key"], body["user_id"])
        async with self.lock:
            await self._expire()
            if self._busy(device):
                raise web.HTTPConflict(reason="frame_busy")
            self._capacity(MAX_AUDIO + device.panel_size)
            now = self.clock()
            job = Job(secrets.token_hex(16), device.id, "voice", "uploading", now,
                      now + JOB_TTL, secrets.token_urlsafe(32), secrets.token_urlsafe(32))
            await self._save(job)
            self.jobs[job.id] = job
            return response({"url": f"{self.public_url}/audio/{job.upload_ticket}",
                             "key": job.id, "fields": {}})

    async def upload(self, request: web.Request) -> web.Response:
        # Buffer the bounded envelope before parsing so extra fields cannot evade limits.
        async with self.lock:
            job = self._ticket(request.match_info["ticket"], "upload")
        raw = await read_limited(request, MAX_AUDIO + 16384)
        stream = aiohttp.StreamReader(request._protocol, limit=len(raw) + 1)
        stream.feed_data(raw)
        stream.feed_eof()
        reader = aiohttp.MultipartReader(request.headers, stream)
        audio: bytes | None = None
        async for part in reader:
            if not isinstance(part, aiohttp.BodyPartReader) or part.name != "file" or audio is not None:
                raise ValueError("Expected exactly one file field")
            audio = bytes(await part.read(decode=False))
        if audio is None:
            raise ValueError("Missing audio")
        await asyncio.to_thread(validate_wav, audio)
        digest = hashlib.sha256(audio).hexdigest()
        async with self.lock:
            job = self._ticket(request.match_info["ticket"], "upload")
            if job.audio_hash is not None:
                if job.audio_hash != digest:
                    raise web.HTTPConflict(reason="audio_changed")
            elif job.state != "uploading":
                raise web.HTTPConflict(reason="invalid_job_state")
            else:
                job.audio, job.audio_hash, job.state = audio, digest, "uploaded"
                await self._save(job)
        # A positive response length makes the stock multipart worker fail.
        return web.Response(body=b"", headers={"Cache-Control": "no-store"})

    async def finalize(self, request: web.Request) -> web.Response:
        body = await json_body(request)
        device = self._device(body["device_key"], body["user_id"])
        orientation = body.get("orientation")
        if orientation not in ("portrait", "landscape"):
            raise ValueError("Invalid orientation")
        async with self.lock:
            await self._expire()
            job = self.jobs.get(str(body["key"]))
            if job is None or job.device != device.id or job.kind != "voice":
                raise web.HTTPNotFound()
            if job.state in TERMINAL:
                raise web.HTTPGone(reason=job.state)
            if job.state == "uploading":
                raise web.HTTPConflict(reason="audio_not_uploaded")
            if job.orientation is not None and job.orientation != orientation:
                raise web.HTTPConflict(reason="orientation_changed")
            job.orientation = orientation
            if job.state == "uploaded":
                job.state = "processing"
                await self._save(job)
                processing = asyncio.create_task(self._process(device, job))
                self.tasks[job.id] = processing
                processing.add_done_callback(lambda _: self.tasks.pop(job.id, None))
            task = self.tasks.get(job.id)
        if task is not None:
            # A disconnected waiter does not cancel a generation owner.
            await asyncio.shield(task)
        async with self.lock:
            if job.state not in {"ready", "transferring", "served"}:
                raise web.HTTPServiceUnavailable(reason=job.state)
            return response({"status": "completed", "presigned_url": self._asset_url(job)})

    async def _process(self, device: Device, job: Job) -> None:
        try:
            async with asyncio.timeout(max(0, min(480, job.expires - self.clock()))):
                asset = await self.process_voice(device, job)
                await asyncio.to_thread(validate_panel, asset, device)
            async with self.lock:
                if job.state != "processing" or job.expires <= self.clock():
                    return
                job.asset = asset
                job.content_hash = hashlib.sha256(asset).hexdigest()
                job.state, job.expires = "ready", self.clock() + ASSET_TTL
                job.busy_until = self.clock() + 180
                job.audio = b""
                await self._save(job)
        except asyncio.CancelledError:
            # Retain the same identity for reconciliation after listener restart.
            raise
        except Exception:
            async with self.lock:
                if job.state not in TERMINAL:
                    job.state, job.audio = "uncertain", b""
                    await self._save(job)

    async def _ha_voice(self, device: Device, job: Job) -> bytes:
        assert self.session is not None
        headers = {"Authorization": f"Bearer {device.bridge_token}",
                   "X-Fraimic-Job": job.id, "X-Fraimic-Orientation": job.orientation or "portrait",
                   "Content-Type": "audio/wav"}
        async with self.session.post(f"{origin(device.ha_url)}/api/fraimic/backend/voice",
                                     data=job.audio, headers=headers, allow_redirects=False) as reply:
            if reply.status != 200:
                raise ValueError("HA voice failed")
            data = await reply.content.readexactly(device.panel_size)
            if await reply.content.read(1):
                raise ValueError("Oversized panel")
            return data

    async def panel(self, request: web.Request) -> web.StreamResponse:
        async with self.lock:
            job = self._ticket(request.match_info["ticket"], "asset")
            if job.state not in {"ready", "served"} or not job.asset:
                raise web.HTTPConflict(reason="asset_not_ready")
            if job.attempts >= 4:
                raise web.HTTPGone(reason="retry_limit")
            device = self.devices[job.device]
            if self._busy(device, except_job=job.id):
                raise web.HTTPConflict(reason="frame_busy")
            job.state, job.attempts = "transferring", job.attempts + 1
            job.busy_until = self.clock() + 180
            await self._save(job)
            data = job.asset
        reply = web.StreamResponse(headers={"Content-Type": "application/octet-stream",
                                   "Content-Length": str(len(data)), "Cache-Control": "no-store"})
        complete = False
        try:
            async with asyncio.timeout(90):
                await reply.prepare(request)
                for start in range(0, len(data), 65536):
                    await reply.write(data[start:start + 65536])
                await reply.write_eof()
                complete = True
            return reply
        finally:
            async with self.lock:
                if job.state == "transferring":
                    job.state = "served" if complete else "ready"
                    if complete:
                        job.served_at = self.clock()
                        job.expires = min(job.expires, self.clock() + 180)
                    job.busy_until = self.clock() + device.settle
                    await self._save(job)

    async def state(self, request: web.Request) -> web.Response:
        device = self._bridge(request)
        async with self.lock:
            await self._expire()
            jobs = [j for j in self.jobs.values() if j.device == device.id]
            return response({"busy": self._busy(device), "next_image_utc": self._next_wake(device),
                             "device": self.telemetry.get(device.id, {}),
                             "jobs": [j.status() for j in jobs[-8:]]})

    async def schedule(self, request: web.Request) -> web.Response:
        device = self._bridge(request)
        body = await json_body(request)
        wake = body.get("next_image_utc")
        if wake is not None and (type(wake) is not int or not self.clock() + 30 < wake < self.clock() + 366 * 86400):
            raise ValueError("Wake must be a future whole-second UTC epoch")
        async with self.lock:
            await asyncio.to_thread(self.store.wake, device.id, wake)
            self.wakes[device.id] = wake
        return response({"next_image_utc": wake})

    async def delivery(self, request: web.Request) -> web.Response:
        device = self._bridge(request)
        expiry = int(request.headers.get("X-Fraimic-Expires", int(self.clock() + ART_TTL)))
        if not self.clock() + device.settle < expiry <= self.clock() + ART_TTL:
            raise ValueError("Image must remain valid through delivery and render")
        ident = request.headers.get("X-Fraimic-Job", "")
        if len(ident) != 32 or any(c not in "0123456789abcdef" for c in ident):
            raise ValueError("Invalid delivery identity")
        data = await read_limited(request, MAX_PANEL)
        await asyncio.to_thread(validate_panel, data, device)
        digest = hashlib.sha256(data).hexdigest()
        async with self.lock:
            await self._expire()
            existing = self.jobs.get(ident)
            if existing is not None:
                if existing.device != device.id or existing.kind != "art" or existing.content_hash != digest:
                    raise web.HTTPConflict(reason="delivery_changed")
                if existing.state in TERMINAL:
                    raise web.HTTPGone()
                return response(existing.status())
            if self._busy(device):
                raise web.HTTPConflict(reason="frame_busy")
            for job in self.jobs.values():
                if job.device == device.id and job.kind == "art" and job.state == "ready":
                    job.state, job.asset = "cancelled", b""
                    await self._save(job)
            self._capacity(len(data))
            now = self.clock()
            job = Job(ident, device.id, "art", "ready", now, expiry,
                      asset_ticket=secrets.token_urlsafe(32), content_hash=digest, asset=data)
            await self._save(job)
            self.jobs[ident] = job
            return response(job.status())

    async def cancel(self, request: web.Request) -> web.Response:
        device = self._bridge(request)
        body = await json_body(request)
        async with self.lock:
            job = self.jobs.get(str(body.get("job_id")))
            if job is None or job.device != device.id:
                raise web.HTTPNotFound()
            if job.state == "transferring":
                raise web.HTTPConflict(reason="transfer_in_progress")
            job.state, job.audio, job.asset = "cancelled", b"", b""
            await self._save(job)
        return response(job.status())


def bridge_routes(backend: Backend) -> list[web.RouteDef]:
    return [
        web.get("/bridge/state", backend.state, allow_head=False),
        web.put("/bridge/schedule", backend.schedule),
        web.post("/bridge/delivery", backend.delivery),
        web.post("/bridge/cancel", backend.cancel),
    ]


def create_bridge_app(backend: Backend) -> web.Application:
    """Private HA listener sharing the device listener's managed backend."""
    app = web.Application(middlewares=[errors], client_max_size=MAX_PANEL)
    app.add_routes(bridge_routes(backend))
    return app


def create_app(backend: Backend, *, include_bridge: bool = False) -> web.Application:
    app = web.Application(middlewares=[errors], client_max_size=MAX_PANEL)

    async def lifecycle(app: web.Application) -> AsyncIterator[None]:
        await backend.setup()

        async def expire() -> None:
            while True:
                await asyncio.sleep(30)
                try:
                    async with backend.lock:
                        await backend._expire()
                except Exception:
                    # Retry transient storage errors without logging private paths.
                    _LOGGER.error("Job cleanup failed; retrying on the next tick")

        cleanup = asyncio.create_task(expire())
        yield
        cleanup.cancel()
        await asyncio.gather(cleanup, return_exceptions=True)
        await backend.close()

    app.cleanup_ctx.append(lifecycle)
    app.add_routes([
        web.get("/api/v1/upload/check/{key}", backend.poll, allow_head=False),
        web.get("/api/v1/albums/{key}", backend.albums, allow_head=False),
        web.post("/api/v1/upload/audio/presign", backend.presign),
        web.post("/api/v1/upload/audio/finalize", backend.finalize),
        web.post("/audio/{ticket}", backend.upload),
        web.get("/panel/{ticket}", backend.panel, allow_head=False),
    ])
    if include_bridge:
        app.add_routes(bridge_routes(backend))
    return app
