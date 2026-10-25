"""Real HA wiring around the companion, with fake inference providers."""

from __future__ import annotations

import asyncio
import hashlib
import io
import wave
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
from PIL import Image
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fraimic.backend_voice import VoiceJobs, pcm_from_wav
from custom_components.fraimic.backend_errors import BackendUnavailable
from custom_components.fraimic.const import CONF_DELIVERY_MODE, DELIVERY_BACKEND
from custom_components.fraimic.diagnostics import async_get_config_entry_diagnostics
from custom_components.fraimic.http_api import _frame_payload, _player_payload
from custom_components.fraimic.library import get_library
from custom_components.fraimic.local_backend import (
    CONF_BACKEND_TOKEN, CONF_BACKEND_URL, CONF_VOICE_MODE, LocalBackend,
)
from custom_components.fraimic.services import async_render_and_upload

from .conftest import setup_entry


def audio_fixture() -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\0\0" * 16000)
    return output.getvalue()


def image_fixture() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (160, 120), "white").save(output, "PNG")
    return output.getvalue()


@pytest.fixture
async def backend_entry(hass: HomeAssistant, frame_client: dict[str, AsyncMock],
                        config_entry: MockConfigEntry, tmp_path: Path):
    hass.config.config_dir = str(tmp_path)
    entry = MockConfigEntry(domain=config_entry.domain, version=config_entry.version,
                            unique_id=config_entry.unique_id, data=dict(config_entry.data),
                            options={**config_entry.options, CONF_DELIVERY_MODE: DELIVERY_BACKEND,
                                     CONF_BACKEND_URL: "http://companion.example:8443",
                                     CONF_BACKEND_TOKEN: "private-fixture-bridge-token" * 2,
                                     CONF_VOICE_MODE: "art", "mode": "none"})
    with patch.object(LocalBackend, "request", new_callable=AsyncMock) as request:
        request.return_value = {"busy": False, "jobs": []}
        await setup_entry(hass, entry)
        yield entry, request


async def test_voice_creates_one_original_and_freezes_result_across_restart(
    hass: HomeAssistant, backend_entry: Any,
) -> None:
    entry, _ = backend_entry
    jobs = entry.runtime_data.backend.voice
    overlays = entry.runtime_data.temporary_overlays
    old_base = (b"\x11" * 960_000, None, "none")
    overlays.base, overlays.dirty = old_base, True
    ident, audio = "a" * 32, audio_fixture()
    original = image_fixture()
    with (
        patch.object(VoiceJobs, "_transcribe", new_callable=AsyncMock, return_value="A quiet forest") as stt,
        patch.object(VoiceJobs, "_generate", new_callable=AsyncMock, return_value=(original, {"provider": "fake", "model": "fixture", "prompt": "A quiet forest"})) as generate,
        patch.object(entry.runtime_data.client, "upload_image", new_callable=AsyncMock) as push,
    ):
        a, b = await asyncio.gather(jobs.async_process(ident, audio, "portrait"),
                                    jobs.async_process(ident, audio, "portrait"))
        assert a == b and len(a) == 960_000
        assert overlays.base is None
        await overlays._async_tick()
        stt.assert_awaited_once()
        generate.assert_awaited_once()
        push.assert_not_awaited()
        library = get_library(hass)
        assert library is not None
        created = [image for image in library.images.values() if image.creation]
        assert len(created) == 1
        assert created[0].creation is not None
        assert created[0].creation.transcript == "A quiet forest"
        assert created[0].creation.metadata is not None
        assert created[0].creation.metadata["model"] == "fixture"
        assert await hass.async_add_executor_job(library.original_path(created[0]).read_bytes) == original
        restarted = VoiceJobs(hass, entry)
        await restarted.async_setup()
        overlays.base, overlays.dirty = old_base, True
        assert await restarted.async_process(ident, audio, "portrait") == a
        assert overlays.base is None
        await overlays._async_tick()
        generate.assert_awaited_once()
        assert entry.runtime_data.displayed_preview is None
        assert not entry.runtime_data.scheduler.external_upload_active


