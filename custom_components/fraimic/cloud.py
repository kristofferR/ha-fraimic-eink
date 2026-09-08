"""Client for the Fraimic cloud account API (``origin.fraimic.com``).

Verified live on 2026-09-07 (see ``docs/fraimic-cloud-api/albums-scheduling.md``).
The account is a Supabase email/password login; the API takes the resulting
JWT as a bearer token. No Home Assistant imports here so the pure helpers stay
unit-testable.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from typing import Any
from urllib.parse import urlencode

import aiohttp

from .const import (
    CLOUD_API_BASE,
    CLOUD_AUTH_ANON_KEY,
    CLOUD_AUTH_BASE,
    CLOUD_SLOT_LEAD_MINUTES,
)

_LOGGER = logging.getLogger(__name__)

# Seconds; wrapped in ``aiohttp.ClientTimeout`` per request so importing this
# module never touches aiohttp (tests stub it).
TIMEOUT = 30
UPLOAD_TIMEOUT = 120
# Refresh the access token this many seconds before Supabase expires it.
TOKEN_REFRESH_MARGIN = 120


class FraimicCloudError(Exception):
    """The cloud API failed or could not be reached.

    ``status`` carries the HTTP status when the cloud answered at all.
    """

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class FraimicCloudAuthError(FraimicCloudError):
    """The account credentials were rejected."""


def password_variants(password: str) -> tuple[str, ...]:
    """Passwords to try, in order.

    The Fraimic web app first submits the password form-encoded (a
    ``URLSearchParams`` quirk) and only then the raw string, so accounts may
    have been created with either spelling. Try raw first; the encoded form
    only differs when the password contains characters that need escaping.
    """
    encoded = urlencode({"p": password})[2:]
    return (password,) if encoded == password else (password, encoded)


def album_interval_minutes(playlist_interval: int) -> int:
    """Album interval for a playlist rotating every ``playlist_interval`` s.

    Album slots fire at ``last edit + interval``. Home Assistant edits the
    album once per rotation, so adding a lead makes the frame wake a few
    minutes *after* each upload and always fetch the fresh image.
    """
    return max(1, math.ceil(playlist_interval / 60)) + CLOUD_SLOT_LEAD_MINUTES


def album_schedule(playlist_interval: int) -> dict[str, Any]:
    minutes = album_interval_minutes(playlist_interval)
    if minutes % 1440 == 0:
        return {"type": "interval", "interval_value": minutes // 1440, "interval_unit": "days"}
    if minutes % 60 == 0:
        return {"type": "interval", "interval_value": minutes // 60, "interval_unit": "hours"}
    return {"type": "interval", "interval_value": minutes, "interval_unit": "minutes"}


def device_settings_payload(settings: dict[str, Any], *, keep_awake: bool) -> dict[str, Any]:
    """Full settings body: the endpoint replaces, so send every key."""
    return {
        "voiceRecordingEnabled": bool(settings.get("voiceRecordingEnabled", True)),
        "keepAwakeEnabled": keep_awake,
        "chargingLedEnabled": bool(settings.get("chargingLedEnabled", True)),
        "style": settings.get("style") or "NONE",
    }


class FraimicCloudClient:
    """Authenticated access to one Fraimic account."""

    def __init__(self, session: aiohttp.ClientSession, email: str, password: str) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._expires_at = 0.0
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------ auth

    async def async_login(self) -> None:
        """Password grant. Raises ``FraimicCloudAuthError`` on bad credentials."""
        last_error: Exception | None = None
        for candidate in password_variants(self._password):
            try:
                data = await self._auth_request(
                    "password", {"email": self._email, "password": candidate}
                )
            except FraimicCloudAuthError as err:
                last_error = err
                continue
            self._store_session(data)
            return
        raise last_error or FraimicCloudAuthError("Login failed")

    async def _auth_request(self, grant: str, body: dict[str, Any]) -> dict[str, Any]:
        headers = {"apikey": CLOUD_AUTH_ANON_KEY, "Content-Type": "application/json"}
        try:
            async with self._session.post(
                f"{CLOUD_AUTH_BASE}/token?grant_type={grant}",
                json=body,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=TIMEOUT),
            ) as resp:
                try:
                    data = await resp.json(content_type=None)
                except ValueError as err:
                    raise FraimicCloudError(
                        f"Auth response was not JSON (HTTP {resp.status})",
                        status=resp.status,
                    ) from err
                if resp.status == 400 or resp.status in (401, 403):
                    raise FraimicCloudAuthError(
                        str((data or {}).get("msg") or (data or {}).get("error_code") or resp.status)
                    )
                if resp.status >= 400:
                    raise FraimicCloudError(
                        f"Auth request failed: HTTP {resp.status}", status=resp.status
                    )
        except aiohttp.ClientError as err:
            raise FraimicCloudError(f"Cannot reach the Fraimic login service: {err}") from err
        except asyncio.TimeoutError as err:
            raise FraimicCloudError("Timed out reaching the Fraimic login service") from err
        if not isinstance(data, dict) or not data.get("access_token"):
            raise FraimicCloudError("Login response had no access token")
        return data

    def _store_session(self, data: dict[str, Any]) -> None:
        self._access_token = data["access_token"]
        self._refresh_token = data.get("refresh_token")
        expires_in = data.get("expires_in")
        self._expires_at = time.time() + (
            float(expires_in) if isinstance(expires_in, (int, float)) else 3600
        )

    async def _async_token(self) -> str:
        async with self._lock:
            if self._access_token and time.time() < self._expires_at - TOKEN_REFRESH_MARGIN:
                return self._access_token
            if self._refresh_token:
                try:
                    data = await self._auth_request(
                        "refresh_token", {"refresh_token": self._refresh_token}
                    )
                except FraimicCloudError as err:
                    _LOGGER.debug("Cloud token refresh failed, logging in again: %s", err)
                else:
                    self._store_session(data)
                    return self._access_token  # type: ignore[return-value]
            await self.async_login()
            return self._access_token  # type: ignore[return-value]

    # ------------------------------------------------------------ requests

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
        retry_auth: bool = True,
    ) -> Any:
        token = await self._async_token()
        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with self._session.request(
                method,
                f"{CLOUD_API_BASE}{path}",
                json=json,
                params=params,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=TIMEOUT),
            ) as resp:
                if resp.status == 401 and retry_auth:
                    # Token revoked server-side; log in again once.
                    self._access_token = None
                    self._refresh_token = None
                    return await self._request(
                        method, path, json=json, params=params, retry_auth=False
                    )
                if resp.status >= 400:
                    text = (await resp.text())[:300]
                    raise FraimicCloudError(
                        f"{method} {path} failed: HTTP {resp.status} {text}",
                        status=resp.status,
                    )
                if resp.status == 204:
                    return None
                try:
                    return await resp.json(content_type=None)
                except ValueError as err:
                    raise FraimicCloudError(
                        f"{method} {path} returned a non-JSON body", status=resp.status
                    ) from err
        except aiohttp.ClientError as err:
            raise FraimicCloudError(f"Cannot reach the Fraimic cloud: {err}") from err
        except asyncio.TimeoutError as err:
            raise FraimicCloudError("Timed out talking to the Fraimic cloud") from err

    # ------------------------------------------------------------ devices

    async def async_devices(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/api/v1/account/devices")
        devices = data.get("devices") if isinstance(data, dict) else None
        return devices if isinstance(devices, list) else []

    async def async_device(self, device_id: str) -> dict[str, Any] | None:
        for device in await self.async_devices():
            if device.get("device_id") == device_id:
                return device
        return None

    async def async_set_keep_awake(self, device_id: str, keep_awake: bool) -> None:
        """Flip keep-awake; the frame applies it on its next cloud poll."""
        device = await self.async_device(device_id)
        if device is None:
            raise FraimicCloudError(f"Device {device_id} is not on this account")
        current = device.get("pending_settings") or device.get("settings") or {}
        await self._request(
            "POST",
            "/api/v1/account/settings",
            json={
                "device_id": device_id,
                "settings": device_settings_payload(current, keep_awake=keep_awake),
            },
        )

    # ------------------------------------------------------------ uploads

    async def async_upload_png(self, png: bytes) -> str:
        """Upload a PNG to the account gallery; returns its ``upload_id``.

        ``mark_for_check_for_upload=false`` keeps it out of the frame's
        "new upload" push so only the album schedule shows it.
        """
        presign = await self._request(
            "POST",
            "/api/v1/upload/image/presign",
            params={"content_type": "image/png", "mark_for_check_for_upload": "false"},
        )
        if not isinstance(presign, dict) or not presign.get("upload_id"):
            raise FraimicCloudError("Presign response had no upload_id")
        form = aiohttp.FormData()
        for key, value in (presign.get("fields") or {}).items():
            form.add_field(key, str(value))
        form.add_field("file", png, filename="image.png", content_type="image/png")
        try:
            async with self._session.post(
                presign["url"], data=form, timeout=aiohttp.ClientTimeout(total=UPLOAD_TIMEOUT)
            ) as resp:
                if resp.status not in (200, 201, 204):
                    raise FraimicCloudError(
                        f"S3 upload failed: HTTP {resp.status} {(await resp.text())[:200]}"
                    )
        except aiohttp.ClientError as err:
            raise FraimicCloudError(f"S3 upload failed: {err}") from err
        except asyncio.TimeoutError as err:
            raise FraimicCloudError("S3 upload timed out") from err
        return str(presign["upload_id"])

    async def async_delete_uploads(self, upload_ids: list[str]) -> None:
        if not upload_ids:
            return
        await self._request(
            "DELETE", "/api/v1/upload/images", json={"upload_public_ids": upload_ids}
        )

    # ------------------------------------------------------------ albums

    async def async_albums(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/api/v1/albums")
        albums = data.get("albums") if isinstance(data, dict) else None
        return albums if isinstance(albums, list) else []

    async def async_create_album(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = await self._request("POST", "/api/v1/albums", json=payload)
        if not isinstance(data, dict) or not data.get("id"):
            raise FraimicCloudError("Album creation returned no id")
        return data

    async def async_update_album(self, album_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Partial update. Any edit re-anchors the album's slot timetable."""
        data = await self._request("PUT", f"/api/v1/albums/{album_id}", json=payload)
        return data if isinstance(data, dict) else {}

    async def async_delete_album(self, album_id: str) -> None:
        await self._request("DELETE", f"/api/v1/albums/{album_id}")
