"""Bounded, private transport records and the stock wire contract."""

from __future__ import annotations

import io
import re
import wave
from dataclasses import dataclass, field
from urllib.parse import urlsplit

MAX_AUDIO = 2_128_192
MAX_PANEL = 2_304_000
MAX_JSON = 4095
JOB_TTL = 600
ASSET_TTL = 3600
ART_TTL = 7 * 86400
MAX_JOBS = 8
MAX_PANEL_ATTEMPTS = 4
MAX_STORAGE = 64 * 1024 * 1024
TERMINAL = {"failed", "uncertain", "cancelled", "expired"}
SETTINGS = {
    "voiceRecordingEnabled", "keepAwakeEnabled",
    "autoUpdateEnabled", "chargingLedEnabled",
}


def origin(value: str, *, https: bool = False) -> str:
    """Accept an explicitly configured origin, never a caller-supplied URL."""
    parsed = urlsplit(value)
    if (parsed.scheme not in ({"https"} if https else {"http", "https"})
        or not parsed.hostname or parsed.username or parsed.password
        or parsed.path not in ("", "/") or parsed.query or parsed.fragment
        or len(value) > 512):
        raise ValueError("Expected an HTTP(S) origin without credentials or a path")
    return value.rstrip("/")


@dataclass(frozen=True)
class Device:
    id: str
    device_key: str = field(repr=False)
    user_id: str = field(repr=False)
    bridge_token: str = field(repr=False)
    ha_url: str
    display_type: str
    settings: dict[str, bool] | None = None
    email_verified: bool | None = None

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", self.id):
            raise ValueError("Invalid device ID")
        if (not self.device_key or not self.user_id or len(self.bridge_token) < 32
            or self.bridge_token in (self.device_key, self.user_id)):
            raise ValueError("Each frame needs identity and a separate strong bridge token")
        if self.display_type not in ("133", "315"):
            raise ValueError("Only Standard 133 and Large 315 panels are supported")
        origin(self.ha_url)
        if self.settings is not None and (
            set(self.settings) != SETTINGS
            or any(type(v) is not bool for v in self.settings.values())
        ):
            raise ValueError("Device settings must be a complete four-boolean snapshot")
        if self.email_verified is not None and type(self.email_verified) is not bool:
            raise ValueError("email_verified must be boolean or absent")

    @property
    def panel_size(self) -> int:
        return MAX_PANEL if self.display_type == "315" else 960_000

    @property
    def settle(self) -> int:
        return 90 if self.display_type == "315" else 60


def validate_panel(data: bytes, device: Device) -> None:
    if len(data) != device.panel_size:
        raise ValueError("Wrong panel buffer size")
    if any((b >> 4) not in (0, 1, 2, 3, 5, 6) or (b & 15) not in (0, 1, 2, 3, 5, 6) for b in data):
        raise ValueError("Invalid panel palette index")


def validate_wav(data: bytes) -> None:
    """Validate the entire RIFF container and PCM sample count, not just a header."""
    if (len(data) > MAX_AUDIO or len(data) < 44 or data[:4] != b"RIFF"
        or int.from_bytes(data[4:8], "little") + 8 != len(data)):
        raise ValueError("Invalid or oversized WAV")
    offset, data_chunks = 12, 0
    while offset < len(data):
        if offset + 8 > len(data):
            raise ValueError("Truncated WAV chunk")
        size = int.from_bytes(data[offset + 4:offset + 8], "little")
        if data[offset:offset + 4] == b"data":
            data_chunks += 1
            if size % 2:
                raise ValueError("Unaligned PCM data")
        offset += 8 + size + size % 2
        if offset > len(data):
            raise ValueError("Truncated WAV chunk")
    if data_chunks != 1:
        raise ValueError("Expected one PCM data chunk")
    try:
        with wave.open(io.BytesIO(data)) as wav:
            if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getcomptype()) != (1, 2, 16000, "NONE"):
                raise ValueError("Expected mono 16-bit 16 kHz PCM")
            count = wav.getnframes()
            if not 0 < count <= 16000 * 66 or len(wav.readframes(count)) != count * 2:
                raise ValueError("Truncated or oversized PCM")
    except (wave.Error, EOFError) as err:
        raise ValueError("Invalid WAV") from err


@dataclass
class Job:
    id: str
    device: str
    kind: str
    state: str
    created: float
    expires: float
    upload_ticket: str = field(default="", repr=False)
    asset_ticket: str = field(default="", repr=False)
    orientation: str | None = None
    audio_hash: str | None = None
    content_hash: str | None = None
    offered_at: float | None = None
    served_at: float | None = None
    busy_until: float = 0
    attempts: int = 0
    audio: bytes = field(default=b"", repr=False)
    asset: bytes = field(default=b"", repr=False)

    def busy(self, now: float) -> bool:
        return self.busy_until > now or (
            self.kind == "voice" and self.state in {"uploading", "uploaded", "processing"}
            and self.expires > now
        )

    def status(self) -> dict[str, object]:
        return {"job_id": self.id, "kind": self.kind, "state": self.state,
                "created_at": self.created, "expires_at": self.expires,
                "served_at": self.served_at, "confirmed_on_panel": False,
                "busy_until": self.busy_until, "content_hash": self.content_hash}
