"""Focused persistence tests for the sleeping-frame send queue."""

from __future__ import annotations

import asyncio
import sys
import types
from unittest.mock import AsyncMock

import pytest
from conftest import load


@pytest.fixture
def send_queue_module(monkeypatch: pytest.MonkeyPatch):
    """Load send_queue with its Home Assistant event surface stubbed."""
    homeassistant = types.ModuleType("homeassistant")
    homeassistant.__path__ = []
    ha_const = types.ModuleType("homeassistant.const")
    ha_const.EVENT_STATE_CHANGED = "state_changed"
    ha_const.STATE_HOME = "home"
    core = types.ModuleType("homeassistant.core")
    core.Event = core.HomeAssistant = core.State = object
    core.callback = lambda function: function
    helpers = types.ModuleType("homeassistant.helpers")
    helpers.__path__ = []
    dispatcher = types.ModuleType("homeassistant.helpers.dispatcher")
    dispatcher.async_dispatcher_send = lambda *_args: None
    event = types.ModuleType("homeassistant.helpers.event")
    event.async_call_later = lambda *_args: None
    storage = types.ModuleType("homeassistant.helpers.storage")
    storage.Store = lambda *_args, **_kwargs: object()
    util = types.ModuleType("homeassistant.util")
    util.__path__ = []
    dt = types.ModuleType("homeassistant.util.dt")
    dt.now = lambda: None

    for name, module in {
        "homeassistant": homeassistant,
        "homeassistant.const": ha_const,
        "homeassistant.core": core,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.dispatcher": dispatcher,
        "homeassistant.helpers.event": event,
        "homeassistant.helpers.storage": storage,
        "homeassistant.util": util,
        "homeassistant.util.dt": dt,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)

    previous = sys.modules.pop("fraimic.send_queue", None)
    try:
        yield load("send_queue")
    finally:
        sys.modules.pop("fraimic.send_queue", None)
        if previous is not None:
            sys.modules["fraimic.send_queue"] = previous


def test_setup_discards_legacy_large_frame_payload(send_queue_module) -> None:
    send_queue = send_queue_module

    class Hass:
        config = types.SimpleNamespace(path=lambda *_parts: "/unused/queue.bin")

        async def async_add_executor_job(self, target, *args):
            return target(*args)

    class Store:
        saved = None

        async def async_load(self):
            return {
                "pending": {
                    "title": "Old queued art",
                    "queued_at": send_queue.time.time(),
                }
            }

        async def async_save(self, data) -> None:
            self.saved = data

    entry = types.SimpleNamespace(
        entry_id="large-frame",
        data={"width": 1440, "height": 2560},
        runtime_data=types.SimpleNamespace(cloud=None),
    )
    queue = send_queue.FraimicSendQueue(Hass(), entry)
    queue._store = Store()
    queue._queued_payload_size = lambda: 1440 * 2560 // 2

    asyncio.run(queue.async_setup())

    assert queue.pending is None
    assert queue._store.saved == {"pending": None}
    assert queue.status == (
        "Discarded queued artwork after the frame format changed; send it again"
    )


def test_queue_rejects_invalid_payload_before_writing(send_queue_module) -> None:
    send_queue = send_queue_module

    class Hass:
        config = types.SimpleNamespace(path=lambda *_parts: "/unused/queue.bin")

        async def async_add_executor_job(self, _target, *_args):
            raise AssertionError("invalid payload must not reach the filesystem")

    entry = types.SimpleNamespace(
        entry_id="small-frame",
        title="Small frame",
        data={"width": 2, "height": 4},
    )
    queue = send_queue.FraimicSendQueue(Hass(), entry)

    with pytest.raises(send_queue.FraimicApiError, match="got 5 bytes, expected 4"):
        asyncio.run(
            queue._async_queue(b"12345", None, "auto", "Art", "hash", "manual")
        )


def test_discard_clears_superseded_pending_send(send_queue_module) -> None:
    send_queue = send_queue_module

    class Hass:
        config = types.SimpleNamespace(path=lambda *_parts: "/unused/queue.bin")

    class Store:
        saved = None

        async def async_save(self, data) -> None:
            self.saved = data

    controller = types.SimpleNamespace(
        submitted_hash="old-hash", async_invalidate=AsyncMock()
    )
    entry = types.SimpleNamespace(
        entry_id="small-frame",
        data={},
        runtime_data=types.SimpleNamespace(temporary_overlays=controller),
    )
    queue = send_queue.FraimicSendQueue(Hass(), entry)
    queue._store = Store()
    queue._pending = {"title": "Older picture", "content_hash": "old-hash"}

    asyncio.run(queue.async_discard())

    assert queue.pending is None
    assert queue._store.saved == {"pending": None}
    assert queue.status == "Idle"
    controller.async_invalidate.assert_awaited_once_with(upload_lock_held=False)


