"""Pure playlist decision logic (no Home Assistant imports; headless-tested).

The scheduler in ``scheduler.py`` wires these into HA; everything here is
plain data-in/data-out so the tricky bits (overnight windows, day filters,
rotation order) are covered by the fast test suite.
"""

from __future__ import annotations

from datetime import datetime

from .schema import ScreenConfig, TimeWindow


def window_matches(windows: tuple[TimeWindow, ...], now: datetime) -> bool:
    """True when ``now`` falls inside any window (no windows = always)."""
    if not windows:
        return True
    current = now.time()
    for window in windows:
        if window.after <= window.before:
            if not window.after <= current <= window.before:
                continue
            start_weekday = now.weekday()
        # Overnight window (e.g. 22:00 -> 06:00): either side of midnight.
        elif current >= window.after:
            start_weekday = now.weekday()
        elif current <= window.before:
            start_weekday = (now.weekday() - 1) % 7
        else:
            continue
        if not window.days or start_weekday in window.days:
            return True
    return False


def eligible(screen: ScreenConfig, now: datetime) -> bool:
    """Whether a screen may be shown right now."""
    return screen.enabled and window_matches(screen.windows, now)


def next_screen(
    screens: list[ScreenConfig] | tuple[ScreenConfig, ...],
    current_id: str | None,
    now: datetime,
    *,
    step: int = 1,
) -> ScreenConfig | None:
    """The next eligible screen after ``current_id`` in rotation order.

    ``step=-1`` walks backwards (previous). A single eligible screen returns
    itself (so a one-screen playlist re-renders with fresh data each cycle).
    Returns None when nothing is eligible.
    """
    if not screens:
        return None
    ids = [screen.screen_id for screen in screens]
    try:
        start = ids.index(current_id)
    except ValueError:
        # Unknown/removed current screen: begin just before the first so the
        # first eligible screen comes up next.
        start = -step if step > 0 else 0
    count = len(screens)
    for offset in range(1, count + 1):
        candidate = screens[(start + step * offset) % count]
        if eligible(candidate, now):
            return candidate
    return None
