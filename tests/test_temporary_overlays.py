"""Temporary overlays keep the same art across expiry, restarts and previews."""

import asyncio
import copy
import sys
import types
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import numpy as np
import pytest

from conftest import load
from test_render_display import _install_ha_stubs


@pytest.fixture
def controller(monkeypatch):
    _install_ha_stubs(monkeypatch)
    saved = {}

    class Store:
        def __init__(self, _hass, _version, key):
            self.key = key

        async def async_load(self):
            return copy.deepcopy(saved.get(self.key))

        async def async_save(self, value):
            saved[self.key] = copy.deepcopy(value)

    storage = types.ModuleType("homeassistant.helpers.storage")
    storage.Store = Store
    event = types.ModuleType("homeassistant.helpers.event")
    event.async_track_time_interval = lambda *_args: lambda: None
    monkeypatch.setitem(sys.modules, "homeassistant.helpers.storage", storage)
    monkeypatch.setitem(sys.modules, "homeassistant.helpers.event", event)
    for name in (
        "fraimic.temporary_overlays",
        "fraimic.overlays",
        "fraimic.render.fetch",
    ):
        monkeypatch.delitem(sys.modules, name, raising=False)
    module = load("temporary_overlays")
    clock = SimpleNamespace(now=1000.0)
    monkeypatch.setattr(module.time, "time", lambda: clock.now)

    async def executor(fn, *args):
        return fn(*args)

    hass = SimpleNamespace(
        data={},
        async_add_executor_job=executor,
        states=SimpleNamespace(get=lambda _id: None),
    )
    entry = SimpleNamespace(
        entry_id="large",
        data={"width": 8, "height": 4},
        options={"rotation": 90},
        runtime_data=SimpleNamespace(
            upload_lock=asyncio.Lock(), scheduler=None, screen_preview_image=None
        ),
    )
    obj = module.TemporaryOverlays(hass, entry)
    entry.runtime_data.temporary_overlays = obj
    packed = load("image_convert")._pack_nibbles(
        np.arange(32, dtype=np.uint8) % 6, 8, 4
    )
    obj.base = (packed, b"thumbnail", "bayer")
    obj.title = "Original art"
    obj.last_signature = obj.signature()
    return module, obj, clock, saved


def overlay(text="Morning"):
    return {"id": "brief", "type": "text", "options": {"literal": text}}


def test_expiry_and_restart_keep_clean_art(controller):
    module, obj, clock, _ = controller
    obj.async_refresh = AsyncMock(return_value={"displayed": True})

    async def run():
        base = obj.base
        await obj.async_show([overlay()], 60)
        signature = obj.signature()
        await obj.async_accept(
            base, {"title": "Original"}, "Original", True, signature, "composite-hash"
        )
        clock.now += 61
        restored = module.TemporaryOverlays(obj.hass, obj.entry)
        await restored.async_setup()
        assert not restored.active
        assert restored.holds_playback  # removal is still due after restart
        rendered, signature, count = await restored.async_compose(
            restored.base, restored.art
        )
        assert rendered[0] == base[0]
        assert count == 0
        assert signature != restored.last_signature
        assert restored.title == "Original"

    asyncio.run(run())


def test_manual_art_change_becomes_the_restoration_base(controller):
    _, obj, clock, _ = controller
    obj.async_refresh = AsyncMock(return_value={"displayed": True})

    async def run():
        await obj.async_show([overlay()], 60)
        new_base = (bytes(reversed(obj.base[0])), b"new thumbnail", "none")
        await obj.async_accept(
            new_base, None, "New art", True, obj.signature(), "new-composite"
        )
        clock.now += 61
        rendered, _, count = await obj.async_compose(obj.base)
        assert rendered is new_base
        assert count == 0
        assert obj.title == "New art"

    asyncio.run(run())


def test_preview_does_not_activate_save_or_send(controller, monkeypatch):
    _, obj, _, saved = controller
    obj.async_compose = AsyncMock(
        return_value=((b"preview buffer", b"png", "none"), "sig", 1)
    )
    display = types.ModuleType("fraimic.render.display")
    previews = []
    display._set_screen_preview = lambda _runtime, png, mode: previews.append(
        (png, mode)
    )
    monkeypatch.setitem(sys.modules, "fraimic.render.display", display)
    base = obj.base
    result = asyncio.run(obj.async_show([overlay()], 60, preview_only=True))
    assert result == {"uploaded": False, "preview_only": True, "overlay_count": 1}
    assert not obj.active
    assert obj.base is base
    assert not saved
    assert previews == [(b"png", "none")]


