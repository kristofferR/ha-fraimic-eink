# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Check for Fraimic firmware and archive the offered app without installing it.

Run with ``uv run scripts/download_firmware.py --help``. Protocol and usage:
docs/firmware/downloader.md. This script has no Home Assistant dependencies.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import http.client
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

API_BASE = "https://origin.fraimic.com"
DISPLAY_TYPES = {"standard": "133", "large": "315"}
MAX_POLL_BYTES = 1024 * 1024
MAX_FIRMWARE_BYTES = 32 * 1024 * 1024


class DownloadError(Exception):
    """A failure whose message is safe to print without credentials or URLs."""


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # The stock direct updater requires 200. Also keep the key-bearing poll
        # path from being forwarded to another origin by an API redirect.
        return None


def validate_url(url: str) -> None:
    """Require verified HTTPS; permit loopback HTTP for local protocol fixtures."""
    try:
        parts = urlsplit(url)
        loopback = parts.hostname in {"localhost", "127.0.0.1", "::1"}
        valid = (
            bool(parts.hostname)
            and (parts.scheme == "https" or (parts.scheme == "http" and loopback))
            and parts.username is None
            and parts.password is None
            and not parts.fragment
            and not any(ord(char) < 33 or ord(char) == 127 for char in url)
        )
        _ = parts.port
    except ValueError:
        valid = False
    if not valid:
        raise DownloadError(
            "Invalid URL: HTTPS is required (HTTP is allowed only on loopback)."
        )


def get(url: str, *, timeout: int, stage: str) -> http.client.HTTPResponse:
    validate_url(url)
    request = Request(url, headers={"User-Agent": "fraimic-firmware-downloader/1.0"})
    try:
        response: http.client.HTTPResponse = build_opener(NoRedirects()).open(
            request, timeout=timeout
        )
        if response.status != 200:
            response.close()
            raise DownloadError(
                f"{stage}: expected HTTP 200, received {response.status}."
            )
        return response
    except HTTPError as error:
        status = error.code
        error.close()
        raise DownloadError(
            f"{stage}: HTTP {status}; no redirect or retry was attempted."
        ) from None
    except (URLError, OSError, http.client.HTTPException, ValueError):
        # urllib errors can contain the device key, signed URL or response body.
        raise DownloadError(
            f"{stage}: connection, TLS, timeout or incomplete response error."
        ) from None


def read_response(
    response: http.client.HTTPResponse, size: int, *, stage: str
) -> bytes:
    try:
        return response.read(size)
    except (OSError, http.client.HTTPException, ValueError):
        raise DownloadError(f"{stage}: timeout or interrupted response.") from None


def read_device_key(path: Path | None) -> str:
    key = (
        path.read_text(encoding="utf-8").strip()
        if path
        else os.environ.get("FRAIMIC_DEVICE_KEY", "").strip()
    )
    if (
        not key
        or "..." in key
        or "…" in key
        or any(not 33 <= ord(c) <= 126 for c in key)
    ):
        raise DownloadError(
            "Supply the full provisioned key with --device-key-file or FRAIMIC_DEVICE_KEY; "
            "a masked key or account device ID cannot be used."
        )
    return key


