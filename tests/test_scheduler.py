"""Tests for playlist scheduler retry state without importing Home Assistant."""

from __future__ import annotations

import asyncio
import sys
import types
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, time, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from conftest import load


def _install_scheduler_stubs(monkeypatch: pytest.MonkeyPatch) -> type[Exception]:
    homeassistant = types.ModuleType("homeassistant")
    core = types.ModuleType("homeassistant.core")
    exceptions = types.ModuleType("homeassistant.exceptions")
    helpers = types.ModuleType("homeassistant.helpers")
    event = types.ModuleType("homeassistant.helpers.event")
    storage = types.ModuleType("homeassistant.helpers.storage")
    util = types.ModuleType("homeassistant.util")
    dt = types.ModuleType("homeassistant.util.dt")
    display = types.ModuleType("fraimic.render.display")
    playlist = types.ModuleType("fraimic.render.playlist")
    schema = types.ModuleType("fraimic.render.schema")
    coordinator = types.ModuleType("fraimic.coordinator")
    screens = types.ModuleType("fraimic.screens")
    services = types.ModuleType("fraimic.services")
    # scheduler imports ArtFetchError from providers.ha, which pulls aiohttp —
    # stub it like the other HA-touching neighbours.
    providers = types.ModuleType("fraimic.providers")
    providers_ha = types.ModuleType("fraimic.providers.ha")

    class HomeAssistant:
        pass

    class HomeAssistantError(Exception):
        pass

    class ArtFetchError(HomeAssistantError):
        pass

    class Store:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def async_load(self) -> dict:
            return {}

        async def async_save(self, _data: dict) -> None:
            return None

    class FrameUploadError(Exception):
        pass

    class CloudDeliveryError(Exception):
        pass

    def callback(func: Callable[..., object]) -> Callable[..., object]:
        return func

    def async_track_time_interval(
        _hass: object, _action: Callable[..., object], _interval: timedelta
    ) -> Callable[[], None]:
        return lambda: None

    async def async_show_screen(*_args: object, **_kwargs: object) -> dict:
        raise FrameUploadError("frame asleep")

    core.HomeAssistant = HomeAssistant
    core.callback = callback
    exceptions.HomeAssistantError = HomeAssistantError
    event.async_track_time_interval = async_track_time_interval
    storage.Store = Store
    dt.now = lambda: datetime(2026, 7, 3, 14, 5)
    dt.utcnow = lambda: datetime(2026, 7, 3, 12, 5)
    display.async_show_screen = async_show_screen
    display.discard_prepared_thumbnails = lambda *_args, **_kwargs: None
    display.prepared_thumbnail_fingerprint = lambda _hass, _entry, screen: repr(
        getattr(screen, "source", None)
    )
    playlist.eligible = lambda *_args, **_kwargs: True
    playlist.next_screen = lambda *_args, **_kwargs: None
    schema.ScreenConfig = SimpleNamespace
    schema.KIND_PICTURE = "picture"
    coordinator.FraimicConfigEntry = SimpleNamespace
    screens.screens_from_entry = lambda _entry: []
    services.FrameUploadError = FrameUploadError
    services.CloudDeliveryError = CloudDeliveryError
    providers.ha = providers_ha
    providers_ha.ArtFetchError = ArtFetchError
    homeassistant.core = core
    homeassistant.exceptions = exceptions
    homeassistant.helpers = helpers
    homeassistant.util = util
    helpers.event = event
    helpers.storage = storage
    util.dt = dt

    for name, module in {
        "homeassistant": homeassistant,
        "homeassistant.core": core,
        "homeassistant.exceptions": exceptions,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.event": event,
        "homeassistant.helpers.storage": storage,
        "homeassistant.util": util,
        "homeassistant.util.dt": dt,
        "fraimic.render.display": display,
        "fraimic.render.playlist": playlist,
        "fraimic.render.schema": schema,
        "fraimic.coordinator": coordinator,
        "fraimic.screens": screens,
        "fraimic.services": services,
        "fraimic.providers": providers,
        "fraimic.providers.ha": providers_ha,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)

    return FrameUploadError


def _load_scheduler(monkeypatch):
    schema = load("render.schema")
    playlist = load("render.playlist")
    _install_scheduler_stubs(monkeypatch)
    monkeypatch.setitem(sys.modules, "fraimic.render.schema", schema)
    monkeypatch.setitem(sys.modules, "fraimic.render.playlist", playlist)
    sys.modules.pop("fraimic.scheduler", None)
    return load("scheduler")


def _screen(name="Picture", **fields):
    schema = load("render.schema")
    return schema.screen_from_dict(
        schema.SCREEN_SCHEMA(
            {
                "name": name,
                "kind": "picture",
                "library_image": name,
                **fields,
            }
        ),
        name,
    )