def test_delivered_queue_item_keeps_retained_base(send_queue_module) -> None:
    send_queue = send_queue_module

    class Hass:
        config = types.SimpleNamespace(path=lambda *_parts: "/unused/queue.bin")

    controller = types.SimpleNamespace(
        submitted_hash="delivered-hash", async_invalidate=AsyncMock()
    )
    entry = types.SimpleNamespace(
        entry_id="small-frame",
        data={},
        runtime_data=types.SimpleNamespace(temporary_overlays=controller),
    )
    queue = send_queue.FraimicSendQueue(Hass(), entry)
    queue._store = types.SimpleNamespace(async_save=AsyncMock())
    queue._pending = {"content_hash": "delivered-hash"}

    asyncio.run(queue.async_discard(delivered=True))

    controller.async_invalidate.assert_not_awaited()


def test_queueing_direct_send_discards_scheduler_retry(send_queue_module) -> None:
    send_queue = send_queue_module
    discarded: list[bool] = []

    class Scheduler:
        async def async_discard_pending_retry(self) -> None:
            discarded.append(True)

    class Hass:
        config = types.SimpleNamespace(path=lambda *_parts: "/unused/queue.bin")

        async def async_add_executor_job(self, _target, *_args):
            return None

    class Store:
        async def async_save(self, _data) -> None:
            return None

    entry = types.SimpleNamespace(
        entry_id="small-frame",
        title="Small frame",
        data={"width": 2, "height": 4},
        runtime_data=types.SimpleNamespace(scheduler=Scheduler()),
    )
    queue = send_queue.FraimicSendQueue(Hass(), entry)
    queue._store = Store()
    queue._start_waiting = lambda: None

    asyncio.run(queue._async_queue(b"1234", None, "none", "New", "hash", "manual"))

    assert discarded == [True]


def test_flush_caps_queued_payload_read(
    send_queue_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    send_queue = send_queue_module
    requested_sizes: list[int] = []

    class Hass:
        config = types.SimpleNamespace(path=lambda *_parts: "/unused/queue.bin")

        async def async_add_executor_job(self, target, *args):
            return target(*args)

    class Store:
        saved = None

        async def async_save(self, data) -> None:
            self.saved = data

    class QueuedFile:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, size: int = -1) -> bytes:
            requested_sizes.append(size)
            return b"12345"

    monkeypatch.setattr(
        send_queue, "open", lambda *_args, **_kwargs: QueuedFile(), raising=False
    )
    entry = types.SimpleNamespace(
        entry_id="small-frame",
        data={"width": 2, "height": 4},
        runtime_data=types.SimpleNamespace(),
    )
    queue = send_queue.FraimicSendQueue(Hass(), entry)
    queue._store = Store()
    queue._pending = {
        "title": "Corrupt art",
        "token": 1,
        "queued_at": send_queue.time.time(),
        "has_preview": False,
    }

    asyncio.run(queue._async_flush())

    assert requested_sizes == [send_queue.MAX_BIN_SIZE + 1]
    assert queue.pending is None
    assert queue._store.saved == {"pending": None}


@pytest.mark.parametrize("next_refresh", [None, 900, 4000])
def test_flush_reserves_redraw_time_for_recomposed_briefing(
    send_queue_module, monkeypatch: pytest.MonkeyPatch, tmp_path, next_refresh
) -> None:
    from unittest.mock import Mock

    payload = tmp_path / "queue.bin"
    payload.write_bytes(b"old!")

    class Hass:
        config = types.SimpleNamespace(path=lambda *_parts: str(payload))

        async def async_add_executor_job(self, target, *args):
            return target(*args)

    controller = types.SimpleNamespace(
        base=(b"art!", b"preview", "none"),
        art=None,
        title="Art",
        inherit=True,
        candidate_valid_until=1029,
        signature=lambda *_args: "active",
        async_recompose_pending=AsyncMock(
            return_value=((b"new!", None, "none"), "active", 1)
        ),
    )
    client = types.SimpleNamespace(upload_image=AsyncMock())
    runtime = types.SimpleNamespace(
        upload_lock=asyncio.Lock(), temporary_overlays=controller, client=client,
        coordinator=types.SimpleNamespace(data={"display": {"next_refresh": next_refresh}}),
    )
    entry = types.SimpleNamespace(
        entry_id="frame",
        title="Frame",
        data={"width": 2, "height": 4},
        options={"power_mode": "minimum"},
        runtime_data=runtime,
    )
    queue = send_queue_module.FraimicSendQueue(Hass(), entry)
    queue._pending = {
        "title": "Briefing",
        "token": 1,
        "queued_at": 1000,
        "has_preview": False,
        "content_hash": "queued",
    }
    previous_probe = Mock()
    queue._unsub_probe = previous_probe
    schedule = Mock()
    monkeypatch.setattr(send_queue_module, "async_call_later", schedule)
    monkeypatch.setattr(send_queue_module.time, "time", lambda: 1000)

    asyncio.run(queue._async_flush())

    client.upload_image.assert_not_awaited()
    previous_probe.assert_called_once()
    schedule.assert_called_once_with(queue._hass, 29, queue._async_probe)
    assert queue.pending is not None


