"""Tests for the pure playlist logic (windows, rotation order)."""

from __future__ import annotations

from datetime import datetime, time

from conftest import load

playlist = load("render.playlist")
schema = load("render.schema")

# 2026-07-06 is a Monday.
MON_NOON = datetime(2026, 7, 6, 12, 0)
MON_NIGHT = datetime(2026, 7, 6, 23, 30)
TUE_EARLY = datetime(2026, 7, 7, 3, 0)
SAT_NOON = datetime(2026, 7, 11, 12, 0)


def _window(after="00:00", before="23:59", days=()):
    return schema.TimeWindow(
        after=time(*map(int, after.split(":"))),
        before=time(*map(int, before.split(":"))),
        days=frozenset(days),
    )


def _screen(screen_id: str, *, enabled=True, windows=(), interval=1800):
    return schema.ScreenConfig(
        screen_id=screen_id,
        name=screen_id,
        layout="full",
        widgets=(schema.WidgetConfig("clock", "main", {}),),
        enabled=enabled,
        windows=tuple(windows),
        interval=interval,
    )


def test_no_windows_always_matches() -> None:
    assert playlist.window_matches((), MON_NOON)


def test_daytime_window() -> None:
    window = _window("07:00", "22:00")
    assert playlist.window_matches((window,), MON_NOON)
    assert not playlist.window_matches((window,), MON_NIGHT)


def test_overnight_window_spans_midnight() -> None:
    window = _window("22:00", "06:00")
    assert playlist.window_matches((window,), MON_NIGHT)
    assert playlist.window_matches((window,), TUE_EARLY)
    assert not playlist.window_matches((window,), MON_NOON)


def test_day_filter() -> None:
    weekdays = _window(days=(0, 1, 2, 3, 4))
    assert playlist.window_matches((weekdays,), MON_NOON)
    assert not playlist.window_matches((weekdays,), SAT_NOON)


def test_any_of_multiple_windows_matches() -> None:
    windows = (_window("06:00", "09:00"), _window("18:00", "23:00"))
    assert not playlist.window_matches(windows, MON_NOON)
    assert playlist.window_matches(windows, MON_NIGHT.replace(hour=19))


def test_rotation_order_and_wraparound() -> None:
    screens = [_screen("a"), _screen("b"), _screen("c")]
    assert playlist.next_screen(screens, "a", MON_NOON).screen_id == "b"
    assert playlist.next_screen(screens, "c", MON_NOON).screen_id == "a"
    assert playlist.next_screen(screens, "b", MON_NOON, step=-1).screen_id == "a"
    assert playlist.next_screen(screens, "a", MON_NOON, step=-1).screen_id == "c"


def test_rotation_skips_disabled_and_out_of_window() -> None:
    screens = [
        _screen("a"),
        _screen("b", enabled=False),
        _screen("c", windows=[_window("00:00", "06:00")]),
        _screen("d"),
    ]
    assert playlist.next_screen(screens, "a", MON_NOON).screen_id == "d"


def test_single_screen_returns_itself() -> None:
    screens = [_screen("only")]
    assert playlist.next_screen(screens, "only", MON_NOON).screen_id == "only"


def test_unknown_current_starts_from_first_eligible() -> None:
    screens = [_screen("a", enabled=False), _screen("b")]
    assert playlist.next_screen(screens, "deleted", MON_NOON).screen_id == "b"
    assert playlist.next_screen(screens, None, MON_NOON).screen_id == "b"


def test_nothing_eligible_returns_none() -> None:
    screens = [_screen("a", enabled=False)]
    assert playlist.next_screen(screens, None, MON_NOON) is None
    assert playlist.next_screen([], None, MON_NOON) is None