@pytest.fixture
def playback(monkeypatch):
    module = _load_scheduler(monkeypatch)
    now = [datetime(2026, 9, 18, 12, tzinfo=timezone.utc)]
    monkeypatch.setattr(module.dt_util, "now", lambda: now[0])
    monkeypatch.setattr(module.dt_util, "utcnow", lambda: now[0])
    monkeypatch.setattr(
        module.dt_util, "parse_datetime", datetime.fromisoformat, raising=False
    )
    monkeypatch.setattr(
        module.dt_util,
        "utc_from_timestamp",
        lambda stamp: datetime.fromtimestamp(stamp, timezone.utc),
        raising=False,
    )
    entry = SimpleNamespace(
        entry_id="frame",
        options={},
        subentries={},
        async_create_task=Mock(),
        runtime_data=SimpleNamespace(
            coordinator=SimpleNamespace(
                last_update_success=True,
                data={"battery": {"percent": 51}},
                async_add_listener=lambda listener: lambda: None,
                async_set_frame_online=Mock(),
            ),
            power=SimpleNamespace(
                retry_at=lambda reason: (now[0] + timedelta(minutes=5)).timestamp()
            ),
            send_queue=None,
            upload_lock=asyncio.Lock(),
            cloud=None,
        ),
    )
    scheduler = module.FraimicScheduler(SimpleNamespace(), entry)
    entry.runtime_data.scheduler = scheduler
    store = SimpleNamespace(
        async_save=AsyncMock(), async_load=AsyncMock(return_value={})
    )
    scheduler._store = store
    show = AsyncMock(
        return_value={"uploaded": True, "displayed": True, "content_hash": "hash"}
    )
    monkeypatch.setattr(module, "async_show_screen", show)
    return SimpleNamespace(
        module=module, scheduler=scheduler, entry=entry, show=show, store=store, now=now
    )


def run(coro):
    return asyncio.run(coro)


def add(p, *names):
    for name in names:
        run(p.scheduler.async_add_to_queue(_screen(name)))
    return p.scheduler.queued_slides


def test_standalone_queue_plays_at_its_own_interval_and_finishes(playback):
    p = playback
    first, second = add(p, "first", "second")
    run(p.scheduler.async_set_playback(interval=600))
    run(p.scheduler.async_set_enabled(True))
    assert p.scheduler.current_id == first.screen_id
    assert p.scheduler.queued_slides == [second]
    p.now[0] += timedelta(seconds=599)
    run(p.scheduler._async_tick())
    assert p.show.await_count == 1
    p.now[0] += timedelta(seconds=1)
    run(p.scheduler._async_tick())
    assert p.scheduler.current_id == second.screen_id
    assert p.scheduler.exhausted
    p.now[0] += timedelta(days=1)
    run(p.scheduler._async_tick())
    assert p.show.await_count == 2
    assert p.scheduler.current_screen == second


def test_closed_display_window_advances_before_long_interval_elapses(playback):
    p = playback
    schema = load("render.schema")
    p.now[0] = p.now[0].replace(hour=8, minute=55)
    morning = replace(
        _screen("morning"),
        windows=(schema.TimeWindow(after=time(6), before=time(9)),),
    )
    run(p.scheduler.async_add_to_queue(morning))
    (art,) = add(p, "art")[-1:]
    run(p.scheduler.async_set_playback(interval=21600))
    run(p.scheduler.async_set_enabled(True))
    assert p.scheduler.current_screen.name == "morning"
    p.now[0] += timedelta(minutes=6)
    run(p.scheduler._async_tick())
    assert p.scheduler.current_screen == art


def test_automatic_playback_keeps_window_deferred_item_for_later(playback):
    p = playback
    schema = load("render.schema")
    morning = replace(
        _screen("morning"),
        windows=(schema.TimeWindow(after=time(6), before=time(9)),),
    )
    run(p.scheduler.async_add_to_queue(morning))
    add(p, "art")
    run(p.scheduler.async_set_enabled(True))
    assert p.scheduler.current_screen.name == "art"
    assert [s.name for s in p.scheduler.queued_slides] == ["morning"]
    assert not p.scheduler.exhausted
    p.now[0] = (p.now[0] + timedelta(days=1)).replace(hour=7)
    run(p.scheduler._async_tick())
    assert p.scheduler.current_screen.name == "morning"
    assert p.scheduler.exhausted


def test_replay_exhausted_queue_is_explicit(playback):
    p = playback
    add(p, "first")
    run(p.scheduler.async_set_enabled(True))
    assert p.scheduler.exhausted
    run(p.scheduler.async_set_enabled(True))
    assert p.show.await_count == 2


def test_repeat_is_a_frame_setting_and_clear_disables_it(playback):
    p = playback
    first, second = add(p, "first", "second")
    run(p.scheduler.async_set_playback(repeat=True))
    for _ in range(3):
        run(p.scheduler.async_next())
    assert p.scheduler.current_id == first.screen_id
    run(p.scheduler.async_clear_queue())
    assert not p.scheduler.queue.repeat
    assert not p.scheduler.queued_slides
    assert p.scheduler.current_screen == first
    assert not run(p.scheduler.async_next())


def test_playlist_actions_copy_items_and_never_assign_or_edit_catalog(playback):
    p = playback
    catalog = SimpleNamespace(
        playlist_id="saved", name="Saved", interval=21600, shuffle=True
    )
    source = [_screen("a"), _screen("b")]
    manager = SimpleNamespace(
        require=lambda _: catalog,
        render_slides=lambda _: source,
        async_assign=AsyncMock(),
    )
    p.scheduler._playlists = manager
    add(p, "existing")
    run(p.scheduler.async_enqueue_playlist("saved", action="queue"))
    assert [s.name for s in p.scheduler.queued_slides] == ["existing", "a", "b"]
    run(p.scheduler.async_enqueue_playlist("saved", action="play_next"))
    assert [s.name for s in p.scheduler.queued_slides] == [
        "a",
        "b",
        "existing",
        "a",
        "b",
    ]
    assert len({s.screen_id for s in p.scheduler.screens}) == 5
    source[0].source["library_image"] = "changed"
    run(p.scheduler.async_refresh_playlist(reset=True))
    assert p.scheduler.queued_slides[0].source["library_image"] == "a"
    run(p.scheduler.async_set_playback(interval=900, shuffle=True, repeat=True))
    assert (catalog.interval, catalog.shuffle) == (21600, True)
    manager.async_assign.assert_not_awaited()