def check_firmware(args: argparse.Namespace, key: str) -> tuple[str, str] | None:
    base = args.api_base_url.rstrip("/")
    validate_url(base)
    if urlsplit(base).query or urlsplit(base).path not in {"", "/"}:
        raise DownloadError("--api-base-url must be an origin without a path or query.")
    query = {
        "display_type": DISPLAY_TYPES[args.model],
        "orientation": args.orientation,
        "is_periodic_poll": "false",
        "current_version": args.current_version,
    }
    for name in ("battery_pct", "wifi_ssid", "ip"):
        value = getattr(args, name)
        if value is not None:
            query[name] = str(value)
    check_url = f"{base}/api/v1/upload/check/{quote(key, safe='')}?{urlencode(query, quote_via=quote)}"
    with get(check_url, timeout=10, stage="Firmware check") as response:
        raw = read_response(response, MAX_POLL_BYTES + 1, stage="Firmware check")
    if len(raw) > MAX_POLL_BYTES:
        raise DownloadError("Firmware check: response exceeds 1 MiB.")
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeError):
        raise DownloadError("Firmware check: invalid JSON response.") from None
    if not isinstance(payload, dict):
        raise DownloadError("Firmware check: expected a JSON object.")
    firmware = payload.get("firmware")
    if firmware is None:
        return None
    if not isinstance(firmware, dict):
        raise DownloadError("Firmware check: invalid firmware offer.")
    version, url = firmware.get("version"), firmware.get("presigned_url")
    if not isinstance(version, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._+-]{0,95}", version
    ):
        raise DownloadError("Firmware check: missing or unsafe firmware version.")
    if not isinstance(url, str) or not url:
        raise DownloadError("Firmware check: missing firmware download URL.")
    validate_url(url)
    return version, url


def download_firmware(args: argparse.Namespace, version: str, url: str) -> Path | None:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    # Publish the binary and metadata together, only after a complete download.
    # A failed or interrupted transfer leaves no apparently finished archive.
    with tempfile.TemporaryDirectory(
        prefix=".download-", dir=args.output_dir
    ) as temporary:
        staging = Path(temporary)
        digest = hashlib.sha256()
        size = 0
        header = bytearray()
        with get(url, timeout=30, stage="Firmware download") as response:
            length = response.headers.get("Content-Length", "")
            if (
                not re.fullmatch(r"[0-9]{1,10}", length)
                or not 24 <= int(length) <= MAX_FIRMWARE_BYTES
            ):
                raise DownloadError(
                    "Firmware download: require Content-Length between 24 bytes and 32 MiB."
                )
            if (
                response.headers.get("Transfer-Encoding")
                or response.headers.get("Content-Encoding", "identity").lower()
                != "identity"
            ):
                raise DownloadError(
                    "Firmware download: chunked or encoded responses are unsupported."
                )
            with (staging / "firmware.bin").open("xb") as output:
                while chunk := read_response(response, 4096, stage="Firmware download"):
                    size += len(chunk)
                    if size > int(length):
                        raise DownloadError(
                            "Firmware download: body exceeds Content-Length."
                        )
                    if len(header) < 24:
                        header.extend(chunk[: 24 - len(header)])
                    digest.update(chunk)
                    output.write(chunk)
        if size != int(length):
            raise DownloadError(
                "Firmware download: incomplete body (Content-Length mismatch)."
            )
        # This is a format sanity check, not the bootloader's image validation.
        if (
            header[0] != 0xE9
            or not 1 <= header[1] <= 16
            or int.from_bytes(header[12:14], "little") != 9
        ):
            raise DownloadError("Firmware download: not an ESP32-S3 application image.")
        sha256 = digest.hexdigest()
        if args.sha256 and not hmac.compare_digest(sha256, args.sha256.lower()):
            raise DownloadError("Firmware download: SHA-256 does not match --sha256.")
        metadata = {
            "downloaded_at": datetime.now(UTC).isoformat(),
            "api_origin": args.api_base_url.rstrip("/"),
            "model": args.model,
            "display_type": DISPLAY_TYPES[args.model],
            "current_version_sent": args.current_version,
            "offered_version": version,
            "bytes": size,
            "sha256": sha256,
            "file": "firmware.bin",
        }
        (staging / "metadata.json").write_text(
            json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
        )
        destination = args.output_dir / f"fraimic-{args.model}-{version}-{sha256[:12]}"
        if destination.exists():
            try:
                saved = json.loads((destination / "metadata.json").read_text())
                with (destination / "firmware.bin").open("rb") as existing:
                    saved_hash = hashlib.file_digest(existing, "sha256").hexdigest()
            except (OSError, ValueError):
                raise DownloadError(
                    "Existing firmware archive is unreadable or incomplete."
                ) from None
            if (
                not isinstance(saved, dict)
                or any(
                    saved.get(field) != metadata[field]
                    for field in (
                        "sha256",
                        "bytes",
                        "file",
                        "model",
                        "display_type",
                        "offered_version",
                    )
                )
                or saved_hash != sha256
            ):
                raise DownloadError(
                    "Existing firmware archive failed content or metadata verification; it was not overwritten."
                )
            print(f"Already archived: {version} ({args.model})")
            return None
        staging.rename(destination)
    print(f"Saved {destination / 'firmware.bin'} ({size:,} bytes)")
    print(f"SHA-256: {sha256}")
    return destination


