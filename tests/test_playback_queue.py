"""Snapshot isolation, order, and repeat semantics of the frame queue."""

from dataclasses import replace
from datetime import datetime, time

import pytest
from conftest import load

model = load("playback_queue")
schema = load("render.schema")


def picture(name):
    return schema.screen_from_dict(
        schema.SCREEN_SCHEMA({"name": name, "kind": "picture", "library_image": name}),
        name,
    )


def test_round_trip_preserves_duplicate_occurrences_settings_and_snapshots():
    queue = model.PlaybackQueue(interval=21600, repeat=True)
    original = replace(picture("same"), overlay_mode="none")
    a, b = queue.add([original, original], playlist_id="saved", playlist_name="Saved")
    queue.cursor = a.screen.screen_id
    original.source["library_image"] = "changed"
    restored = model.PlaybackQueue.from_dict(queue.to_dict())
    assert restored.to_dict() == queue.to_dict()
    assert a.screen.screen_id != b.screen.screen_id
    assert b.screen.source["library_image"] == "same"
    assert restored.items[1].screen.overlay_mode == "none"
    assert restored.upcoming[0].playlist_name == "Saved"


def test_dashboard_snapshot_round_trips_widgets_and_time_windows():
    screen = schema.screen_from_dict(
        schema.SCREEN_SCHEMA(
            {
                "name": "Dashboard",
                "layout": "full",
                "widgets": [{"type": "template", "slot": "main", "template": "Hello"}],
                "windows": [
                    {"after": "09:00", "before": "17:00", "days": ["mon", "fri"]}
                ],
            }
        )
    )
    queue = model.PlaybackQueue()
    item = queue.add([screen])[0]
    restored = model.PlaybackQueue.from_dict(queue.to_dict())
    assert restored.items[0].screen == item.screen


def test_shuffle_only_changes_upcoming_and_can_restore_order():
    queue = model.PlaybackQueue()
    items = queue.add([picture(str(i)) for i in range(20)])
    queue.cursor = items[3].screen.screen_id
    queue.set_shuffle(True)
    assert queue.items[:4] == items[:4]
    assert {i.screen.screen_id for i in queue.upcoming} == {
        i.screen.screen_id for i in items[4:]
    }
    queue.set_shuffle(False)
    assert queue.items == items


def test_repeat_is_explicit_and_removed_items_never_return():
    queue = model.PlaybackQueue()
    a, b, c = queue.add([picture(name) for name in ("a", "b", "c")])
    queue.cursor = a.screen.screen_id
    queue.remove(0, b.screen.screen_id)
    queue.cursor = c.screen.screen_id
    now = datetime(2026, 9, 18, 12)
    assert queue.candidate(now) is None
    queue.repeat = True
    assert queue.candidate(now) == a
    assert b not in queue.items
    queue.clear()
    assert queue.candidate(now) is None


def test_reorder_rejects_stale_and_duplicate_ids():
    queue = model.PlaybackQueue()
    a, b = queue.add([picture("a"), picture("b")])
    with pytest.raises(ValueError):
        queue.reorder([a.screen.screen_id, a.screen.screen_id])
    with pytest.raises(ValueError):
        queue.reorder([a.screen.screen_id])
    queue.reorder([b.screen.screen_id, a.screen.screen_id])
    assert queue.items == [b, a]


def test_window_deferred_item_survives_consumption_and_restart():
    queue = model.PlaybackQueue()
    morning = replace(
        picture("morning"),
        windows=(schema.TimeWindow(after=time(6), before=time(9)),),
    )
    a, b = queue.add([morning, picture("anytime")])
    night = datetime(2026, 9, 18, 22)
    assert queue.candidate(night) == b
    queue.advance(b.screen.screen_id, night)
    assert queue.upcoming == [a]
    restored = model.PlaybackQueue.from_dict(queue.to_dict())
    assert restored.candidate(night) is None
    assert restored.candidate(datetime(2026, 9, 19, 7)).screen == a.screen


def test_previous_wraps_only_when_repeat_is_enabled():
    queue = model.PlaybackQueue()
    a, b = queue.add([picture("a"), picture("b")])
    now = datetime(2026, 9, 18, 12)
    queue.cursor = a.screen.screen_id
    assert queue.candidate(now, previous=True) is None
    queue.repeat = True
    assert queue.candidate(now, previous=True) == b