async def test_uncertain_generation_is_not_repeated_after_ha_restart(
    hass: HomeAssistant, backend_entry: Any,
) -> None:
    entry, _ = backend_entry
    jobs = entry.runtime_data.backend.voice
    ident, audio = "b" * 32, audio_fixture()
    with (
        patch.object(VoiceJobs, "_transcribe", new_callable=AsyncMock, return_value="A forest"),
        patch.object(VoiceJobs, "_generate", new_callable=AsyncMock, side_effect=TimeoutError) as generate,
    ):
        with pytest.raises(HomeAssistantError):
            await jobs.async_process(ident, audio, "portrait")
        assert jobs.jobs[ident]["outcome"] == "uncertain"
        assert not entry.runtime_data.scheduler.external_upload_active
        restarted = VoiceJobs(hass, entry)
        await restarted.async_setup()
        # A same-ID reconciliation gives a result card, never a second charge.
        packed = await restarted.async_process(ident, audio, "portrait")
        assert len(packed) == 960_000
        generate.assert_awaited_once()


async def test_voice_hold_prevents_queue_send_and_releases_on_failure(
    hass: HomeAssistant, backend_entry: Any,
) -> None:
    entry, _ = backend_entry
    jobs = entry.runtime_data.backend.voice
    started, release = asyncio.Event(), asyncio.Event()
    overlays = entry.runtime_data.temporary_overlays
    old_base = (b"\x11" * 960_000, None, "none")
    overlays.base = old_base

    async def stt(pcm: bytes) -> str:
        started.set()
        await release.wait()
        raise HomeAssistantError("No transcript")

    with patch.object(VoiceJobs, "_transcribe", side_effect=stt):
        task = asyncio.create_task(jobs.async_process("c" * 32, audio_fixture(), "portrait"))
        await started.wait()
        assert entry.runtime_data.scheduler.external_upload_active
        with patch("custom_components.fraimic.scheduler.async_show_screen", new_callable=AsyncMock) as show:
            await entry.runtime_data.scheduler._async_rotate(force=True)
            show.assert_not_awaited()
        release.set()
        with pytest.raises(HomeAssistantError):
            await task
    assert not entry.runtime_data.scheduler.external_upload_active
    assert overlays.base == old_base


async def test_migrated_backend_delivery_holds_overdue_playback_after_startup(
    hass: HomeAssistant, backend_entry: Any,
) -> None:
    from custom_components.fraimic.render.schema import SCREEN_SCHEMA, screen_from_dict

    entry, request = backend_entry
    scheduler = entry.runtime_data.scheduler
    screen = screen_from_dict(SCREEN_SCHEMA({
        "name": "Next picture", "kind": "picture", "library_image": "next",
    }), "next")
    await scheduler.async_add_to_queue(screen)
    await scheduler.async_set_enabled(True, rotate=False)
    queue = entry.runtime_data.send_queue
    await queue._async_queue(b"\x11" * 960_000, None, "none", "Manual picture", "manual", "manual")
    request.reset_mock()
    with (
        patch("custom_components.fraimic.async_register_panel"),
        patch("custom_components.fraimic._async_warm_catalogs"),
        patch("custom_components.fraimic.async_start_sweep", return_value=lambda: None),
        patch("custom_components.fraimic.scheduler.async_show_screen", new_callable=AsyncMock) as show,
    ):
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        runtime = entry.runtime_data
        assert runtime.send_queue.pending is None
        assert runtime.scheduler._hold_until > dt_util.utcnow()
        assert not runtime.backend.acceptance_pending
        await runtime.scheduler._async_tick()
        show.assert_not_awaited()
    deliveries = [call for call in request.await_args_list if call.args[:2] == ("POST", "/bridge/delivery")]
    assert len(deliveries) == 1
    assert entry.runtime_data.displayed_preview is None
    assert entry.runtime_data.power.last_hash is None


