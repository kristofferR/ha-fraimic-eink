"""Widget registry: widget type -> renderer function."""

from __future__ import annotations

from .base import WidgetRenderer
from .core import CORE_WIDGETS

WIDGET_REGISTRY: dict[str, WidgetRenderer] = {**CORE_WIDGETS}