def test_play_now_replaces_queue_but_keeps_last_confirmed_display_on_failure(playback):
    p = playback
    add(p, "old")
    run(p.scheduler.async_next())
    old = p.scheduler.current_screen
    p.scheduler._playlists = SimpleNamespace(
        require=lambda _: SimpleNamespace(name="New"),
        render_slides=lambda _: [_screen("new")],
    )
    p.show.side_effect = p.module.FrameUploadError("asleep")
    run(p.scheduler.async_enqueue_playlist("saved", action="play"))
    assert p.scheduler.current_screen == old
    assert [s.name for s in p.scheduler.queued_slides] == ["new"]
    assert p.scheduler._pending == p.scheduler.queued_slides[0]


def test_play_now_notifies_and_waits_only_for_new_playlist_window(playback):
    p = playback
    add(p, "old")
    run(p.scheduler.async_set_playback(interval=21600))
    run(p.scheduler.async_next())
    schema = load("render.schema")
    scheduled = replace(
        _screen("scheduled"),
        windows=(schema.TimeWindow(after=time(13), before=time(14)),),
    )
    p.scheduler._playlists = SimpleNamespace(
        require=lambda _: SimpleNamespace(name="Scheduled"),
        render_slides=lambda _: [scheduled],
    )
    observed = []
    p.scheduler.async_add_listener(lambda: observed.append(p.scheduler.enabled))
    run(p.scheduler.async_enqueue_playlist("saved", action="play"))
    assert observed[-1] is True
    assert p.scheduler.current_screen.name == "old"
    p.now[0] += timedelta(hours=1)
    run(p.scheduler._async_tick())
    assert p.scheduler.current_screen.name == "scheduled"


@pytest.mark.parametrize("repeat", [False, True])
def test_disabled_only_queue_is_exhausted(playback, repeat):
    p = playback
    run(p.scheduler.async_add_to_queue(replace(_screen("disabled"), enabled=False)))
    run(p.scheduler.async_set_playback(repeat=repeat))
    run(p.scheduler.async_set_enabled(True))
    assert p.scheduler.exhausted
    p.show.assert_not_awaited()


def test_remove_and_reorder_have_no_hidden_rotation(playback):
    p = playback
    a, b, c = add(p, "a", "b", "c")
    run(p.scheduler.async_reorder_queue([c.screen_id, a.screen_id, b.screen_id]))
    run(p.scheduler.async_remove_from_queue(1, a.screen_id))
    assert p.scheduler.queued_slides == [c, b]
    run(p.scheduler.async_next())
    run(p.scheduler.async_next())
    assert p.scheduler.exhausted
    with pytest.raises(p.module.HomeAssistantError):
        run(p.scheduler.async_remove_from_queue(0, c.screen_id))


def test_selecting_later_duplicate_uses_unique_occurrence(playback):
    p = playback
    first, second = add(p, "same", "same")
    assert first.screen_id != second.screen_id
    run(p.scheduler.async_play_queue_item("queue", 1, second.screen_id))
    assert p.scheduler.current_id == second.screen_id
    assert p.scheduler.exhausted
    run(p.scheduler.async_previous())
    assert p.scheduler.current_id == first.screen_id


@pytest.mark.parametrize("manual", [True, False])
def test_sleep_retry_preserves_queue_and_manual_intent_across_restart(playback, manual):
    p = playback
    first, second = add(p, "a", "b")
    p.scheduler.enabled = p.scheduler._stored_enabled = not manual
    p.show.side_effect = p.module.FrameUploadError("asleep")
    run(p.scheduler._async_show(first, manual=manual))
    assert p.scheduler.queued_slides == [first, second]
    assert p.scheduler.current_id is None
    saved = p.store.async_save.call_args.args[0]
    p.store.async_load.return_value = saved
    restored = p.module.FraimicScheduler(SimpleNamespace(), p.entry)
    restored._store = p.store
    run(restored.async_start())
    assert restored._pending.screen_id == first.screen_id
    assert restored._pending_requires_enabled is (not manual)
    p.show.side_effect = None
    run(restored._async_retry_pending(restored._pending))
    assert restored.current_id == first.screen_id
    assert restored.queued_slides == [second]
    assert restored._pending is None


def test_pending_automatic_retry_follows_reorder_and_clear(playback):
    p = playback
    a, b = add(p, "a", "b")
    p.show.side_effect = p.module.FrameUploadError("asleep")
    run(p.scheduler.async_set_enabled(True))
    run(p.scheduler.async_reorder_queue([b.screen_id, a.screen_id]))
    assert p.scheduler._pending == b
    run(p.scheduler.async_clear_queue())
    assert p.scheduler._pending is None


def test_manual_pending_selection_survives_settings_and_reorder(playback):
    p = playback
    a, b, c = add(p, "a", "b", "c")
    p.show.side_effect = p.module.FrameUploadError("asleep")
    run(p.scheduler.async_play_queue_item("queue", 1, b.screen_id))
    run(p.scheduler.async_set_playback(interval=21600, repeat=True))
    run(p.scheduler.async_reorder_queue([c.screen_id, a.screen_id, b.screen_id]))
    assert p.scheduler._pending == b
    p.show.side_effect = None
    run(p.scheduler._async_retry_pending(b))
    assert p.scheduler.current_screen == b


