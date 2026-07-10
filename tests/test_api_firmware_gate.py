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
