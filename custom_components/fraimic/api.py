"""Lightweight async client for the Fraimic E-Ink Canvas REST API.

The frame exposes an unauthenticated HTTP API on the local network. See the
official "Fraimic REST API Guide" (firmware v0.2.16) for the full contract.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

from .const import DEFAULT_TIMEOUT, MAX_BIN_SIZE, UPLOAD_TIMEOUT

_LOGGER = logging.getLogger(__name__)


class FraimicError(Exception):
    """Base error for the Fraimic API."""


class FraimicConnectionError(FraimicError):
    """Raised when the frame cannot be reached.

    This is the normal state while the frame is in deep sleep — it is then
    completely unreachable on the network until tapped awake.
    """


class FraimicApiError(FraimicError):
    """Raised when the frame returns an error response.

    Attributes:
        status: HTTP status code.
        error: The ``error`` field from the JSON body, if any.
    """

    def __init__(self, message: str, *, status: int | None = None, error: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.error = error


# First firmware verified (on real hardware) to accept POST /api/image with an
# application/octet-stream body. Older firmware (0.2.21) answered 501 and hung.
MIN_API_IMAGE_FIRMWARE = (0, 2, 28)


def parse_firmware(version: Any) -> tuple[int, ...] | None:
    """Parse a firmware string like ``0.2.28`` / ``v0.2.28`` into an int tuple."""
    if not isinstance(version, str):
        return None
    parts = version.strip().lstrip("vV").split(".")
    try:
        return tuple(int(p) for p in parts)
    except ValueError:
        return None


def firmware_supports_api_image(version: Any) -> bool:
    """True when this firmware's ``POST /api/image`` is safe to use.

    Verified on real hardware: 0.2.28 accepts an octet-stream body and returns
    structured errors; 0.2.21 answered 501 and wedged the HTTP server. Unknown
    or unparsable versions stay on the multipart ``/upload`` path, which works
    on every firmware seen so far.
    """
    parsed = parse_firmware(version)
    return parsed is not None and parsed >= MIN_API_IMAGE_FIRMWARE


def normalize_host(host: str) -> str:
    """Return a bare host (no scheme, no trailing slash) from user input."""
    host = host.strip()
    for prefix in ("http://", "https://"):
        if host.lower().startswith(prefix):
            host = host[len(prefix) :]
            break
    return host.strip("/")


class FraimicClient:
    """Talks to a single Fraimic frame."""

    def __init__(self, host: str, session: aiohttp.ClientSession) -> None:
        self._host = normalize_host(host)
        # Uploads go to POST /api/image (octet-stream) when the coordinator has
        # confirmed a firmware that supports it, else multipart /upload. False
        # until the first successful poll (e.g. frame asleep at startup).
        self.prefer_api_image = False
        self._session = session
        # Bracket bare IPv6 literals (2+ colons, not already bracketed) so the URL
        # is valid; a normal "host" or "host:port" is left untouched.
        url_host = self._host
        if url_host.count(":") >= 2 and not url_host.startswith("["):
            url_host = f"[{url_host}]"
        self._base = f"http://{url_host}"

    @property
    def host(self) -> str:
        """Return the normalized host."""
        return self._host

    async def _request(self, method: str, path: str, **kwargs: Any) -> aiohttp.ClientResponse:
        url = f"{self._base}{path}"
        timeout = aiohttp.ClientTimeout(total=kwargs.pop("timeout", DEFAULT_TIMEOUT))
        try:
            return await self._session.request(method, url, timeout=timeout, **kwargs)
        except (aiohttp.ClientConnectionError, asyncio.TimeoutError) as err:
            raise FraimicConnectionError(f"Cannot reach Fraimic at {self._host}: {err}") from err
        except aiohttp.ClientError as err:
            raise FraimicError(f"Unexpected error talking to {self._host}: {err}") from err

    async def _json(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        resp = await self._request(method, path, **kwargs)
        async with resp:
            try:
                data = await resp.json(content_type=None)
            except (aiohttp.ClientError, ValueError):
                data = None
            if resp.status >= 400:
                error = data.get("error") if isinstance(data, dict) else None
                raise FraimicApiError(
                    f"{method} {path} returned HTTP {resp.status}"
                    + (f" ({error})" if error else ""),
                    status=resp.status,
                    error=error,
                )
            if not isinstance(data, dict):
                raise FraimicError(f"{method} {path} returned a non-JSON body")
            return data

    async def get_info(self) -> dict[str, Any]:
        """Return the full device snapshot from ``GET /api/info``."""
        return await self._json("GET", "/api/info")

    async def get_battery(self) -> dict[str, Any]:
        """Return the lightweight battery status from ``GET /api/battery``."""
        return await self._json("GET", "/api/battery")

    async def restart(self) -> dict[str, Any]:
        """Reboot the frame (``POST /api/restart``)."""
        return await self._json("POST", "/api/restart")

    async def sleep(self) -> dict[str, Any]:
        """Put the frame into deep sleep (``POST /api/sleep``).

        Blocked while a charging cable is connected; the frame then responds
        with ``{"error": "charging_cable_connected"}``.
        """
        return await self._json("POST", "/api/sleep")

    async def refresh(self) -> dict[str, Any]:
        """Trigger a full E-Ink refresh cycle (``POST /api/refresh``)."""
        return await self._json("POST", "/api/refresh")

    async def upload_image(
        self, data: bytes, *, refresh: bool = False, recover: bool = True
    ) -> None:
        """Upload a raw Spectra 6 ``.bin`` image and render it.

        Two firmware-dependent wire paths (both verified on real hardware):

        - Firmware >= 0.2.28 (``prefer_api_image``): ``POST /api/image`` with a
          raw ``application/octet-stream`` body. Returns
          ``{"status": "rendering", "bytes_received": N}`` in ~10 s and gives
          structured errors (``invalid_image_size``, ``unsupported_content_type``).
        - Otherwise: ``POST /upload`` with a ``multipart/form-data`` ``image``
          field — the path the frame's own portal uses, works on every firmware
          seen so far. On firmware 0.2.21, ``/api/image`` instead returned 501
          and hung the device, hence the version gate.

        Either way a successful upload renders the image by itself (~20-30 s),
        so no follow-up ``/api/refresh`` is needed — firing one mid-render just
        gets the connection reset by the busy ESP32. ``refresh`` stays available
        for firmwares that need the explicit kick.

        ``recover`` handles a firmware bug seen repeatedly on real hardware:
        after an aborted/interrupted upload the frame's upload handler wedges —
        upload connections get reset while the rest of the API still answers.
        A device restart clears it, so on a connection-level upload failure we
        restart the frame, wait for it to come back, and retry once.
        """
        if len(data) > MAX_BIN_SIZE:
            raise FraimicError(
                f"Image is {len(data)} bytes; the frame rejects uploads over "
                f"{MAX_BIN_SIZE} bytes"
            )

        attempt = self._do_upload_api_image if self.prefer_api_image else self._do_upload
        try:
            await attempt(data)
        except FraimicConnectionError:
            if not recover:
                raise
            # The wedge only affects uploads; if the whole frame is down (deep
            # sleep), the restart below fails the same way and we re-raise.
            _LOGGER.warning(
                "Upload to %s failed at the connection level — the frame's "
                "upload handler may be wedged; restarting the frame and "
                "retrying once",
                self._host,
            )
            await self.restart()
            await self._wait_reachable()
            await attempt(data)

        if refresh:
            # A refresh failure is non-fatal (the image is already buffered), but
            # surface it so a silently-not-updating frame is diagnosable.
            try:
                await self.refresh()
            except FraimicError as err:
                _LOGGER.warning("Image uploaded but display refresh failed: %s", err)

    async def _do_upload_api_image(self, data: bytes) -> None:
        """One ``POST /api/image`` attempt (firmware >= 0.2.28).

        The body must be raw bytes with ``Content-Type: application/octet-stream``
        — anything else (including multipart) gets a 501 ``unsupported_content_type``
        and, for large bodies, briefly wedges the frame's HTTP server because the
        firmware rejects without draining the request.
        """
        resp = await self._request(
            "POST",
            "/api/image",
            data=data,
            headers={"Content-Type": "application/octet-stream"},
            timeout=UPLOAD_TIMEOUT,
        )
        async with resp:
            try:
                body = await resp.json(content_type=None)
            except (aiohttp.ClientError, ValueError):
                body = None
            if resp.status >= 400:
                error = body.get("error") if isinstance(body, dict) else None
                raise FraimicApiError(
                    f"Upload failed with HTTP {resp.status}"
                    + (f" ({error})" if error else ""),
                    status=resp.status,
                    error=error,
                )

    async def _do_upload(self, data: bytes) -> None:
        """One ``POST /upload`` attempt."""
        form = aiohttp.FormData()
        form.add_field(
            "image", data, filename="image.bin", content_type="application/octet-stream"
        )
        resp = await self._request("POST", "/upload", data=form, timeout=UPLOAD_TIMEOUT)
        async with resp:
            if resp.status >= 400:
                body = await resp.text()
                raise FraimicApiError(
                    f"Upload failed with HTTP {resp.status}: {body[:200]}",
                    status=resp.status,
                )

    async def _wait_reachable(self, *, attempts: int = 12, delay: float = 5.0) -> None:
        """Poll the lightweight battery endpoint until the frame answers."""
        for _ in range(attempts):
            await asyncio.sleep(delay)
            try:
                await self.get_battery()
            except FraimicError:
                continue
            return
        raise FraimicConnectionError(
            f"Fraimic at {self._host} did not come back after a restart"
        )
