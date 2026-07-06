"""Widget registry: widget type -> renderer function."""

from __future__ import annotations

from .agenda import render_calendar, render_todo
from .base import WidgetRenderer
from .charts import render_chart, render_gauge, render_progress
from .core import CORE_WIDGETS
from .picture import render_image
from .weather import render_weather_current, render_weather_forecast

WIDGET_REGISTRY: dict[str, WidgetRenderer] = {
    **CORE_WIDGETS,
    "weather_current": render_weather_current,
    "weather_forecast": render_weather_forecast,
    "calendar": render_calendar,
    "todo": render_todo,
    "chart": render_chart,
    "gauge": render_gauge,
    "progress": render_progress,
    "image": render_image,
}