def test_removing_manual_pending_selection_cancels_retry(playback):
    p = playback
    a, b = add(p, "a", "b")
    p.show.side_effect = p.module.FrameUploadError("asleep")
    run(p.scheduler.async_play_queue_item("queue", 1, b.screen_id))
    run(p.scheduler.async_remove_from_queue(1, b.screen_id))
    assert p.scheduler._pending is None
    assert p.scheduler.queued_slides == [a]


def test_pending_automatic_retry_does_not_run_while_paused(playback):
    p = playback
    (a,) = add(p, "a")
    p.show.side_effect = p.module.FrameUploadError("asleep")
    run(p.scheduler.async_set_enabled(True))
    run(p.scheduler.async_set_enabled(False))
    p.show.reset_mock()
    run(p.scheduler._async_retry_pending(a))
    p.show.assert_not_awaited()


def test_explicit_send_owns_next_wake_over_automatic_queue(playback):
    p = playback
    (a,) = add(p, "a")
    p.entry.runtime_data.send_queue = SimpleNamespace(
        pending=object(), async_discard=AsyncMock()
    )
    p.show.side_effect = p.module.FrameUploadError("asleep")
    run(p.scheduler._async_show(a))
    assert p.scheduler._pending is None
    run(p.scheduler.async_next())
    p.entry.runtime_data.send_queue.async_discard.assert_awaited_once()
    assert p.scheduler._pending == a


@pytest.mark.parametrize("reason", ["low_battery", "cooldown", "daily_budget"])
def test_deferred_send_exposes_reason_backs_off_and_preserves_position(
    playback, reason
):
    p = playback
    a, b = add(p, "a", "b")
    run(p.scheduler.async_next())
    p.show.return_value = {"uploaded": False, "displayed": False, "skip_reason": reason}
    p.scheduler.enabled = True
    p.now[0] += timedelta(days=1)
    run(p.scheduler._async_tick())
    assert p.scheduler.blocked_reason == reason
    assert p.scheduler.retry_at == p.now[0] + timedelta(minutes=5)
    assert p.scheduler.current_screen == a
    assert p.scheduler.queued_slides == [b]
    p.show.reset_mock()
    run(p.scheduler._async_tick())
    p.show.assert_not_awaited()


@pytest.mark.parametrize("error", ["ArtFetchError", "CloudDeliveryError"])
def test_transient_failures_keep_queue_head(playback, error):
    p = playback
    (a,) = add(p, "a")
    p.show.side_effect = getattr(p.module, error)("temporary")
    run(p.scheduler.async_set_enabled(True))
    assert p.scheduler.queued_slides == [a]
    assert p.scheduler.retry_at is not None
    assert p.scheduler._pending is None


@pytest.mark.parametrize("error", ["ArtFetchError", "CloudDeliveryError"])
@pytest.mark.parametrize("manual", [False, True])
def test_failed_auto_art_is_replaced_only_for_automatic_fetch_errors(playback, error, manual):
    p = playback
    _auto(p)
    failed = p.scheduler.queued_slides[0]
    p.show.side_effect = getattr(p.module, error)("unavailable")
    if manual:
        with pytest.raises(getattr(p.module, error)):
            run(p.scheduler._async_show(failed, manual=True))
    else:
        assert not run(p.scheduler._async_show(failed))
    removed = error == "ArtFetchError" and not manual
    assert (p.scheduler.queue.get(failed.screen_id) is None) == removed
    assert p.scheduler.retry_at == p.now[0] + timedelta(minutes=5)
    if removed:
        assert failed.screen_id not in {
            item["id"] for item in p.store.async_save.call_args.args[0]["playback_queue"]["items"]
        }
        p.show.side_effect = None
        run(p.scheduler._async_top_up_auto())
        p.now[0] += timedelta(minutes=5)
        run(p.scheduler._async_tick())
        assert p.scheduler.current_screen.name == "pick1"


@pytest.mark.parametrize("legacy,other_source", [(False, False), (True, False), (False, True)])
def test_failed_auto_art_backs_off_its_source_before_refill(
    playback, monkeypatch, legacy, other_source
):
    p = playback
    sources = [{"kind": "gallery", "source": "broken", "label": "Art"}]
    if other_source:
        sources.append({"kind": "gallery", "source": "healthy", "label": "Art"})
    run(p.scheduler.async_set_auto({"sources": sources}))
    monkeypatch.setattr(
        p.module, "pick_source",
        lambda sources, unavailable: next(
            (source for source in sources if source.key not in unavailable), None
        ),
    )

    async def resolve(_hass, _entry, _settings, source, _history, *, exclude, playlists):
        if f"library:{source.source}" in exclude:
            raise p.module.AutoSourceQueued
        return _screen(source.source)

    resolver = AsyncMock(side_effect=resolve)
    monkeypatch.setitem(
        sys.modules, "fraimic.auto_sources", SimpleNamespace(async_resolve_pick=resolver)
    )
    run(p.scheduler.async_set_playback(end_action="auto"))
    run(p.scheduler._async_top_up_auto())
    failed = p.scheduler.queue.auto_upcoming[0]
    if legacy:
        failed.auto_source_key = None
    p.show.side_effect = p.module.ArtFetchError("404")
    assert not run(p.scheduler._async_show(failed.screen))
    source_key = p.scheduler.auto.sources[0].key
    assert p.scheduler._auto_backoff == {source_key: p.now[0] + p.module.AUTO_BACKOFF}
    p.show.side_effect = None
    for _ in range(2):
        run(p.scheduler._async_top_up_auto())
        p.now[0] += timedelta(minutes=5)
        run(p.scheduler._async_tick())
        assert all(slide.name != "broken" for slide in p.scheduler.queued_slides)
    assert sum(call.args[3].source == "broken" for call in resolver.await_args_list) == 2
    if other_source:
        assert p.scheduler.current_screen.name == "healthy"
    p.now[0] += timedelta(minutes=5)
    assert p.scheduler._auto_topup_due()
    run(p.scheduler._async_top_up_auto())
    assert any(slide.name == "broken" for slide in p.scheduler.queued_slides)