async def test_backend_acceptance_survives_restart_before_scheduler_is_ready(
    hass: HomeAssistant, backend_entry: Any,
) -> None:
    entry, request = backend_entry
    scheduler = entry.runtime_data.scheduler
    entry.runtime_data.scheduler = None
    try:
        await entry.runtime_data.backend.async_deliver(b"\x11" * 960_000)
        restarted = LocalBackend(hass, entry)
        await restarted.async_setup()
        assert restarted.acceptance_pending
        entry.runtime_data.backend = restarted
    finally:
        entry.runtime_data.scheduler = scheduler
    request.reset_mock()
    await restarted.async_status()
    assert scheduler._hold_until > dt_util.utcnow()
    assert not restarted.acceptance_pending
    assert not any(call.args[:2] == ("POST", "/bridge/delivery") for call in request.await_args_list)
    restored = LocalBackend(hass, entry)
    await restored.async_setup()
    assert not restored.acceptance_pending


async def test_pull_delivery_never_pushes_or_confirms_display(
    hass: HomeAssistant, backend_entry: Any,
) -> None:
    entry, request = backend_entry
    with patch.object(entry.runtime_data.client, "upload_image", new_callable=AsyncMock) as push:
        result = await async_render_and_upload(hass, entry, image_fixture())
        assert result["backend_queued"] is True
        assert result["uploaded"] is result["displayed"] is False
        push.assert_not_awaited()
        assert entry.runtime_data.displayed_preview is None
        assert entry.runtime_data.power.last_hash is None
    calls = request.await_args_list
    assert any(call.args[:2] == ("POST", "/bridge/delivery") for call in calls)
    assert any(call.args[:2] == ("PUT", "/bridge/schedule") for call in calls)


@pytest.mark.parametrize("first_expiry,retry_expiry", [(None, None), (7200, 7200), (7200, 10800)])
async def test_ambiguous_delivery_reuses_persisted_identity(
    hass: HomeAssistant, backend_entry: Any, first_expiry: int | None, retry_expiry: int | None,
) -> None:
    entry, request = backend_entry
    backend = entry.runtime_data.backend
    request.side_effect = [HomeAssistantError("connection lost"), {}, {}]
    now = int(dt_util.utcnow().timestamp())
    with pytest.raises(HomeAssistantError):
        await backend.async_deliver(b"\x11" * 960_000,
                                    expires_at=now + first_expiry if first_expiry is not None else None)
    ident = backend.pending["id"]
    restarted = LocalBackend(hass, entry)
    await restarted.async_setup()
    await restarted.async_deliver(b"\x11" * 960_000,
                                  expires_at=now + retry_expiry if retry_expiry is not None else None)
    assert restarted.pending is not None
    assert restarted.pending["id"] == ident
    deliveries = [call for call in request.await_args_list if call.args[:2] == ("POST", "/bridge/delivery")]
    assert deliveries[-1].kwargs["job_id"] == ident


@pytest.mark.parametrize("accepted_expiry,requested_expiry,new_identity", [
    (-60, None, True),
    (7200, None, False),
    (7200, 7200.9, False),
    (7200, 10800, True),
    (7200, 3600, True),
])
async def test_accepted_delivery_identity_tracks_expiry_after_restart(
    hass: HomeAssistant, backend_entry: Any, accepted_expiry: int,
    requested_expiry: float | None, new_identity: bool,
) -> None:
    entry, request = backend_entry
    backend = entry.runtime_data.backend
    now = int(dt_util.utcnow().timestamp())
    request.return_value = {"expires_at": now + accepted_expiry}
    await backend.async_deliver(b"\x11" * 960_000)
    ident = backend.pending["id"]
    restarted = LocalBackend(hass, entry)
    await restarted.async_setup()
    await restarted.async_deliver(b"\x11" * 960_000,
                                  expires_at=now + requested_expiry if requested_expiry is not None else None)
    assert restarted.pending is not None
    assert (restarted.pending["id"] != ident) is new_identity
    deliveries = [call for call in request.await_args_list if call.args[:2] == ("POST", "/bridge/delivery")]
    assert deliveries[-1].kwargs["job_id"] == restarted.pending["id"]


