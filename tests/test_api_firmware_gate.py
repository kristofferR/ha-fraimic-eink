"""Tests for the firmware-gated upload-path selection in api.py.

Loads api.py standalone (no HA, no aiohttp installed in CI) by stubbing the
aiohttp import — only the pure version-parsing helpers are exercised here.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

PKG_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "fraimic"


def _load_api():
    if "aiohttp" not in sys.modules:
        stub = types.ModuleType("aiohttp")
        # api.py references these in except clauses / type hints at runtime.
        stub.ClientError = type("ClientError", (Exception,), {})
        stub.ClientConnectionError = type(
            "ClientConnectionError", (stub.ClientError,), {}
        )
        stub.ClientResponse = object
        stub.ClientSession = object
        stub.ClientTimeout = lambda **kw: None
        stub.FormData = object
        sys.modules["aiohttp"] = stub
    if "fraimic" not in sys.modules:
        pkg = types.ModuleType("fraimic")
        pkg.__path__ = [str(PKG_DIR)]
        sys.modules["fraimic"] = pkg
    for name in ("const", "api"):
        mod_name = f"fraimic.{name}"
        if mod_name not in sys.modules:
            spec = importlib.util.spec_from_file_location(
                mod_name, PKG_DIR / f"{name}.py"
            )
            assert spec and spec.loader
            module = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = module
            spec.loader.exec_module(module)
    return sys.modules["fraimic.api"]


api = _load_api()


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("0.2.28", (0, 2, 28)),
        ("v0.2.28", (0, 2, 28)),
        ("V1.0.0", (1, 0, 0)),
        (" 0.3.1 ", (0, 3, 1)),
        ("0.2", (0, 2)),
        ("garbage", None),
        ("0.2.x", None),
        ("", None),
        (None, None),
        (28, None),
    ],
)
def test_parse_firmware(version, expected):
    assert api.parse_firmware(version) == expected


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        # Verified hang on 0.2.21; verified working on 0.2.28.
        ("0.2.21", False),
        ("0.2.27", False),
        ("0.2.28", True),
        ("v0.2.28", True),
        ("0.2.29", True),
        ("0.3.0", True),
        ("1.0.0", True),
        # Unknown/unparsable firmware must stay on the safe multipart path.
        (None, False),
        ("unknown", False),
        ("0.2", False),
    ],
)
def test_firmware_supports_api_image(version, expected):
    assert api.firmware_supports_api_image(version) is expected


def test_large_frame_upload_uses_extended_timeout():
    assert api.FraimicClient._upload_timeout(bytes(2_304_000)) == 600
    assert api.FraimicClient._upload_timeout(b"small frame") == 90


def test_upload_rejects_a_buffer_that_is_not_the_panel_size():
    import asyncio

    client = api.FraimicClient("192.0.2.1", object(), bin_size=960_000)

    async def unexpected(_data):
        raise AssertionError("a wrong-size buffer reached the frame")

    client._do_upload = client._do_upload_api_image = unexpected
    with pytest.raises(api.FraimicError, match="exactly 960000 bytes"):
        asyncio.run(client.upload_image(bytes(960_000 - 17)))


class _Reply:
    """Just enough of an aiohttp response for ``FraimicClient._json``."""

    def __init__(self, body):
        self.status = 200
        self._body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return None

    async def json(self, **_kwargs):
        if isinstance(self._body, str):
            import json

            return json.loads(self._body)
        return self._body


@pytest.mark.parametrize(
    "body",
    [{"status": "ok"}, '{"albums": [{"id": "a"', "<html>502 Bad Gateway</html>"],
    ids=["empty-upstream", "truncated", "html"],
)
def test_album_listing_must_be_an_album_list(body):
    import asyncio

    client = api.FraimicClient("192.0.2.1", object())

    async def reply(*_args, **_kwargs):
        return _Reply(body)

    client._request = reply
    with pytest.raises(api.FraimicError):
        asyncio.run(client.get_albums())


def test_album_edit_reply_must_be_that_album():
    import asyncio

    client = api.FraimicClient("192.0.2.1", object())
    sent = []

    async def reply(*args, **_kwargs):
        sent.append(args)
        return _Reply({"status": "ok"})

    client._request = reply
    with pytest.raises(api.FraimicError, match="did not return the album"):
        asyncio.run(client.update_album("a", {"active": False}))
    # The proxy cuts IDs at 127 bytes, which could edit a different album.
    with pytest.raises(api.FraimicError, match="longer than 127"):
        asyncio.run(client.update_album("a" * 128, {"active": False}))
    assert len(sent) == 1


@pytest.mark.parametrize(("bin_size", "settle"), [(960_000, 60), (2_304_000, 90)])
def test_commands_wait_for_the_render_after_an_upload(monkeypatch, bin_size, settle):
    """The firmware neither joins the render on sleep/restart nor guards it."""
    import asyncio

    clock = {"now": 1_000.0}
    waits = []

    async def fake_sleep(seconds):
        waits.append(seconds)
        clock["now"] += seconds

    monkeypatch.setattr(api.time, "time", lambda: clock["now"])
    monkeypatch.setattr(api.asyncio, "sleep", fake_sleep)
    client = api.FraimicClient("192.0.2.1", object(), bin_size=bin_size)
    sent = []

    async def upload(_data):
        sent.append(("upload", clock["now"]))

    async def reply(method, path, **_kwargs):
        sent.append((path, clock["now"]))
        return _Reply({"status": "ok"})

    client._do_upload = upload
    client._request = reply

    async def run():
        await client.upload_image(bytes(bin_size))
        clock["now"] += 10
        await client.sleep()

    asyncio.run(run())

    assert waits == [settle - 10]
    assert sent == [("upload", 1_000.0), ("/api/sleep", 1_000.0 + settle)]


@pytest.mark.parametrize("first_command", ["refresh", "upload"])
@pytest.mark.parametrize("next_command", ["upload", "refresh", "sleep", "restart"])
def test_commands_serialize_requests_and_recheck_the_render(
    monkeypatch, first_command, next_command
):
    import asyncio

    clock = {"now": 1000.0}
    sent = []
    yield_once = asyncio.sleep
    client = api.FraimicClient("192.0.2.1", object(), bin_size=4)
    monkeypatch.setattr(api.time, "time", lambda: clock["now"])

    async def run():
        waiting = asyncio.Event()
        release_wait = asyncio.Event()
        requesting = asyncio.Event()
        release_reply = asyncio.Event()

        async def fake_sleep(seconds):
            if not waiting.is_set():
                waiting.set()
                await release_wait.wait()
            clock["now"] += seconds

        async def request(name):
            sent.append((name, clock["now"]))
            if len(sent) == 1:
                requesting.set()
                await release_reply.wait()

        async def upload(_data):
            await request("upload")

        async def reply(_method, path, **_kwargs):
            await request(path.removeprefix("/api/"))
            return _Reply({"status": "ok"})

        def command(name):
            return client.upload_image(b"1234") if name == "upload" else getattr(client, name)()

        monkeypatch.setattr(api.asyncio, "sleep", fake_sleep)
        client._do_upload = upload
        client._request = reply
        client.mark_rendering()
        first = asyncio.create_task(command(first_command))
        await waiting.wait()
        second = asyncio.create_task(command(next_command))
        await yield_once(0)
        release_wait.set()
        await requesting.wait()
        await yield_once(0)
        assert sent == [(first_command, 1060)]
        release_reply.set()
        await asyncio.gather(first, second)

    asyncio.run(run())
    assert sent == [(first_command, 1060), (next_command, 1120)]


@pytest.mark.parametrize("recovery", [False, True])
@pytest.mark.parametrize("interruption", ["cancel", "timeout"])
def test_interrupted_upload_protects_the_possible_render(
    monkeypatch, recovery, interruption
):
    import asyncio
    from unittest.mock import AsyncMock

    clock = {"now": 1000.0}
    client = api.FraimicClient("192.0.2.1", object(), bin_size=4)
    monkeypatch.setattr(api.time, "time", lambda: clock["now"])

    async def fake_sleep(seconds):
        clock["now"] += seconds

    monkeypatch.setattr(api.asyncio, "sleep", fake_sleep)

    async def run():
        uploading = asyncio.Event()
        attempts = 0

        async def upload(_data):
            nonlocal attempts
            attempts += 1
            if recovery and attempts == 1:
                raise api.FraimicConnectionError("connection reset")
            uploading.set()
            if interruption == "timeout":
                raise api.FraimicTimeoutError("reply timed out")
            await asyncio.Event().wait()

        client._do_upload = upload
        client.restart = AsyncMock()
        client._wait_reachable = AsyncMock()
        task = asyncio.create_task(client.upload_image(b"1234"))
        await uploading.wait()
        if interruption == "cancel":
            task.cancel()
        error = asyncio.CancelledError if interruption == "cancel" else api.FraimicTimeoutError
        with pytest.raises(error):
            await task
        assert attempts == (2 if recovery else 1)
        assert client.restart.await_count == (1 if recovery else 0)
        assert client.render_busy_until == clock["now"] + 60
        assert not client._command_lock.locked()
        await client.wait_for_render()
        assert clock["now"] == client.render_busy_until

    asyncio.run(run())