def test_preview_restores_active_composition_deadline(controller, monkeypatch):
    _, obj, _, _ = controller
    obj.temporary = [overlay("Active briefing")]
    obj.expires_at = 2000
    obj.composed_valid_until = 1030

    async def compose(*_args):
        obj.composed_valid_until = None
        return (b"preview buffer", b"png", "none"), "sig", 1

    obj.async_compose = compose
    display = types.ModuleType("fraimic.render.display")
    display._set_screen_preview = lambda *_args: None
    monkeypatch.setitem(sys.modules, "fraimic.render.display", display)

    asyncio.run(obj.async_show([overlay("Preview")], 60, preview_only=True))

    assert obj.temporary == [overlay("Active briefing")]
    assert obj.expires_at == 2000
    assert obj.composed_valid_until == 1030


def test_pending_send_is_recomposed_after_expiry(controller):
    _, obj, clock, _ = controller
    obj.async_refresh = AsyncMock(return_value={"displayed": False})

    async def run():
        await obj.async_show([overlay()], 60)
        await obj.async_accept(obj.base, None, "Art", True, obj.signature(), "queued")
        clock.now += 61
        rendered, signature, count = await obj.async_recompose_pending(
            {"content_hash": "queued"}
        )
        assert rendered == obj.base
        assert count == 0
        assert signature == "[]"
        assert await obj.async_recompose_pending({"content_hash": "unrelated"}) is None

    asyncio.run(run())


def test_composition_uses_full_panel_pixels_not_thumbnail(controller, monkeypatch):
    module, obj, _, _ = controller
    from PIL import Image
    import io

    obj.temporary = [module.normalize_overlay(overlay())]
    obj.expires_at = 2000
    seen = []

    async def compose(_hass, _entry, png, _art, *, overlays, snapshot_deadlines=None):
        seen.append(Image.open(io.BytesIO(png)).size)
        return png, len(overlays)

    monkeypatch.setattr(module, "async_apply_frame_overlays", compose)
    display = types.ModuleType("fraimic.render.display")
    display._NEUTRAL_OVERRIDES = {}
    services = types.ModuleType("fraimic.services")
    services.async_convert_for_entry = AsyncMock(return_value=obj.base)
    monkeypatch.setitem(sys.modules, "fraimic.render.display", display)
    monkeypatch.setitem(sys.modules, "fraimic.services", services)
    asyncio.run(obj.async_compose(obj.base))
    assert seen == [(4, 8)]
    assert obj.base[1] == b"thumbnail"


def test_visibility_boundaries_require_refresh_even_without_temporary_overlay(
    controller, monkeypatch
):
    module, obj, _, _ = controller
    value = module.normalize_overlay(
        {**overlay(), "visibility": {"mode": "times", "from": "06:00", "to": "09:00"}}
    )
    obj.hass.data["fraimic"] = {
        "overlays": SimpleNamespace(for_frame=lambda _id: [value])
    }
    monkeypatch.setattr(module.dt_util, "now", lambda: datetime(2026, 9, 19, 5, 59))
    obj.last_signature = obj.signature()
    assert not obj.holds_playback
    monkeypatch.setattr(module.dt_util, "now", lambda: datetime(2026, 9, 19, 6, 0))
    assert obj.holds_playback
    obj.last_signature = obj.signature()
    monkeypatch.setattr(module.dt_util, "now", lambda: datetime(2026, 9, 19, 9, 1))
    assert obj.holds_playback


def test_unknown_or_invalidated_artwork_never_restores_an_old_picture(controller):
    module, obj, _, saved = controller

    async def run():
        await obj.async_invalidate()
        assert obj.base is None
        with pytest.raises(module.HomeAssistantError, match="clean artwork"):
            await obj.async_show([overlay()], 60)
        assert not obj.holds_playback

    asyncio.run(run())


def install_delivery(monkeypatch, obj):
    """Exercise real timer/acceptance behavior with a transport boundary stub."""
    calls = []

    async def deliver(*_args, **_kwargs):
        calls.append(copy.deepcopy(obj.visible()))
        await obj.async_accept(
            obj.base, obj.art, obj.title, obj.inherit, obj.signature(), "pixels"
        )
        return {"displayed": True}

    services = types.ModuleType("fraimic.services")
    services.async_render_and_upload = deliver
    monkeypatch.setitem(sys.modules, "fraimic.services", services)
    return calls