def test_legacy_auto_failure_with_shared_labels_preserves_other_sources(playback):
    p = playback
    run(p.scheduler.async_set_auto({"sources": [
        {"kind": "gallery", "source": "broken", "label": "Art"},
        {"kind": "gallery", "source": "healthy", "label": "Art"},
    ]}))
    _auto(p)
    failed = p.scheduler.queue.auto_upcoming[0]
    failed.auto_source_key = None
    p.show.side_effect = p.module.ArtFetchError("404")
    assert not run(p.scheduler._async_show(failed.screen))
    assert not p.scheduler._auto_backoff
    assert "library:pick0" in p.scheduler.auto_history.entries
    assert p.scheduler._auto_topup_due()


@pytest.mark.parametrize("source", [{"url": "https://example.test/art.jpg"}, {"entity": "image.art"}])
def test_failed_auto_playlist_source_backs_off_before_refill(playback, source):
    p = playback
    run(p.scheduler.async_set_auto({"sources": [{"kind": "playlist", "playlist_id": "art"}]}))

    async def pick(_source):
        if p.scheduler.queue.auto_upcoming:
            raise p.module.AutoSourceQueued
        return replace(_screen("art"), source=source)

    resolve = AsyncMock(side_effect=pick)
    p.scheduler._async_resolve_auto = resolve
    run(p.scheduler.async_set_playback(end_action="auto"))
    run(p.scheduler._async_top_up_auto())
    failed = p.scheduler.queue.auto_upcoming[0]
    p.show.side_effect = p.module.HomeAssistantError("source unavailable")
    assert not run(p.scheduler._async_show(failed.screen))
    assert p.scheduler.queue.get(failed.screen.screen_id) is None
    assert p.scheduler._auto_backoff == {
        failed.auto_source_key: p.now[0] + p.module.AUTO_BACKOFF
    }
    resolve.reset_mock()
    for _ in range(14):
        p.now[0] += timedelta(minutes=1)
        run(p.scheduler._async_top_up_auto())
        run(p.scheduler._async_tick())
    resolve.assert_not_awaited()
    p.now[0] += timedelta(minutes=1)
    assert p.scheduler._auto_topup_due()
    run(p.scheduler._async_top_up_auto())
    resolve.assert_awaited()


def test_permanently_invalid_item_does_not_block_following_item(playback):
    p = playback
    a, b = add(p, "a", "b")
    p.show.side_effect = p.module.HomeAssistantError("invalid")
    run(p.scheduler.async_set_enabled(True))
    assert p.scheduler.queued_slides == [b]
    assert p.scheduler.current_screen is None
    p.show.side_effect = None
    p.now[0] += timedelta(minutes=1)
    run(p.scheduler._async_tick())
    assert p.scheduler.current_screen == b


def test_failed_manual_selection_preserves_unrelated_upcoming_items(playback):
    p = playback
    current, a, b, c = add(p, "current", "a", "b", "c")
    run(p.scheduler.async_next())
    p.show.side_effect = p.module.HomeAssistantError("missing image")
    with pytest.raises(p.module.HomeAssistantError):
        run(p.scheduler.async_play_queue_item("queue", 1, b.screen_id))
    assert p.scheduler.current_screen == current
    assert p.scheduler.queued_slides == [a, b, c]
    assert p.scheduler.blocked_reason is None


@pytest.mark.parametrize("repeat", [False, True])
def test_final_invalid_item_finishes_without_a_stale_retry(playback, repeat):
    p = playback
    add(p, "invalid")
    run(p.scheduler.async_set_playback(repeat=repeat))
    p.show.side_effect = p.module.HomeAssistantError("missing image")
    run(p.scheduler.async_set_enabled(True))
    assert p.scheduler.exhausted
    assert p.scheduler.blocked_reason is None
    assert p.scheduler.retry_at is None


def test_cloud_acceptance_advances_delivery_without_claiming_display(playback):
    p = playback
    a, b = add(p, "a", "b")
    run(p.scheduler.async_next())
    p.entry.runtime_data.cloud = SimpleNamespace(
        wake_interval=600,
        delivery_deadline=(p.now[0] + timedelta(seconds=780)).timestamp(),
    )

    async def cloud_send(*args, **kwargs):
        await p.scheduler.async_cloud_delivery_accepted()
        return {"uploaded": False, "displayed": False, "cloud_queued": True}

    p.show.side_effect = cloud_send
    run(p.scheduler.async_next())
    assert p.scheduler.current_screen == a
    assert p.scheduler.queue.cursor == b.screen_id
    assert p.scheduler.exhausted
    assert p.scheduler.hold_until == p.now[0] + timedelta(seconds=780)


def test_paused_scheduler_still_retires_cloud_delivery(playback):
    p = playback
    expire = AsyncMock()
    p.entry.runtime_data.cloud = SimpleNamespace(async_expire_delivery=expire)
    run(p.scheduler._async_tick())
    expire.assert_awaited_once()


