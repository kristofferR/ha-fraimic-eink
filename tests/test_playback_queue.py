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
    queue = model.PlaybackQueue(interval=21600, end_action="repeat")
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
    queue.end_action = "repeat"
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
    queue.end_action = "repeat"
    assert queue.candidate(now, previous=True) == b


def test_shuffle_changes_include_next_repeat_cycle(monkeypatch):
    queue = model.PlaybackQueue(end_action="repeat")
    a, b, c = queue.add([picture(name) for name in ("a", "b", "c")])
    queue.cursor = c.screen.screen_id
    monkeypatch.setattr(model.random, "shuffle", lambda items: items.reverse())
    queue.set_shuffle(True)
    assert queue.upcoming == [b, a]
    assert queue.get(queue.cursor) == c
    queue.set_shuffle(False)
    assert queue.items == [a, b, c]
    assert queue.candidate(datetime(2026, 9, 18, 12)) == a


def test_disabled_snapshots_do_not_count_as_future_playback():
    queue = model.PlaybackQueue()
    disabled, a, b = queue.add([
        replace(picture("disabled"), enabled=False), picture("a"), picture("b")
    ])
    (next_item,) = queue.add([picture("next")], index=1)
    assert queue.upcoming == [a, next_item, b]
    queue.advance(b.screen.screen_id, datetime(2026, 9, 18, 12))
    assert queue.upcoming == []
    assert queue.position > queue.items.index(disabled)


def test_hand_items_play_before_auto_picks_and_keep_converts_a_pick():
    queue = model.PlaybackQueue()
    (current,) = queue.add([picture("current")])
    queue.cursor = current.screen.screen_id
    pick = queue.add_auto(picture("pick"), "Favorites")
    hand = queue.add([picture("hand")])[0]
    assert queue.upcoming == [hand, pick]
    assert queue.add([picture("first")], index=0)[0] == queue.upcoming[0]
    ids = [item.screen.screen_id for item in queue.upcoming]
    queue.reorder(list(reversed(ids)))
    # Auto picks stay below everything queued by hand unless they are kept.
    assert queue.upcoming[-1] == pick
    queue.reorder(list(reversed(ids)), keep_ids=[pick.screen.screen_id])
    assert queue.upcoming[0] == pick and pick.auto_source is None


def test_shuffle_clear_and_trim_leave_auto_picks_in_place(monkeypatch):
    queue = model.PlaybackQueue(end_action="repeat")
    items = queue.add([picture(str(i)) for i in range(4)])
    queue.cursor = items[0].screen.screen_id
    pick = queue.add_auto(picture("pick"), "Surprise me")
    queue.end_action = "auto"
    monkeypatch.setattr(model.random, "shuffle", lambda values: values.reverse())
    queue.set_shuffle(True)
    assert queue.upcoming[-1] == pick
    queue.clear()
    assert queue.upcoming == [pick] and queue.end_action == "auto"
    played = [queue.add_auto(picture(f"old{i}"), "Auto") for i in range(3)]
    queue.cursor = played[-1].screen.screen_id
    queue.trim_played(2)
    assert played[0] not in queue.items and played[1] in queue.items
    assert items[0] in queue.items  # hand history is never trimmed
    assert queue.drop_auto() == []


def test_legacy_repeat_flag_migrates_to_end_action():
    data = model.PlaybackQueue().to_dict()
    data.pop("end_action")
    data["repeat"] = True
    assert model.PlaybackQueue.from_dict(data).end_action == "repeat"
    queue = model.PlaybackQueue(end_action="auto")
    queue.add_auto(picture("pick"), "Favorites")
    restored = model.PlaybackQueue.from_dict(queue.to_dict())
    assert restored.end_action == "auto"
    assert restored.auto_upcoming[0].auto_source == "Favorites"
