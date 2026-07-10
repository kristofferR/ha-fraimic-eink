"""Parser for the frame's ``GET /info`` HTML admin page.

The page carries data absent from every JSON endpoint: the physical panel
size and battery health diagnostics (charge cycles, state-of-health, current
draw, temperature). The layout is unversioned firmware HTML, so everything
here is defensive: every field is optional and any parse failure yields an
incomplete dict rather than an error.

Pure module — no Home Assistant imports — so it stays unit-testable
standalone, like ``image_convert``.
"""

from __future__ import annotations

import html as html_module
import re
from typing import Any

# One row on the page: <span class='info-label'>Label</span>
#                      <span class='info-value'>Value…</span>
_ROW_RE = re.compile(
    r"<span class='info-label'>\s*(?P<label>[^<]+?)\s*</span>"
    r"\s*<span class='info-value'>(?P<value>.*?)</span>\s*</div>",
    re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")
_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _rows(page: str) -> dict[str, str]:
    """Extract label → plain-text value pairs from the page.

    The page repeats some labels across sections (e.g. ``Status`` under both
    Power and WiFi); those are dropped rather than guessed at. Every label we
    parse below is unique on firmware 0.2.28.
    """
    seen: dict[str, str] = {}
    ambiguous: set[str] = set()
    for match in _ROW_RE.finditer(page):
        label = html_module.unescape(match.group("label")).strip()
        value = html_module.unescape(_TAG_RE.sub("", match.group("value"))).strip()
        if label in seen and seen[label] != value:
            ambiguous.add(label)
        else:
            seen[label] = value
    for label in ambiguous:
        del seen[label]
    return seen


def _number(value: str | None) -> float | None:
    if not value:
        return None
    match = _NUMBER_RE.search(value)
    return float(match.group(0)) if match else None


def _int(value: str | None) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def parse_info_page(page: str) -> dict[str, Any]:
    """Parse the ``/info`` HTML into a flat dict of optional fields.

    Keys (all optional — absent when the row is missing or unparsable):
    ``panel_size_in``, ``battery_cycles``, ``battery_soh``,
    ``battery_current_ma``, ``battery_temperature_c``.
    """
    if not isinstance(page, str) or "info-label" not in page:
        return {}
    rows = _rows(page)
    parsed: dict[str, Any] = {}

    # "Device Type" reads e.g. `13.3" E-Ink` / `31.5" E-Ink`.
    panel = _number(rows.get("Device Type"))
    if panel is not None:
        parsed["panel_size_in"] = panel

    cycles = _int(rows.get("Cycles"))
    if cycles is not None:
        parsed["battery_cycles"] = cycles

    soh = _number(rows.get("Health (SOH)"))
    if soh is not None:
        parsed["battery_soh"] = soh

    # Positive while charging (e.g. "2090 mA"); may read negative on drain.
    current = _int(rows.get("Current"))
    if current is not None:
        parsed["battery_current_ma"] = current

    # "25°C" after entity unescaping.
    temperature = _number(rows.get("Temperature"))
    if temperature is not None:
        parsed["battery_temperature_c"] = temperature

    return parsed