def test_pause_preserves_remaining_interval(playback):
    p = playback
    add(p, "a", "b")
    run(p.scheduler.async_set_enabled(True))
    p.now[0] += timedelta(seconds=100)
    run(p.scheduler.async_set_enabled(False))
    p.now[0] += timedelta(hours=2)
    run(p.scheduler.async_set_enabled(True))
    assert (p.now[0] - p.scheduler.last_rotation).total_seconds() == 100
    assert p.show.await_count == 1


def test_camera_pause_does_not_overwrite_persisted_playback(playback):
    p = playback
    add(p, "a", "b")
    run(p.scheduler.async_set_enabled(True))
    run(p.scheduler.async_set_enabled(False, persist=False))
    assert not p.scheduler.enabled
    assert p.scheduler.stored_enabled
    run(p.scheduler._async_save())
    assert p.store.async_save.call_args.args[0]["enabled"]


def test_external_send_holds_queue_without_consuming_it(playback):
    p = playback
    (a,) = add(p, "a")
    run(p.scheduler.async_notify_external_upload())
    assert p.scheduler.queued_slides == [a]
    assert p.scheduler.displayed_hash is None
    assert p.scheduler.hold_until == p.now[0] + timedelta(
        seconds=p.scheduler.queue.interval
    )


@pytest.mark.parametrize("operation", ["add", "clear", "reorder", "next", "settings"])
def test_queue_mutations_cannot_race_an_upload(playback, operation):
    p = playback
    (a,) = add(p, "a")
    p.scheduler._busy = True
    actions = {
        "add": lambda: p.scheduler.async_add_to_queue(_screen()),
        "clear": p.scheduler.async_clear_queue,
        "reorder": lambda: p.scheduler.async_reorder_queue([a.screen_id]),
        "next": p.scheduler.async_next,
        "settings": lambda: p.scheduler.async_set_playback(repeat=True),
    }
    with pytest.raises(p.module.HomeAssistantError):
        run(actions[operation]())
    assert p.scheduler.queued_slides == [a]


@pytest.mark.parametrize("retry_current", [False, True])
def test_migration_preserves_current_hand_queue_session_and_interval(playback, retry_current):
    p = playback
    a, b, c = [_screen(name) for name in ("a", "b", "c")]
    p.scheduler._playlists = SimpleNamespace(
        assigned_to=lambda _: SimpleNamespace(
            playlist_id="saved", name="Saved", interval=21600, shuffle=False
        ),
        render_slides=lambda _: [a, b, c],
        render_slide_by_id=lambda _: None,
    )
    p.store.async_load.return_value = {
        "enabled": True,
        "current_screen_id": "b",
        "playlist_cursor_id": "b",
        "queued_slide_ids": ["c"],
        "displayed_hash": "hash",
        "last_rotation": p.now[0].isoformat(),
        "session": {"order": ["a", "b", "c"]},
        "pending_queue_id": "b" if retry_current else None,
    }
    run(p.scheduler.async_start())
    assert p.scheduler.current_screen.name == "b"
    assert p.scheduler._pending == (p.scheduler.current_screen if retry_current else None)
    assert [s.name for s in p.scheduler.queued_slides] == ["c", "c", "a"]
    assert p.scheduler.queue.repeat
    assert p.scheduler.queue.interval == 21600
    assert len({s.screen_id for s in p.scheduler.screens}) == 4
    saved = p.store.async_save.call_args.args[0]
    p.store.async_load.return_value = saved
    restored = p.module.FraimicScheduler(SimpleNamespace(), p.entry)
    restored._store = p.store
    run(restored.async_start())
    assert restored.queue.to_dict() == p.scheduler.queue.to_dict()


def test_queue_survives_library_pruning_without_restarting_played_items(playback):
    p = playback
    a, b, c = add(p, "a", "b", "c")
    run(p.scheduler.async_next())
    run(p.scheduler.async_next())
    run(p.scheduler.async_prune_library_image("b"))
    assert p.scheduler.queued_slides == [c]
    assert p.scheduler.current_screen == b


def test_prefetch_respects_window_and_never_uploads(playback):
    p = playback
    p.entry.options[p.module.CONF_PLAYLIST_PREFETCH] = 2
    add(p, "a", "b", "c")
    assert [s.name for s in p.scheduler._prefetch_screens()] == ["a", "b"]
    p.show.assert_not_awaited()


def test_starting_another_playlist_preserves_frame_playback_settings(playback):
    p = playback
    run(p.scheduler.async_set_playback(interval=21600, shuffle=True, repeat=True))
    p.scheduler._playlists = SimpleNamespace(
        require=lambda _: SimpleNamespace(name="Saved"),
        render_slides=lambda _: [_screen("a"), _screen("b")],
    )
    run(p.scheduler.async_enqueue_playlist("saved", action="play"))
    assert p.scheduler.queue.interval == 21600
    assert p.scheduler.queue.shuffle
    assert p.scheduler.queue.repeat


def test_catalog_preview_lookup_does_not_add_a_queue_entry(playback):
    p = playback
    source = _screen("catalog")
    p.scheduler._playlists = SimpleNamespace(render_slide_by_id=lambda _: source)
    assert p.scheduler.slide_by_id("catalog") == source
    assert p.scheduler.screens == []


