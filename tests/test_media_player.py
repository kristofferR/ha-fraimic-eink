"""Camera wake scheduling without a running Home Assistant instance."""

import asyncio
import sys
import types
from unittest.mock import AsyncMock, Mock

from conftest import load
from test_scheduler import _install_scheduler_stubs


def _player(monkeypatch):
    _install_scheduler_stubs(monkeypatch)
    modules = {}
    for name in (
        "aiohttp", "homeassistant.components", "homeassistant.components.media_source",
        "homeassistant.components.media_player", "homeassistant.helpers.aiohttp_client",
        "homeassistant.helpers.entity_platform", "fraimic.entity", "fraimic.providers.engine",
    ):
        modules[name] = types.ModuleType(name)
        monkeypatch.setitem(sys.modules, name, modules[name])
    media = modules["homeassistant.components.media_player"]
    for name in ("BrowseMedia", "MediaClass", "MediaPlayerEntity", "MediaPlayerState"):
        setattr(media, name, object)
    media.MediaPlayerDeviceClass = types.SimpleNamespace(RECEIVER="receiver")
    media.MediaType = types.SimpleNamespace(IMAGE="image")
    media.MediaPlayerEntityFeature = types.SimpleNamespace(PLAY_MEDIA=1, BROWSE_MEDIA=2, STOP=4)
    media.async_process_play_media_url = None
    modules["homeassistant.helpers.aiohttp_client"].async_get_clientsession = None
    modules["homeassistant.helpers.entity_platform"].AddEntitiesCallback = object
    modules["fraimic.providers.engine"].read_capped = None
    for name in ("PROVIDERS", "available_provider_keys", "build_media_id", "parse_media_id"):
        setattr(sys.modules["fraimic.providers"], name, None)
    for name in ("async_render_and_upload", "begin_external_upload", "finish_external_upload"):
        setattr(sys.modules["fraimic.services"], name, None)
    sys.modules["homeassistant.helpers.event"].async_call_later = None

    class Base:
        def __init__(self, coordinator):
            self.coordinator = coordinator
            self.hass = object()

    modules["fraimic.entity"].FraimicEntity = Base
    sys.modules.pop("fraimic.media_player", None)
    module = load("media_player")
    cloud = types.SimpleNamespace(delivery_deadline=3840, camera_interval=None)
    entry = types.SimpleNamespace(entry_id="frame", runtime_data=types.SimpleNamespace(cloud=cloud))
    player = module.FraimicMediaPlayer(types.SimpleNamespace(config_entry=entry))
    player._camera_entity = "camera.art"
    player._async_show_camera = AsyncMock()
    return module, player


def test_cloud_camera_retries_at_deadline_and_stop_cancels(monkeypatch):
    module, player = _player(monkeypatch)
    timers = []

    def later(_hass, delay, callback):
        cancel = Mock()
        timers.append((delay, callback, cancel))
        return cancel

    monkeypatch.setattr(module, "async_call_later", later)
    monkeypatch.setattr(module.time, "time", lambda: 3600)
    asyncio.run(player._async_camera_tick(None))
    assert timers[0][0] == 240
    player._async_show_camera.assert_not_awaited()
    monkeypatch.setattr(module.time, "time", lambda: 3840)
    asyncio.run(timers[0][1](None))
    player._async_show_camera.assert_awaited_once()
    assert player._camera_retry_unsub is None
    monkeypatch.setattr(module.time, "time", lambda: 3600)
    asyncio.run(player._async_camera_tick(None))
    player._stop_camera_loop()
    timers[-1][2].assert_called_once()
    assert player._camera_retry_unsub is None


def test_overlapping_camera_ticks_capture_only_once(monkeypatch):
    module, player = _player(monkeypatch)
    monkeypatch.setattr(module.time, "time", lambda: 4000)
    captures = []

    async def capture(*_args, **_kwargs):
        captures.append(True)
        await asyncio.sleep(0)

    player._async_show_camera = capture

    async def run():
        await asyncio.gather(player._async_camera_tick(None), player._async_camera_tick(None))

    asyncio.run(run())
    assert captures == [True]
