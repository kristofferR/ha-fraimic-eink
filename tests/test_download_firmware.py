"""Exercise the standalone downloader against an isolated HTTP vendor fixture."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

import pytest

spec = importlib.util.spec_from_file_location(
    "download_firmware",
    Path(__file__).resolve().parents[1] / "scripts/download_firmware.py",
)
assert spec and spec.loader
downloader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(downloader)

KEY = "synthetic-device-secret"
SIGNATURE = "synthetic-signed-url-secret"
# Enough ESP image header for the downloader's sanity check. Not bootable code.
IMAGE = (
    bytes([0xE9, 1])
    + bytes(10)
    + bytes([9, 0])
    + bytes(10)
    + b"synthetic firmware" * 400
)


@pytest.fixture
def vendor(tmp_path, monkeypatch):
    state = {
        "requests": [],
        "poll_status": 200,
        "download_status": 200,
        "image": IMAGE,
        "length": str(len(IMAGE)),
    }

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            state["requests"].append((self.path, dict(self.headers)))
            if self.path.startswith("/api/v1/upload/check/"):
                self.send_response(state["poll_status"])
                body = json.dumps(state["poll"]).encode()
                self.send_header("Content-Length", str(len(body)))
            else:
                self.send_response(state["download_status"])
                body = state["image"]
                if state["length"] is not None:
                    self.send_header("Content-Length", state["length"])
            self.send_header("Location", state["origin"] + "/redirect-target")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    state["origin"] = f"http://127.0.0.1:{server.server_port}"
    state["poll"] = {
        "has_new_upload": True,
        "presigned_url": state["origin"] + "/art.bin",
        "firmware": {
            "version": "0.2.30",
            "presigned_url": state["origin"] + "/firmware.bin?signature=" + SIGNATURE,
        },
        "account": {"private_data": "must not be archived"},
    }
    monkeypatch.setenv("FRAIMIC_DEVICE_KEY", KEY)
    state["output"] = tmp_path / "archives"
    state["args"] = [
        "--model",
        "large",
        "--current-version",
        "0.2.29",
        "--api-base-url",
        state["origin"],
        "--output-dir",
        str(state["output"]),
    ]
    worker = Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
    )
    worker.start()
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


@pytest.mark.parametrize(
    ("model", "display_type"), [("standard", "133"), ("large", "315")]
)
def test_poll_download_and_private_metadata(
    vendor, tmp_path, capsys, model, display_type
):
    key_file = tmp_path / "device.key"
    key_file.write_text(KEY + "\n")
    digest = hashlib.sha256(IMAGE).hexdigest()
    result = downloader.main(
        vendor["args"]
        + [
            "--model",
            model,
            "--device-key-file",
            str(key_file),
            "--battery-pct",
            "83",
            "--wifi-ssid",
            "Home & café+#",
            "--ip",
            "192.0.2.10",
            "--sha256",
            digest.upper(),
        ]
    )
    assert result == 0
    assert len(vendor["requests"]) == 2
    poll, download = vendor["requests"]
    assert urlsplit(poll[0]).path == f"/api/v1/upload/check/{KEY}"
    assert parse_qs(urlsplit(poll[0]).query) == {
        "display_type": [display_type],
        "orientation": ["portrait"],
        "is_periodic_poll": ["false"],
        "current_version": ["0.2.29"],
        "battery_pct": ["83"],
        "wifi_ssid": ["Home & café+#"],
        "ip": ["192.0.2.10"],
    }
    assert "Home%20%26%20caf%C3%A9%2B%23" in poll[0]
    assert download[0] == "/firmware.bin?signature=" + SIGNATURE
    assert "Authorization" not in poll[1] and "Range" not in download[1]
    (archive,) = vendor["output"].iterdir()
    assert (archive / "firmware.bin").read_bytes() == IMAGE
    metadata_text = (archive / "metadata.json").read_text()
    metadata = json.loads(metadata_text)
    assert metadata["sha256"] == digest
    assert metadata["bytes"] == len(IMAGE)
    assert metadata["display_type"] == display_type
    assert metadata["current_version_sent"] == "0.2.29"
    assert metadata["offered_version"] == "0.2.30"
    captured = capsys.readouterr()
    for secret in (KEY, SIGNATURE, "must not be archived", "Home & café"):
        assert secret not in metadata_text + captured.out + captured.err


@pytest.mark.parametrize("missing", [True, False])
def test_no_offer_does_not_download_image(vendor, missing):
    if missing:
        del vendor["poll"]["firmware"]
    else:
        vendor["poll"]["firmware"] = None
    assert downloader.main(vendor["args"]) == 0
    assert len(vendor["requests"]) == 1
    assert not vendor["output"].exists()


def test_check_only_omits_unsupplied_telemetry(vendor):
    assert downloader.main(vendor["args"] + ["--check-only"]) == 0
    assert len(vendor["requests"]) == 1
    query = parse_qs(urlsplit(vendor["requests"][0][0]).query)
    assert set(query) == {
        "display_type",
        "orientation",
        "is_periodic_poll",
        "current_version",
    }
    assert not vendor["output"].exists()


@pytest.mark.parametrize(
    "firmware",
    [
        {},
        [],
        "bad",
        {"version": "../../outside", "presigned_url": "https://example.com"},
        {"version": "0.3", "presigned_url": "file:///etc/passwd"},
        {"version": "0.3", "presigned_url": "http://example.com/firmware.bin"},
        {"version": "0.3", "presigned_url": "https://example.com:invalid/firmware.bin"},
    ],
)
def test_malformed_offer_is_an_error(vendor, firmware):
    vendor["poll"]["firmware"] = firmware
    assert downloader.main(vendor["args"]) == 1
    assert len(vendor["requests"]) == 1
    assert not vendor["output"].exists()


@pytest.mark.parametrize(
    ("stage", "status"),
    [
        ("poll", 401),
        ("poll", 403),
        ("poll", 404),
        ("poll", 500),
        ("poll", 302),
        ("download", 403),
        ("download", 302),
        ("download", 206),
    ],
)
def test_http_errors_are_redacted_and_never_retried_or_redirected(
    vendor, capsys, stage, status
):
    vendor[stage + "_status"] = status
    assert downloader.main(vendor["args"]) == 1
    assert len(vendor["requests"]) == (1 if stage == "poll" else 2)
    captured = capsys.readouterr()
    assert str(status) in captured.err
    assert KEY not in captured.out + captured.err
    assert SIGNATURE not in captured.out + captured.err
    assert not list(vendor["output"].glob("*"))


@pytest.mark.parametrize(
    "failure", ["truncated", "no_length", "huge", "html", "wrong_chip", "hash"]
)
def test_failed_download_leaves_no_archive(vendor, failure):
    extra = []
    if failure == "truncated":
        vendor["length"] = str(len(IMAGE) + 10)
    elif failure == "no_length":
        vendor["length"] = None
    elif failure == "huge":
        vendor["length"] = str(downloader.MAX_FIRMWARE_BYTES + 1)
    elif failure == "html":
        vendor["image"] = b"<html>error</html>".ljust(len(IMAGE))
    elif failure == "wrong_chip":
        vendor["image"] = IMAGE[:12] + bytes(2) + IMAGE[14:]
    else:
        extra = ["--sha256", "0" * 64]
    assert downloader.main(vendor["args"] + extra) == 1
    assert list(vendor["output"].iterdir()) == []


def test_existing_archive_is_preserved(vendor):
    assert downloader.main(vendor["args"]) == 0
    (archive,) = vendor["output"].iterdir()
    metadata = (archive / "metadata.json").read_bytes()
    assert downloader.main(vendor["args"]) == 0
    assert list(vendor["output"].iterdir()) == [archive]
    assert (archive / "firmware.bin").read_bytes() == IMAGE
    assert (archive / "metadata.json").read_bytes() == metadata


def test_corrupt_existing_archive_is_not_silently_skipped(vendor):
    assert downloader.main(vendor["args"]) == 0
    (archive,) = vendor["output"].iterdir()
    (archive / "firmware.bin").write_bytes(b"damaged")
    assert downloader.main(vendor["args"]) == 1
    assert (archive / "firmware.bin").read_bytes() == b"damaged"


def test_incomplete_archive_metadata_is_rejected(vendor):
    assert downloader.main(vendor["args"]) == 0
    (archive,) = vendor["output"].iterdir()
    metadata_file = archive / "metadata.json"
    metadata = json.loads(metadata_file.read_text())
    del metadata["model"]
    metadata_file.write_text(json.dumps(metadata))
    assert downloader.main(vendor["args"]) == 1


def test_notifications_only_for_new_content(vendor, monkeypatch):
    monkeypatch.setattr(downloader.shutil, "which", lambda _: "/test/terminal-notifier")
    notify = Mock()
    monkeypatch.setattr(downloader.subprocess, "run", notify)
    args = vendor["args"] + ["--notify"]
    assert downloader.main(args + ["--check-only"]) == 0
    notify.assert_not_called()
    assert downloader.main(args) == 0
    (archive,) = vendor["output"].iterdir()
    command = notify.call_args.args[0]
    assert command[0] == "/test/terminal-notifier"
    assert archive.resolve().as_uri() in command
    assert "Large: 0.2.30. Saved for analysis." in command
    assert downloader.main(args) == 0
    assert notify.call_count == 1
    # A vendor reissue with the same version and different bytes is new content.
    vendor["image"] = IMAGE[:-1] + b"!"
    assert downloader.main(args) == 0
    assert notify.call_count == 2
    vendor["poll"]["firmware"] = None
    assert downloader.main(args) == 0
    assert notify.call_count == 2


def test_notification_failure_keeps_download(vendor, monkeypatch, capsys):
    monkeypatch.setattr(downloader.shutil, "which", lambda _: "/test/terminal-notifier")
    monkeypatch.setattr(
        downloader.subprocess,
        "run",
        Mock(side_effect=subprocess.CalledProcessError(3, "notifier")),
    )
    assert downloader.main(vendor["args"] + ["--notify"]) == 1
    (archive,) = vendor["output"].iterdir()
    assert (archive / "firmware.bin").read_bytes() == IMAGE
    assert "Firmware saved, but macOS notification failed" in capsys.readouterr().err


@pytest.mark.parametrize("key", ["", "...masked", "…masked", "two words"])
def test_missing_or_masked_key_never_reaches_vendor(vendor, monkeypatch, key):
    monkeypatch.setenv("FRAIMIC_DEVICE_KEY", key)
    assert downloader.main(vendor["args"]) == 1
    assert vendor["requests"] == []


@pytest.mark.parametrize("operation", ["open", "write"])
def test_disk_errors_are_not_reported_as_network_errors(
    vendor, monkeypatch, capsys, operation
):
    original_open = Path.open

    @contextmanager
    def fail_archive(path, *args, **kwargs):
        if path.name == "firmware.bin":
            if operation == "open":
                raise OSError("private filesystem detail")
            yield Mock(write=Mock(side_effect=OSError("private filesystem detail")))
        else:
            with original_open(path, *args, **kwargs) as stream:
                yield stream

    monkeypatch.setattr(Path, "open", fail_archive)
    assert downloader.main(vendor["args"]) == 1
    captured = capsys.readouterr()
    assert "write the firmware archive" in captured.err
    assert "connection" not in captured.err
    assert "private filesystem detail" not in captured.err
    assert list(vendor["output"].iterdir()) == []