def test_restart_preserves_pending_legacy_external_picture(playback):
    p = playback
    schema = load("render.schema")
    p.store.async_load.return_value = {
        "enabled": False,
        "external_queue": {"external": schema.screen_to_dict(_screen("external"))},
        "queued_slide_ids": ["external"],
        "pending_queue_id": "external",
        "pending_requires_enabled": False,
    }
    run(p.scheduler.async_start())
    assert p.scheduler._pending.screen_id == p.scheduler.queued_slides[0].screen_id
    assert not p.scheduler._pending_requires_enabled


def test_charging_releases_delay_and_notifies_player(playback):
    p = playback
    p.scheduler.blocked_reason = "low_battery"
    p.scheduler.retry_at = p.now[0] + timedelta(minutes=5)
    listener = Mock()
    p.scheduler.async_add_listener(listener)
    p.entry.runtime_data.coordinator.data = {"battery": {"charging": True}}
    p.scheduler._coordinator_updated()
    assert p.scheduler.blocked_reason is None
    assert p.scheduler.retry_at is None
    listener.assert_called_once()


def _auto(p, *, fail=None):
    """Turn on auto mode with a fake resolver that names picks pick0, pick1..."""
    made = []

    async def resolve(source):
        if fail is not None:
            raise fail
        made.append(f"pick{len(made)}")
        return _screen(made[-1])

    p.scheduler._async_resolve_auto = resolve
    run(p.scheduler.async_set_playback(end_action="auto"))
    run(p.scheduler._async_top_up_auto())
    return made


def test_auto_mode_keeps_art_changing_after_the_queue_ends(playback):
    p = playback
    (hand,) = add(p, "hand")
    run(p.scheduler.async_set_playback(interval=600))
    run(p.scheduler.async_set_enabled(True))
    _auto(p)
    assert not p.scheduler.exhausted
    assert [s.name for s in p.scheduler.queued_slides] == ["pick0", "pick1", "pick2"]
    p.now[0] += timedelta(seconds=599)
    run(p.scheduler._async_tick())
    assert p.scheduler.current_screen.name == "hand"
    p.now[0] += timedelta(seconds=1)
    run(p.scheduler._async_tick())
    assert p.scheduler.current_screen.name == "pick0"
    assert p.scheduler.playlist_name == "Auto · Surprise me"
    assert "library:pick0" in p.scheduler.auto_history.entries
    run(p.scheduler._async_top_up_auto())
    assert [s.name for s in p.scheduler.queued_slides] == ["pick1", "pick2", "pick3"]
    # Something queued by hand still plays before the remaining auto picks.
    add(p, "later")
    assert p.scheduler.queued_slides[0].name == "later"


@pytest.mark.parametrize("source_kind", ["playlist", "shuffle"])
@pytest.mark.parametrize("overlay_mode", ["inherit", "none"])
def test_auto_overlays_preserve_playlist_choices(playback, source_kind, overlay_mode):
    p = playback
    settings = {"kind": source_kind}
    if source_kind == "playlist":
        settings["playlist_id"] = "saved"
    run(p.scheduler.async_set_auto({"sources": [settings], "overlays": "none"}))

    async def resolve(_source):
        return replace(_screen("art"), overlay_mode=overlay_mode)

    p.scheduler._async_resolve_auto = resolve
    run(p.scheduler.async_set_playback(end_action="auto"))
    run(p.scheduler._async_top_up_auto())
    expected = overlay_mode if source_kind == "playlist" else "none"
    assert all(slide.overlay_mode == expected for slide in p.scheduler.queued_slides)


def test_auto_playlist_fallback_identity_reaches_displayed_history(playback):
    p = playback

    async def resolve(_source):
        return replace(
            _screen("art"), source={"entity": "image.art"}, history_key="slide:saved:a"
        )

    p.scheduler._async_resolve_auto = resolve
    run(p.scheduler.async_set_playback(end_action="auto"))
    run(p.scheduler._async_top_up_auto())
    run(p.scheduler._async_tick())
    assert "slide:saved:a" in p.scheduler.auto_history.entries


@pytest.mark.parametrize("pool_size", [1, 2])
def test_auto_refill_reuses_small_pools_on_cadence_without_backoff(playback, monkeypatch, pool_size):
    p = playback
    keys = [f"library:pick{i}" for i in range(pool_size)]

    async def resolve(_hass, _entry, settings, _source, history, *, exclude, playlists):
        if all(key in exclude for key in keys):
            raise p.module.AutoSourceQueued
        key = history.choose(keys, settings.avoid_repeats_days, p.now[0], exclude=exclude)
        return _screen(key.removeprefix("library:")) if key else None

    resolver = AsyncMock(side_effect=resolve)
    monkeypatch.setitem(
        sys.modules, "fraimic.auto_sources", SimpleNamespace(async_resolve_pick=resolver)
    )
    run(p.scheduler.async_set_playback(interval=600))
    run(p.scheduler.async_set_playback(end_action="auto"))
    run(p.scheduler._async_top_up_auto())
    assert len(p.scheduler.queued_slides) == pool_size
    for _ in range(5):
        previous_id = p.scheduler.current_id
        run(p.scheduler._async_tick())
        assert p.scheduler.current_id != previous_id
        run(p.scheduler._async_top_up_auto())
        assert len(p.scheduler.queued_slides) == pool_size
        assert not p.scheduler._auto_backoff
        calls = resolver.await_count
        assert not p.scheduler._auto_topup_due()
        run(p.scheduler._async_top_up_auto())
        p.now[0] += timedelta(seconds=60)
        run(p.scheduler._async_tick())
        assert resolver.await_count == calls
        p.now[0] += timedelta(seconds=540)

    first = p.scheduler.queued_slides[0]
    run(p.scheduler.async_remove_from_queue(0, first.screen_id))
    assert p.scheduler._auto_topup_due()
    run(p.scheduler._async_top_up_auto())
    assert len(p.scheduler.queued_slides) == pool_size