def test_active_overlay_rereads_data_on_interval_without_extending_expiry(
    controller, monkeypatch
):
    _, obj, clock, _ = controller
    calls = install_delivery(monkeypatch, obj)

    async def run():
        await obj.async_show([overlay()], 180, refresh_interval=60)
        deadline = obj.expires_at
        assert len(calls) == 1
        clock.now += 30
        await obj._async_tick()
        assert len(calls) == 1
        clock.now += 30
        await obj._async_tick()
        assert len(calls) == 2  # same config still fetches current widget data
        assert obj.expires_at == deadline
        clock.now = deadline
        await obj._async_tick()
        assert calls[-1] == []  # remove at the original end time
        assert not obj.active
        count = len(calls)
        clock.now += 60
        await obj._async_tick()
        assert len(calls) == count

    asyncio.run(run())


def test_visibility_change_bypasses_refresh_interval(controller, monkeypatch):
    module, obj, clock, _ = controller
    calls = install_delivery(monkeypatch, obj)
    value = module.normalize_overlay(
        {
            **overlay(),
            "visibility": {"mode": "times", "from": "06:00", "to": "09:00"},
        }
    )
    obj.temporary = [value]
    obj.expires_at = 5000
    obj.refresh_interval = 3600
    obj._next_refresh_at = 4600
    monkeypatch.setattr(module.dt_util, "now", lambda: datetime(2026, 9, 19, 8, 50))
    obj.last_signature = obj.signature()
    monkeypatch.setattr(module.dt_util, "now", lambda: datetime(2026, 9, 19, 9, 1))
    clock.now = 1090

    asyncio.run(obj._async_tick())

    assert calls == [[]]


def test_duplicate_refresh_does_not_rewrite_retained_framebuffer(controller):
    module, obj, _, _ = controller

    async def run():
        obj.temporary = [module.normalize_overlay(overlay())]
        obj.expires_at = 2000
        signature = obj.signature()
        await obj.async_accept(
            obj.base, None, obj.title, True, signature, "same-pixels"
        )
        obj._store.async_save = AsyncMock()
        obj._next_refresh_at = 1120
        await obj.async_accept(
            obj.base, None, obj.title, True, signature, "same-pixels"
        )
        obj._store.async_save.assert_not_awaited()

    asyncio.run(run())


def test_accept_uses_incoming_permanent_overlay_preference(controller):
    module, obj, _, _ = controller
    permanent = module.normalize_overlay(overlay("Permanent"))
    obj.hass.data["fraimic"] = {
        "overlays": SimpleNamespace(for_frame=lambda _id: [permanent])
    }

    asyncio.run(
        obj.async_accept(
            obj.base, None, obj.title, False, obj.signature(False), "same-pixels"
        )
    )
    assert not obj.dirty


def test_mark_dirty_requests_immediate_persisted_refresh(controller):
    _, obj, _, _ = controller
    obj._next_refresh_at = 2000
    obj._store.async_save = AsyncMock()

    asyncio.run(obj.async_mark_dirty())

    assert obj.dirty
    assert obj._next_refresh_at == 0
    obj._store.async_save.assert_awaited_once()


def test_busy_scheduler_deferral_requests_immediate_persisted_retry(
    controller, monkeypatch
):
    _, obj, _, _ = controller
    calls = install_delivery(monkeypatch, obj)
    scheduler = SimpleNamespace(
        busy=True,
        external_upload_active=False,
        begin_external_upload=lambda: None,
        finish_external_upload=lambda **_kwargs: None,
    )
    obj.entry.runtime_data.scheduler = scheduler
    obj._next_refresh_at = 2000
    obj._store.async_save = AsyncMock()

    async def run():
        assert (await obj.async_refresh())["deferred"]
        assert obj.dirty
        assert obj._next_refresh_at == 0
        obj._store.async_save.assert_awaited_once()
        scheduler.busy = False
        await obj._async_tick()
        assert len(calls) == 1

    asyncio.run(run())


def test_briefing_deadline_triggers_refresh_and_survives_restart(
    controller, monkeypatch
):
    module, obj, clock, _ = controller
    calls = install_delivery(monkeypatch, obj)
    obj.temporary = [module.normalize_overlay(overlay())]
    obj.expires_at = 2000
    obj.refresh_interval = 0
    obj._next_refresh_at = 2000
    obj.composed_valid_until = 1030
    obj.last_signature = obj.signature()

    async def run():
        await obj._async_save()
        restored = module.TemporaryOverlays(obj.hass, obj.entry)
        await restored.async_setup()
        assert restored.composed_valid_until == 1030
        clock.now = 1029
        await obj._async_tick()
        assert not calls
        clock.now = 1030
        await obj._async_tick()
        assert len(calls) == 1

    asyncio.run(run())


