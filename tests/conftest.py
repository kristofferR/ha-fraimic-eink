"""Shared test helpers: import fraimic modules without importing Home Assistant.

Only the integration's top-level ``__init__.py`` imports Home Assistant, so we
register a synthetic ``fraimic`` package pointing at the real directory and let
normal import machinery handle everything below it. Pure modules (const,
image_convert, render.*) then import cleanly; HA-touching modules simply must
not be loaded here.
"""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "fraimic"


def load(name: str):
    """Import ``fraimic.<name>`` (dotted paths ok) without executing HA imports."""
    if "fraimic" not in sys.modules:
        pkg = types.ModuleType("fraimic")
        pkg.__path__ = [str(PKG_DIR)]
        sys.modules["fraimic"] = pkg
    return importlib.import_module(f"fraimic.{name}")