def test_auto_picks_follow_set_times(playback):
    p = playback
    add(p, "hand")
    run(p.scheduler.async_set_enabled(True))
    run(p.scheduler.async_set_auto({"cadence": "times", "times": ["18:00"]}))
    _auto(p)
    p.now[0] = p.now[0].replace(hour=17, minute=59)
    run(p.scheduler._async_tick())
    assert p.scheduler.current_screen.name == "hand"
    assert p.scheduler.cycle_seconds == 6 * 3600
    p.now[0] = p.now[0].replace(hour=18)
    run(p.scheduler._async_tick())
    assert p.scheduler.current_screen.name == "pick0"


def test_removing_or_refreshing_auto_picks_skips_them(playback):
    p = playback
    _auto(p)
    first = p.scheduler.queued_slides[0]
    run(p.scheduler.async_remove_from_queue(0, first.screen_id))
    assert "library:pick0" in p.scheduler.auto_history.entries
    run(p.scheduler._async_top_up_auto())
    assert [s.name for s in p.scheduler.queued_slides] == ["pick1", "pick2", "pick3"]
    run(p.scheduler.async_new_auto_picks())
    assert not p.scheduler.queued_slides
    assert {"library:pick1", "library:pick3"} <= set(p.scheduler.auto_history.entries)


def test_settings_change_discards_stale_picks_and_in_flight_resolution(playback):
    p = playback
    _auto(p)

    async def resolve(source):
        await p.scheduler.async_set_auto({"avoid_repeats_days": 7})
        return _screen("stale")

    p.scheduler._async_resolve_auto = resolve
    run(p.scheduler.async_remove_from_queue(0, p.scheduler.queued_slides[0].screen_id))
    run(p.scheduler._async_top_up_auto())
    assert not p.scheduler.queued_slides
    assert p.scheduler.auto.avoid_repeats_days == 7


def test_failing_sources_back_off_and_explain_the_wait(playback):
    p = playback
    run(p.scheduler.async_set_enabled(True))
    _auto(p, fail=p.module.HomeAssistantError("Met is unreachable"))
    assert not p.scheduler.queued_slides
    assert p.scheduler.blocked_reason == "auto_unavailable"
    assert p.scheduler.auto_error == "Surprise me: Met is unreachable"
    assert not p.scheduler._auto_topup_due()
    p.now[0] += p.module.AUTO_BACKOFF
    assert p.scheduler._auto_topup_due()


def test_leaving_auto_mode_drops_unplayed_picks(playback):
    p = playback
    _auto(p)
    run(p.scheduler.async_set_playback(end_action="stop"))
    assert not p.scheduler.queued_slides
    assert p.scheduler.exhausted
    assert not p.scheduler._auto_topup_due()


def test_choosing_auto_mode_starts_idle_playback(playback):
    p = playback
    assert not p.scheduler.enabled
    _auto(p)
    assert p.scheduler.enabled
    run(p.scheduler._async_tick())
    assert p.scheduler.current_screen.name == "pick0"


def test_active_hours_hold_auto_picks_overnight(playback):
    p = playback
    run(p.scheduler.async_set_auto({"active_hours": {"after": "07:00", "before": "22:00"}}))
    p.now[0] = p.now[0].replace(hour=23)
    _auto(p)
    run(p.scheduler._async_tick())
    assert p.show.await_count == 0
    p.now[0] += timedelta(hours=8)
    run(p.scheduler._async_tick())
    assert p.scheduler.current_screen.name == "pick0"


def test_cloud_delivery_keeps_auto_picks_on_the_queue_interval(playback):
    p = playback
    p.entry.runtime_data.cloud = SimpleNamespace(
        async_sync_interval=AsyncMock(), delivery_deadline=None,
        async_expire_delivery=AsyncMock(),
    )
    add(p, "hand")
    run(p.scheduler.async_set_playback(interval=600))
    run(p.scheduler.async_set_enabled(True))
    run(p.scheduler.async_set_auto({"cadence": "interval", "interval": 7200}))
    _auto(p)
    assert p.scheduler.cycle_seconds == 600


def test_repeat_after_auto_loops_shown_picks_as_history(playback):
    p = playback
    run(p.scheduler.async_set_enabled(True))
    _auto(p)
    run(p.scheduler._async_tick())
    assert p.scheduler.current_screen.name == "pick0"
    run(p.scheduler.async_set_playback(end_action="repeat", shuffle=True))
    assert all(item.auto_source is None for item in p.scheduler.queue.items)
    assert not p.scheduler.queue.auto_upcoming


def test_producing_needs_something_showable_now(playback):
    p = playback
    schema = load("render.schema")
    p.now[0] = p.now[0].replace(hour=10, minute=0)
    morning = replace(
        _screen("morning"),
        windows=(schema.TimeWindow(after=time(6), before=time(9)),),
    )
    run(p.scheduler.async_add_to_queue(morning))
    run(p.scheduler.async_set_enabled(True))
    # Outside every queued picture's hours nothing new would reach the frame.
    assert not p.scheduler.producing
    p.now[0] = p.now[0].replace(hour=7)
    assert p.scheduler.producing
    p.scheduler.blocked_reason = "low_battery"
    assert not p.scheduler.producing