async def test_diagnostics_redact_backend_credential(hass: HomeAssistant, backend_entry: Any) -> None:
    import json
    entry, _ = backend_entry
    dumped = json.dumps(await async_get_config_entry_diagnostics(hass, entry))
    assert entry.options[CONF_BACKEND_TOKEN] not in dumped
    assert entry.options[CONF_BACKEND_URL] not in dumped


async def test_voice_rejects_changed_content_and_invalid_wav(backend_entry: Any) -> None:
    entry, _ = backend_entry
    jobs = entry.runtime_data.backend.voice
    audio = audio_fixture()
    with pytest.raises(ValueError):
        await jobs.async_process("d" * 32, audio[:-2], "portrait")
    assert not jobs.jobs
    jobs.jobs["d" * 32] = {"hash": hashlib.sha256(audio).hexdigest(), "orientation": "portrait",
                           "state": "accepted", "created": 9_999_999_999}
    with pytest.raises(HomeAssistantError):
        await jobs.async_process("d" * 32, audio, "landscape")
    assert len(pcm_from_wav(audio)) == 32000


async def test_failed_schedule_survives_restart_and_retries(hass: HomeAssistant, backend_entry: Any) -> None:
    import time
    entry, request = backend_entry
    backend = entry.runtime_data.backend
    request.side_effect = BackendUnavailable("offline")
    deadline = int(time.time() + 7200)
    with pytest.raises(BackendUnavailable):
        await backend.async_schedule(deadline)
    restarted = LocalBackend(hass, entry)
    await restarted.async_setup()
    assert restarted.schedule_pending and restarted.next_wake == deadline
    request.side_effect = None
    request.return_value = {"busy": False, "jobs": []}
    await restarted.async_status()
    assert not restarted.schedule_pending
    assert request.await_args_list[-2].kwargs["payload"] == {"next_image_utc": deadline}


async def test_bridge_auth_is_narrow_and_management_remains_authenticated(
    backend_entry: Any, hass_client_no_auth: Any,
) -> None:
    entry, _ = backend_entry
    client = await hass_client_no_auth()
    headers = {"X-Fraimic-Job": "f" * 32, "X-Fraimic-Orientation": "portrait"}
    assert (await client.post("/api/fraimic/backend/voice", headers=headers, data=audio_fixture())).status == 401
    headers["Authorization"] = f"Bearer {entry.options[CONF_BACKEND_TOKEN]}"
    assert (await client.get("/api/fraimic/library", headers=headers)).status == 401
    with patch.object(VoiceJobs, "async_process", new_callable=AsyncMock, return_value=b"\x11" * 960_000) as voice:
        reply = await client.post("/api/fraimic/backend/voice", headers=headers, data=audio_fixture())
        assert reply.status == 200
        assert len(await reply.read()) == 960_000
        voice.assert_awaited_once()


async def test_bridge_rejects_non_utf8_authorization(backend_entry: Any, hass: HomeAssistant) -> None:
    from unittest.mock import Mock

    from aiohttp import web
    from homeassistant.components.http import KEY_HASS
    from custom_components.fraimic.local_backend import BackendVoiceView

    request = Mock(
        spec=web.Request,
        headers={"Authorization": "Bearer \udcff"}, app={KEY_HASS: hass},
    )
    with pytest.raises(web.HTTPUnauthorized):
        await BackendVoiceView().post(request)


async def test_backend_contact_updates_battery_without_claiming_lan_awake(backend_entry: Any) -> None:
    import time
    entry, _ = backend_entry
    coordinator = entry.runtime_data.coordinator
    coordinator.last_update_success = False
    coordinator.async_backend_contact({"last_seen": time.time(), "battery_percent": 24})
    assert coordinator.data["battery"]["percent"] == 24
    assert coordinator.device_reachable
    assert not coordinator.last_update_success


@pytest.mark.parametrize("method", ["refresh", "sleep", "restart"])
async def test_backend_owns_lan_redraw_and_power_commands(backend_entry: Any, method: str) -> None:
    from custom_components.fraimic.api import FraimicApiError
    entry, _ = backend_entry
    with pytest.raises(FraimicApiError, match="backend owns delivery"):
        await getattr(entry.runtime_data.client, method)()


