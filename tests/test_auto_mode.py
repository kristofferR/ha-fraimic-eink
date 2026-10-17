"""Auto mode decisions: settings, weighted sources, repeat avoidance, cadence."""

import random
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
import voluptuous as vol
from conftest import load

auto = load("auto_mode")

NOW = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)


def test_settings_round_trip_and_partial_updates():
    settings = auto.AutoSettings().updated(
        {
            "sources": [
                {"kind": "gallery", "source": "saved", "browse_id": "favorites",
                 "label": "Favorites", "weight": 2},
                {"kind": "shuffle"},
            ],
            "cadence": "times",
            "times": ["17:30", "07:00", "07:00"],
            "days": ["mon", "fri"],
            "active_hours": {"after": "07:00", "before": "23:00"},
            "avoid_repeats_days": -1,
            "orientation": "strict",
            "fit": "contain",
        }
    )
    assert settings.times == (time(7), time(17, 30))
    assert settings.days == {0, 4}
    assert settings.sources[1].title == "Surprise me"
    assert auto.AutoSettings.from_dict(settings.to_dict()) == settings
    # Untouched keys survive a partial update; fit can return to the default.
    changed = settings.updated({"caption": True, "fit": None})
    assert changed.caption and changed.fit is None
    assert changed.times == settings.times


@pytest.mark.parametrize(
    "patch",
    [
        {"cadence": "times"},
        {"sources": [{"kind": "gallery"}]},
        {"sources": [{"kind": "playlist"}]},
        {"sources": [{"kind": "shuffle"}, {"kind": "shuffle"}]},
        {"interval": 60},
        {"sources": [{"kind": "shuffle", "weight": 4}]},
    ],
)
def test_invalid_settings_are_rejected(patch):
    with pytest.raises(vol.Invalid):
        auto.AutoSettings().updated(patch)


def test_pick_source_respects_weights_and_backoff():
    heavy = auto.AutoSource("gallery", source="saved", weight=3)
    light = auto.AutoSource("shuffle")
    rng = random.Random(4)
    picks = [auto.pick_source((heavy, light), rng=rng) for _ in range(400)]
    assert 0.65 < picks.count(heavy) / len(picks) < 0.85
    assert auto.pick_source((heavy, light), {heavy.key}) == light
    assert auto.pick_source((heavy,), {heavy.key}) is None


def test_history_prefers_fresh_art_then_the_least_recently_shown():
    history = auto.AutoHistory()
    history.record("a", NOW - timedelta(days=40))
    history.record("b", NOW - timedelta(days=2))
    history.record("c", NOW - timedelta(days=1))
    assert history.choose(["a", "b", "c"], 30, NOW) == "a"
    assert history.choose(["b", "c"], 30, NOW) == "b"
    assert history.choose(["b", "c"], 30, NOW, exclude={"b"}) == "c"
    assert history.choose(["b"], 30, NOW, exclude={"b"}) is None
    # Until all shown: anything ever shown waits for the rest of the pool.
    assert history.choose(["a", "new"], auto.AVOID_UNTIL_ALL_SHOWN, NOW) == "new"
    assert history.choose(["a", "b"], 0, NOW, rng=random.Random(1)) in {"a", "b"}
    history.record("a", NOW)
    assert list(history.entries) == ["b", "c", "a"]
    assert auto.AutoHistory.from_list(history.to_list()).entries == history.entries


def test_history_is_bounded():
    history = auto.AutoHistory()
    for index in range(auto.HISTORY_LIMIT + 5):
        history.record(str(index), NOW)
    assert len(history.entries) == auto.HISTORY_LIMIT
    assert "0" not in history.entries


def test_next_change_for_each_cadence():
    last = datetime(2026, 10, 16, 18, tzinfo=timezone.utc)  # a Friday
    settings = auto.AutoSettings()
    assert settings.next_change(None, 600) is None
    assert settings.next_change(last, 600) == last + timedelta(seconds=600)
    own = settings.updated({"cadence": "interval", "interval": 3600})
    assert own.next_change(last, 600) == last + timedelta(hours=1)
    times = settings.updated({"cadence": "times", "times": ["07:00", "17:30"]})
    assert times.next_change(last, 600) == datetime(2026, 10, 17, 7, tzinfo=timezone.utc)
    weekdays = times.updated({"days": ["mon"]})
    assert weekdays.next_change(last, 600) == datetime(2026, 10, 19, 7, tzinfo=timezone.utc)


def test_picture_key_identifies_the_artwork():
    schema = load("render.schema")

    def screen(**source):
        return schema.screen_from_dict(
            schema.SCREEN_SCHEMA({"name": "x", "kind": "picture", **source})
        )

    assert auto.picture_key(screen(library_image="img")) == "library:img"
    assert auto.picture_key(screen(provider="met", provider_item="7")) == "provider:met:7"
    assert auto.picture_key(screen(provider="met")) is None


@pytest.mark.parametrize("cadence", ["queue", "interval"])
@pytest.mark.parametrize("month,day", [(3, 29), (10, 25)])
def test_interval_cadences_use_elapsed_time_across_dst(cadence, month, day):
    last = datetime(2026, month, day, 1, tzinfo=ZoneInfo("Europe/Oslo"))
    settings = auto.AutoSettings().updated({"cadence": cadence, "interval": 7200})
    due = settings.next_change(last, 7200)
    assert due.timestamp() - last.timestamp() == 7200


@pytest.mark.parametrize("month,day,hours", [(3, 29, 1), (10, 25, 3)])
def test_set_times_follow_wall_clock_across_dst(month, day, hours):
    local = ZoneInfo("Europe/Oslo")
    last = datetime(2026, month, day, 1, tzinfo=local)
    settings = auto.AutoSettings().updated({"cadence": "times", "times": ["03:00"]})
    due = settings.next_change(last, 600)
    assert due == datetime(2026, month, day, 3, tzinfo=local)
    assert due.timestamp() - last.timestamp() == hours * 3600