def test_expiry_bypasses_refresh_retry_guard(controller, monkeypatch):
    _, obj, clock, _ = controller
    calls = install_delivery(monkeypatch, obj)

    async def run():
        await obj.async_show([overlay()], 30)
        assert obj._retry_at == 1060
        clock.now = 1030
        await obj._async_tick()
        assert calls[-1] == []

    asyncio.run(run())


def test_failed_delivery_retries_before_normal_refresh(controller, monkeypatch):
    module, obj, clock, _ = controller
    calls = 0

    async def deliver(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise module.HomeAssistantError("offline")
        await obj.async_accept(
            obj.base, obj.art, obj.title, obj.inherit, obj.signature(), "pixels"
        )
        return {"displayed": True}

    services = types.ModuleType("fraimic.services")
    services.async_render_and_upload = deliver
    monkeypatch.setitem(sys.modules, "fraimic.services", services)

    async def run():
        with pytest.raises(module.HomeAssistantError, match="offline"):
            await obj.async_show([overlay()], 7200, refresh_interval=3600)
        assert obj._next_refresh_at == obj._retry_at == 1060
        clock.now = 1059
        await obj._async_tick()
        assert calls == 1
        clock.now = 1060
        await obj._async_tick()
        assert calls == 2

    asyncio.run(run())


def test_update_coalesces_latest_content_and_cannot_revive_expired_overlay(
    controller, monkeypatch
):
    _, obj, clock, _ = controller
    calls = install_delivery(monkeypatch, obj)

    async def run():
        await obj.async_show([overlay("1/6")], 120)
        deadline = obj.expires_at
        clock.now += 5
        assert (await obj.async_update([overlay("2/6")]))["deferred"]
        clock.now += 5
        assert (await obj.async_update([overlay("3/6")]))["deferred"]
        assert len(calls) == 1
        clock.now += 50
        await obj._async_tick()
        assert len(calls) == 2
        assert calls[-1][0]["options"]["literal"] == "3/6"
        assert obj.expires_at == deadline
        clock.now = deadline
        assert (await obj.async_update([overlay("4/6")]))["active"] is False
        await obj._async_tick()
        assert calls[-1] == []

    asyncio.run(run())


def test_refresh_preference_survives_restart_and_zero_still_expires(
    controller, monkeypatch
):
    module, obj, clock, _ = controller
    calls = install_delivery(monkeypatch, obj)

    async def run():
        await obj.async_show([overlay()], 180, refresh_interval=0)
        restored = module.TemporaryOverlays(obj.hass, obj.entry)
        await restored.async_setup()
        assert restored.refresh_interval == 0
        assert restored.expires_at == obj.expires_at
        clock.now += 60
        await obj._async_tick()
        assert len(calls) == 1
        clock.now = obj.expires_at
        await obj._async_tick()
        assert calls[-1] == []

    asyncio.run(run())


@pytest.mark.parametrize("interval", [True, -1, 1, 59, 3601, "60"])
def test_invalid_refresh_interval_is_rejected(controller, interval):
    _, obj, _, _ = controller
    with pytest.raises(ValueError, match="Refresh interval"):
        asyncio.run(obj.async_show([overlay()], 60, refresh_interval=interval))


def test_briefing_cannot_be_saved_as_permanent_overlay(controller):
    _, obj, _, _ = controller
    overlays = load("overlays")
    manager = overlays.OverlayManager(obj.hass)
    briefing = {
        "type": "briefing",
        "options": {"entity": "sensor.morning_brief"},
    }

    with pytest.raises(ValueError, match="temporary overlay"):
        asyncio.run(manager.async_replace(obj.entry.entry_id, [briefing]))
    assert "briefing" not in overlays.PERMANENT_OVERLAY_TYPES


@pytest.mark.parametrize(
    "payload,empty",
    [
        ({"text": " \n "}, True),
        ({"error": "Unavailable"}, True),
        ({"text": "0"}, False),
        ({"value": 0}, False),
    ],
)
def test_empty_or_failed_content_can_disappear_without_hiding_zero(
    controller, payload, empty
):
    assert load("overlays")._empty_payload(payload) is empty


def test_invalidation_discards_only_the_pending_composite_for_that_artwork(controller):
    _, obj, _, _ = controller
    obj.submitted_hash = "old composite"
    queue = SimpleNamespace(
        pending={"content_hash": "old composite"}, async_discard=AsyncMock()
    )
    obj.entry.runtime_data.send_queue = queue
    asyncio.run(obj.async_invalidate())
    queue.async_discard.assert_awaited_once()
    assert obj.base is None
