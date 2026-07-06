"""Render context: everything a screen render needs, gathered up front.

Built on the event loop (``fetch.async_build_context``) before the CPU-bound
SVG/raster step runs in the executor, so the pure rendering code never touches
Home Assistant. ``now`` is injected for deterministic tests.

Widget payloads are plain JSON-able dicts keyed by the widget's index in
``ScreenConfig.widgets``. A payload of ``{"error": "..."}`` makes the widget
render an error placeholder instead of failing the whole screen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class RenderContext:
    now: datetime
    language: str = "en"
    widget_data: dict[int, Any] = field(default_factory=dict)