def test_cloud_setup_discards_lan_queue_without_starting_probes(send_queue_module):
    from unittest.mock import AsyncMock, Mock

    hass = types.SimpleNamespace(config=types.SimpleNamespace(path=lambda *parts: "/unused"))
    entry = types.SimpleNamespace(
        entry_id="frame", data={}, runtime_data=types.SimpleNamespace(cloud=object())
    )
    queue = send_queue_module.FraimicSendQueue(hass, entry)
    queue._store = types.SimpleNamespace(
        async_load=AsyncMock(return_value={"pending": {"title": "Old art"}}),
        async_save=AsyncMock(),
    )
    queue._start_waiting = Mock()
    asyncio.run(queue.async_setup())
    queue._start_waiting.assert_not_called()
    queue._store.async_save.assert_awaited_once_with({"pending": None})
    assert queue.pending is None


@pytest.mark.parametrize("fails", [False, True])
def test_hybrid_setup_migrates_local_queue_without_losing_failed_send(
    send_queue_module, tmp_path, fails,
):
    from unittest.mock import AsyncMock, Mock

    payload = tmp_path / "queue.bin"
    payload.write_bytes(b"1234")
    payload.with_suffix(".bin.png").write_bytes(b"calibrated-preview")

    class Hass:
        config = types.SimpleNamespace(path=lambda *parts: str(payload))

        async def async_add_executor_job(self, target, *args):
            return target(*args)

    pending = {
        "title": "Scheduled picture", "queued_at": send_queue_module.time.time(), "has_preview": True,
    }
    cloud = types.SimpleNamespace(
        async_deliver=AsyncMock(side_effect=RuntimeError("cloud unavailable") if fails else None),
    )
    power = types.SimpleNamespace(async_invalidate_display=AsyncMock())
    entry = types.SimpleNamespace(
        entry_id="frame", data={"width": 2, "height": 4},
        options={"delivery_mode": "hybrid"},
        runtime_data=types.SimpleNamespace(cloud=cloud, power=power),
    )
    queue = send_queue_module.FraimicSendQueue(Hass(), entry)
    queue._store = types.SimpleNamespace(
        async_load=AsyncMock(return_value={"pending": pending}), async_save=AsyncMock(),
    )
    queue._start_waiting = Mock()
    if fails:
        with pytest.raises(RuntimeError, match="cloud unavailable"):
            asyncio.run(queue.async_setup())
        assert queue.pending == pending
        queue._store.async_save.assert_not_awaited()
        power.async_invalidate_display.assert_not_awaited()
    else:
        asyncio.run(queue.async_setup())
        assert queue.pending is None
        queue._store.async_save.assert_awaited_once_with({"pending": None})
        power.async_invalidate_display.assert_awaited_once()
        assert queue.status == "Queued for cloud delivery"
    cloud.async_deliver.assert_awaited_once_with(b"1234", title="Scheduled picture", preview_png=b"calibrated-preview")
    queue._start_waiting.assert_not_called()


def test_hybrid_migration_defers_retained_overlay_to_fresh_composition(send_queue_module, tmp_path):
    from unittest.mock import AsyncMock

    payload = tmp_path / "queue.bin"
    payload.write_bytes(b"old!")

    class Hass:
        config = types.SimpleNamespace(path=lambda *parts: str(payload))

        async def async_add_executor_job(self, target, *args):
            return target(*args)

    events = []
    controller = types.SimpleNamespace(
        base=(b"art!", b"preview", "none"), submitted_hash="overlay", dirty=False
    )

    async def mark_dirty():
        controller.dirty = True
        events.append("dirty persisted")

    controller.async_mark_dirty = AsyncMock(side_effect=mark_dirty)
    cloud = types.SimpleNamespace(async_deliver=AsyncMock())
    entry = types.SimpleNamespace(
        entry_id="frame", data={"width": 2, "height": 4}, options={"delivery_mode": "hybrid"},
        runtime_data=types.SimpleNamespace(cloud=cloud, temporary_overlays=controller),
    )
    queue = send_queue_module.FraimicSendQueue(Hass(), entry)
    queue._store = types.SimpleNamespace(
        async_load=AsyncMock(return_value={"pending": {"queued_at": send_queue_module.time.time(), "content_hash": "overlay"}}),
        async_save=AsyncMock(side_effect=lambda _data: events.append("queue discarded")),
    )
    asyncio.run(queue.async_setup())
    assert controller.dirty
    controller.async_mark_dirty.assert_awaited_once()
    assert events == ["dirty persisted", "queue discarded"]
    assert queue.pending is None
    cloud.async_deliver.assert_not_awaited()
