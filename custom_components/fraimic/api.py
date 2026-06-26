"""Lightweight async client for the Fraimic E-Ink Canvas REST API.

The frame exposes an unauthenticated HTTP API on the local network. See the
official "Fraimic REST API Guide" (firmware v0.2.16) for the full contract.
"""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp

from .const import DEFAULT_TIMEOUT, MAX_BIN_SIZE, UPLOAD_TIMEOUT


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
        self._session = session
        self._base = f"http://{self._host}"

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

    async def upload_image(self, data: bytes, *, refresh: bool = True) -> None:
        """Upload a raw Spectra 6 ``.bin`` image and render it.

        Uses ``POST /upload`` with a ``multipart/form-data`` ``image`` field,
        then triggers ``/api/refresh``. This is the path the frame's own portal
        uses. Do NOT use ``POST /api/image`` with an octet-stream body — on real
        frames it returns 501 and hangs the device for 45+ seconds.
        """
        if len(data) > MAX_BIN_SIZE:
            raise FraimicError(
                f"Image is {len(data)} bytes; the frame rejects uploads over "
                f"{MAX_BIN_SIZE} bytes"
            )

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

        if refresh:
            # A refresh failure is non-fatal; the image is already buffered.
            try:
                await self.refresh()
            except FraimicError:
                pass
