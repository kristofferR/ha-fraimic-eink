"""Focused persistence tests for the sleeping-frame send queue."""

from __future__ import annotations

import asyncio
import sys
import types

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
