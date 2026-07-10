"""Tests for the /logs HTML admin-page parser (pure module, no HA)."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "fraimic"


def _load():
    if "fraimic" not in sys.modules:
        pkg = types.ModuleType("fraimic")
        pkg.__path__ = [str(PKG_DIR)]
        sys.modules["fraimic"] = pkg
    name = "fraimic.log_page"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, PKG_DIR / "log_page.py")
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


log_page = _load()


def _area(div_id: str, *lines: str) -> str:
    body = "\n".join(lines)
    return f"<div class='log-area' id='{div_id}'>{body}</div>"


# Shape copied from a real 13.3" frame on firmware 0.2.28.
REAL_SHAPE = (
    "<div class='log-wrap'>"
    + _area(
        "logOutput",
        "--- Thu, Jul 09, 2026 10:24 PM ---",
        "22:23:10 I (4045526) MAIN: [LOOP] Exited button wait",
        "22:24:13 W (4108516) WIFI: WiFi lost &mdash; reason 2",
        "22:24:14 E (4108616) UPLOAD: handler wedged",
    )
    + "<button>up</button>"
    + _area(
        "prevOutput",
        "--- Thu, Jul 09, 2026 09:15 PM ---",
        "21:15:43 I (35494244) MAIN: [LOOP] Entering deep sleep",
    )
    + "</div>"
)


def test_parses_both_boots():
    parsed = log_page.parse_logs_page(REAL_SHAPE)
    assert set(parsed) == {"current", "previous"}
    assert parsed["current"][0] == "--- Thu, Jul 09, 2026 10:24 PM ---"
    assert parsed["current"][-1] == "22:24:14 E (4108616) UPLOAD: handler wedged"
    assert len(parsed["current"]) == 4
    assert parsed["previous"] == [
        "--- Thu, Jul 09, 2026 09:15 PM ---",
        "21:15:43 I (35494244) MAIN: [LOOP] Entering deep sleep",
    ]


def test_unescapes_entities():
    parsed = log_page.parse_logs_page(REAL_SHAPE)
    assert "WiFi lost — reason 2" in parsed["current"][2]


def test_blank_lines_dropped():
    page = _area("logOutput", "line one", "", "   ", "line two")
    assert log_page.parse_logs_page(page)["current"] == ["line one", "line two"]


def test_only_current_boot():
    page = _area("logOutput", "just this boot")
    parsed = log_page.parse_logs_page(page)
    assert parsed == {"current": ["just this boot"]}


def test_garbage_inputs():
    assert log_page.parse_logs_page("") == {}
    assert log_page.parse_logs_page("<html>no logs</html>") == {}
    assert log_page.parse_logs_page(None) == {}  # type: ignore[arg-type]
    # An empty log area yields no key rather than an empty list.
    assert log_page.parse_logs_page(_area("logOutput")) == {}