async def test_handoff_shows_waiting_then_served_without_confirming(
    hass: HomeAssistant, backend_entry: Any,
) -> None:
    entry, request = backend_entry
    backend = entry.runtime_data.backend
    jobs: list[dict[str, Any]] = []

    async def bridge(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        if path == "/bridge/delivery":
            job = {"job_id": kwargs["job_id"], "state": "ready", "created_at": 1.0, "served_at": None}
            jobs[:] = [job]
            return dict(job)
        if path == "/bridge/state":
            return {"busy": False, "jobs": [dict(job) for job in jobs], "device": {}}
        return {}

    request.side_effect = bridge
    await backend.async_deliver(b"\x11" * 960_000, title="Sunflowers", preview_png=b"png")
    # The one-job delivery reply must not replace the cached state's shape.
    assert backend.status["jobs"][0]["job_id"] == backend.preview["job"]
    assert backend.summary() == "waiting"
    player = _player_payload(hass, entry)
    assert player["preview"]["title"] == "Sunflowers"
    assert player["preview"]["status"] == "waiting"
    assert player["preview"]["next_wake"] is not None
    assert entry.runtime_data.displayed_preview is None

    jobs[0].update(state="served", served_at=dt_util.utcnow().timestamp())
    await backend.async_status()
    assert backend.summary() == "served"
    assert _player_payload(hass, entry)["preview"]["status"] == "served"
    assert entry.runtime_data.displayed_preview is None

    request.side_effect = BackendUnavailable("down")
    with pytest.raises(BackendUnavailable):
        await backend.async_status()
    assert backend.summary() == "offline"


async def test_only_a_missed_wake_makes_a_sleeping_frame_unreachable(
    hass: HomeAssistant, backend_entry: Any,
) -> None:
    entry, _ = backend_entry
    backend, coordinator = entry.runtime_data.backend, entry.runtime_data.coordinator
    coordinator.frame_online = False
    now = dt_util.utcnow().timestamp()
    backend.last_due, backend.next_wake = None, int(now + 3600)
    assert _frame_payload(hass, entry)["unreachable"] is False

    backend.last_due = int(now - 3600)
    coordinator._last_seen = now - 7200
    frame = _frame_payload(hass, entry)
    assert frame["unreachable"] is True
    assert frame["missed_wake"] is not None
    assert frame["delivery"] == DELIVERY_BACKEND

    coordinator.async_backend_contact({"last_seen": now - 3500})
    assert _frame_payload(hass, entry)["unreachable"] is False


async def test_status_view_lists_voice_requests_without_tombstones(
    hass: HomeAssistant, backend_entry: Any, hass_client: Any,
) -> None:
    entry, _ = backend_entry
    jobs = entry.runtime_data.backend.voice
    with (
        patch.object(VoiceJobs, "_transcribe", new_callable=AsyncMock, return_value="A quiet forest"),
        patch.object(VoiceJobs, "_generate", new_callable=AsyncMock,
                     return_value=(image_fixture(), {"provider": "fake", "style": "Woodcut", "cost": 0.04})),
    ):
        await jobs.async_process("c" * 32, audio_fixture(), "portrait")
    jobs.jobs["d" * 32] = {"created": 1.0, "state": "expired", "hash": "x", "orientation": "portrait"}
    # A voice result becomes the player's handed-off picture.
    assert entry.runtime_data.backend.preview["job"] == "c" * 32
    assert entry.runtime_data.backend.preview["title"] == "“A quiet forest”"

    client = await hass_client()
    reply = await client.get(f"/api/fraimic/backend/status/{entry.entry_id}")
    assert reply.status == 200
    body = await reply.json()
    assert body["summary"] == "idle"
    assert [(r["id"], r["status"], r["mode"], r["transcript"], r["style"], r["cost"])
            for r in body["requests"]] == [("c" * 32, "ready", "art", "A quiet forest", "Woodcut", 0.04)]