def notify_download(archive: Path, model: str, version: str) -> None:
    notifier = shutil.which("terminal-notifier")
    if notifier is None:
        raise DownloadError(
            "Firmware saved, but terminal-notifier is not installed or not on PATH."
        )
    try:
        subprocess.run(
            [
                notifier,
                "-title",
                "Fraimic firmware downloaded",
                "-message",
                f"{model.title()}: {version}. Saved for analysis.",
                "-group",
                f"fraimic-firmware-{model}",
                "-open",
                archive.resolve().as_uri(),
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        raise DownloadError(
            "Firmware saved, but macOS notification failed. Check terminal-notifier permissions."
        ) from None


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    result.add_argument(
        "--device-key-file",
        type=Path,
        help="Private file holding the full key; otherwise use FRAIMIC_DEVICE_KEY",
    )
    result.add_argument("--model", required=True, choices=DISPLAY_TYPES)
    result.add_argument(
        "--current-version",
        required=True,
        help="Version reported to the vendor (e.g. 0.2.28); the server chooses the offer",
    )
    result.add_argument(
        "--orientation", choices=("portrait", "landscape"), default="portrait"
    )
    result.add_argument(
        "--battery-pct",
        type=int,
        choices=range(101),
        metavar="0-100",
        help="Optional frame telemetry",
    )
    result.add_argument("--wifi-ssid", help="Optional frame telemetry")
    result.add_argument("--ip", help="Optional frame LAN IP telemetry")
    result.add_argument(
        "--api-base-url", default=API_BASE, help="API origin (default: %(default)s)"
    )
    result.add_argument("--output-dir", type=Path, default=Path("scratch/firmware"))
    result.add_argument(
        "--check-only",
        action="store_true",
        help="Check for an offer without downloading it",
    )
    result.add_argument(
        "--notify",
        action="store_true",
        help="Send a macOS notification only for a newly saved archive (requires terminal-notifier)",
    )
    result.add_argument(
        "--sha256", help="Require a separately known SHA-256 for the downloaded file"
    )
    return result


def main(argv: list[str] | None = None) -> int:
    arguments = parser()
    args = arguments.parse_args(argv)
    if not args.current_version.strip():
        arguments.error("--current-version must not be empty")
    if args.sha256 and not re.fullmatch(r"[0-9a-fA-F]{64}", args.sha256):
        arguments.error("--sha256 must contain 64 hexadecimal characters")
    if args.sha256 and args.check_only:
        arguments.error("--sha256 requires a download; remove --check-only")
    try:
        offer = check_firmware(args, read_device_key(args.device_key_file))
        if offer is None:
            print("No firmware offered for this device and reported version.")
            return 0
        version, url = offer
        print(f"Firmware offered: {version} ({args.model})")
        if not args.check_only:
            archive = download_firmware(args, version, url)
            if archive is not None and args.notify:
                notify_download(archive, args.model, version)
    except DownloadError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except (OSError, UnicodeError):
        print(
            "Error: cannot read the key file or write the firmware archive.",
            file=sys.stderr,
        )
        return 1
    except KeyboardInterrupt:
        print("Cancelled.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
