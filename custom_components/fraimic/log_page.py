"""Parser for the frame's ``GET /logs`` HTML admin page.

The frame serves an ESP-IDF log viewer. The log text is embedded as plain
text inside two ``<div class='log-area'>`` blocks — ``logOutput`` (the current
boot) and ``prevOutput`` (the previous boot). Warning/Error lines are present
without authentication; Info-level lines are only served once the firmware's
password gate has been satisfied (see ``api.FraimicClient.get_logs``).

Pure module — no Home Assistant imports — so it stays unit-testable
standalone, like ``image_convert`` and ``info_page``.
"""

from __future__ import annotations

import html as html_module
import re

_AREA_RE = re.compile(
    r"<div class='log-area'[^>]*id='(?P<id>[^']+)'[^>]*>(?P<body>.*?)</div>",
    re.DOTALL,
)

# Map the page's div ids to friendlier keys.
_AREAS = {"logOutput": "current", "prevOutput": "previous"}


def parse_logs_page(page: str) -> dict[str, list[str]]:
    """Extract log lines per boot from the ``/logs`` HTML.

    Returns ``{"current": [...], "previous": [...]}`` (keys omitted when the
    corresponding block is absent). Blank lines are dropped; HTML entities are
    unescaped. The log body is plain text on every firmware seen, so no inner
    markup stripping is needed, but be defensive and tolerate its absence.
    """
    if not isinstance(page, str):
        return {}
    result: dict[str, list[str]] = {}
    for match in _AREA_RE.finditer(page):
        key = _AREAS.get(match.group("id"))
        if key is None:
            continue
        lines = [
            html_module.unescape(line).rstrip()
            for line in match.group("body").split("\n")
            if line.strip()
        ]
        if lines:
            result[key] = lines
    return result
