"""Exercise the actual HTTP boundary with synthetic audio and exact panel bytes."""

import asyncio
import io
import wave
from dataclasses import replace
from pathlib import Path

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from fraimic_backend.model import Device, MAX_AUDIO, validate_wav
from fraimic_backend.server import Backend, create_app, create_bridge_app

DEVICE = Device("large", "fixture-device-key", "fixture-user", "bridge-secret-" * 4,
                "http://127.0.0.1:8123", "315")
IDENTITY = {"device_key": DEVICE.device_key, "user_id": DEVICE.user_id}
AUTH = {"Authorization": f"Bearer {DEVICE.bridge_token}"}
PANEL = b"\x12" * 2_304_000


def wav():
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\0\0" * 16000)
    return output.getvalue()


@pytest.fixture
async def service(tmp_path):
    now = [1_800_000_000.0]
    calls = []

    async def voice(device, job):
        calls.append(job.id)
        return PANEL

    backend = Backend([DEVICE], "https://frame.example", tmp_path / "state.sqlite3",
                      process_voice=voice, clock=lambda: now[0])
    async with TestClient(TestServer(create_app(backend, include_bridge=True))) as client:
        yield backend, client, now, calls


async def presign(client):
    reply = await client.post("/api/v1/upload/audio/presign", json=IDENTITY)
    assert reply.status == 200, await reply.text()
    assert "Transfer-Encoding" not in reply.headers
    body = await reply.json()
    assert body["fields"] == {}
    assert len(body["key"]) <= 255
    return body


async def upload(client, signed, content=None):
    form = aiohttp.FormData()
    form.add_field("file", wav() if content is None else content,
                   filename="recording.wav", content_type="audio/wav")
    path = "/audio/" + signed["url"].rsplit("/", 1)[-1]
    return await client.post(path, data=form)


async def finalize(client, signed, **overrides):
    return await client.post("/api/v1/upload/audio/finalize", json={
        **IDENTITY, "key": signed["key"], "orientation": "landscape", **overrides,
    })


async def test_stock_voice_round_trip_headers_exact_bytes_and_retry(service):
    backend, client, now, calls = service
    signed = await presign(client)
    reply = await upload(client, signed)
    assert reply.status == 200
    assert reply.headers["Content-Length"] == "0"
    assert await reply.read() == b""
    assert (await upload(client, signed)).status == 200
    first, second = await asyncio.gather(finalize(client, signed), finalize(client, signed))
    assert first.status == second.status == 200
    first_body = await first.read()
    assert int(first.headers["Content-Length"]) == len(first_body) < 4096
    assert "Transfer-Encoding" not in first.headers
    assert first_body == await second.read()
    assert calls == [signed["key"]]
    assert backend.jobs[signed["key"]].audio == b""
    asset_path = "/panel/" + (await first.json())["presigned_url"].rsplit("/", 1)[-1]
    for _ in range(2):
        asset = await client.get(asset_path)
        assert asset.status == 200
        assert asset.headers["Content-Length"] == "2304000"
        assert asset.headers["Content-Type"] == "application/octet-stream"
        assert "Transfer-Encoding" not in asset.headers
        assert await asset.read() == PANEL
    state = await (await client.get("/bridge/state", headers=AUTH)).json()
    assert state["jobs"][0]["state"] == "served"
    assert state["jobs"][0]["confirmed_on_panel"] is False
    assert state["busy"] is True
    now[0] += 91
    assert (await (await client.get("/bridge/state", headers=AUTH)).json())["busy"] is False


@pytest.mark.parametrize("field,value", [("device_key", "wrong"), ("user_id", "wrong"), ("user_id", None)])
async def test_identity_is_bound_to_enrolled_user(service, field, value):
    _, client, _, _ = service
    reply = await client.post("/api/v1/upload/audio/presign", json={**IDENTITY, field: value})
    assert reply.status == 401


async def test_tickets_purposes_upload_order_and_conflicting_replays(service):
    _, client, _, calls = service
    signed = await presign(client)
    assert (await finalize(client, signed)).status == 409
    ticket = signed["url"].rsplit("/", 1)[-1]
    assert (await client.get(f"/panel/{ticket}")).status == 404
    assert (await client.get("/panel/no-ticket")).status == 404
    assert (await upload(client, signed, b"invalid")).status == 400
    assert (await upload(client, signed, wav()[:-2])).status == 400
    assert (await upload(client, signed)).status == 200
    changed = bytearray(wav())
    changed[-1] = 1
    assert (await upload(client, signed, bytes(changed))).status == 409
    assert (await finalize(client, signed, orientation="bad")).status == 400
    assert (await finalize(client, signed)).status == 200
    assert (await finalize(client, signed, orientation="portrait")).status == 409
    assert len(calls) == 1


async def test_expiry_cancellation_cleanup_and_busy_release(service):
    backend, client, now, calls = service
    signed = await presign(client)
    assert (await upload(client, signed)).status == 200
    assert (await client.post("/api/v1/upload/audio/presign", json=IDENTITY)).status == 409
    now[0] += 601
    assert (await finalize(client, signed)).status == 410
    job = backend.jobs[signed["key"]]
    assert not job.audio and not job.asset
    signed = await presign(client)
    cancelled = await client.post("/bridge/cancel", headers=AUTH, json={"job_id": signed["key"]})
    assert cancelled.status == 200
    assert (await upload(client, signed)).status == 410
    assert not calls
    await presign(client)


async def test_wake_and_settings_preserved_on_idle_and_ready_polls(service):
    backend, client, now, _ = service
    backend.devices[DEVICE.id] = replace(DEVICE, settings={
        "voiceRecordingEnabled": True, "keepAwakeEnabled": False,
        "autoUpdateEnabled": True, "chargingLedEnabled": False,
    }, email_verified=True)
    wake = int(now[0] + 3600)
    assert (await client.put("/bridge/schedule", headers=AUTH, json={"next_image_utc": wake})).status == 200
    path = f"/api/v1/upload/check/{DEVICE.device_key}?display_type=315&orientation=portrait&is_periodic_poll=false&current_version=0.2.29&battery_pct=80&wifi_ssid=private&include_account=true"
    idle = await (await client.get(path)).json()
    assert idle["next_image_utc"] == wake
    assert idle["firmware"] is None and not idle["has_new_upload"]
    assert idle["device_settings"]["autoUpdateEnabled"] is True
    assert idle["account"] == {"email_verified": True}
    assert (await client.post("/bridge/delivery", headers={**AUTH, "X-Fraimic-Job": "a" * 32}, data=PANEL)).status == 200
    ready = await (await client.get(path)).json()
    assert ready["has_new_upload"] and ready["next_image_utc"] == wake
    assert ready["firmware"] is None
    # No second offer while the first may already be downloading or recording.
    assert not (await (await client.get(path)).json())["has_new_upload"]
    assert (await client.get(path.replace("315", "133"))).status == 409


async def test_voice_holds_scheduler_and_scheduled_offer_holds_voice(service):
    backend, client, now, _ = service
    signed = await presign(client)
    assert (await client.post("/bridge/delivery", headers={**AUTH, "X-Fraimic-Job": "a" * 32}, data=PANEL)).status == 409
    await client.post("/bridge/cancel", headers=AUTH, json={"job_id": signed["key"]})
    assert (await client.post("/bridge/delivery", headers={**AUTH, "X-Fraimic-Job": "a" * 32}, data=PANEL)).status == 200
    await client.get(f"/api/v1/upload/check/{DEVICE.device_key}")
    assert (await client.post("/api/v1/upload/audio/presign", json=IDENTITY)).status == 409
    now[0] += 181
    await presign(client)
    assert not (await (await client.get(f"/api/v1/upload/check/{DEVICE.device_key}")).json())["has_new_upload"]


@pytest.mark.parametrize(("succeeds", "offered"), [(True, False), (False, False), (True, True)])
async def test_voice_supersedes_unoffered_art_only_after_success(service, succeeds, offered):
    backend, client, now, _ = service
    ident = "a" * 32
    assert (await client.post(
        "/bridge/delivery", headers={**AUTH, "X-Fraimic-Job": ident}, data=PANEL,
    )).status == 200
    poll_path = f"/api/v1/upload/check/{DEVICE.device_key}"
    if offered:
        assert (await (await client.get(poll_path)).json())["has_new_upload"]
    now[0] += 181
    if not succeeds:
        async def fail(device, job):
            raise TimeoutError("possibly billed")

        backend.process_voice = fail
    signed = await presign(client)
    await upload(client, signed)
    assert backend.jobs[ident].state == "ready"
    final = await finalize(client, signed)
    if succeeds:
        assert final.status == 200
        path = "/panel/" + (await final.json())["presigned_url"].rsplit("/", 1)[-1]
        assert await (await client.get(path)).read() == PANEL
        now[0] += DEVICE.settle + 1
    else:
        assert final.status == 503
    superseded = succeeds and not offered
    persisted, _, _ = await asyncio.to_thread(backend.store.load)
    assert persisted[ident].state == ("cancelled" if superseded else "ready")
    assert persisted[ident].asset == (b"" if superseded else PANEL)
    assert (await (await client.get(poll_path)).json())["has_new_upload"] is not superseded


@pytest.mark.parametrize("restart", [False, True])
async def test_voice_result_survives_art_cancellation_journal_failure(service, monkeypatch, restart):
    backend, client, now, calls = service
    ident = "a" * 32
    assert (await client.post(
        "/bridge/delivery", headers={**AUTH, "X-Fraimic-Job": ident}, data=PANEL,
    )).status == 200
    now[0] += 181
    signed = await presign(client)
    assert (await upload(client, signed)).status == 200
    save = backend.store.save

    def fail_cancellation(job):
        if job.id == ident and job.state == "cancelled":
            raise OSError("journal unavailable")
        save(job)

    monkeypatch.setattr(backend.store, "save", fail_cancellation)
    first = await finalize(client, signed)
    assert first.status == 200
    persisted, _, _ = await asyncio.to_thread(backend.store.load)
    assert persisted[signed["key"]].state == "ready"
    assert persisted[signed["key"]].asset == PANEL
    assert backend.jobs[ident].state == "cancelled"
    assert persisted[ident].state == "ready"
    if restart:
        # Simulate losing in-memory cancellation state before the next retry.
        backend.jobs = persisted
        backend._pending_art_cancellations.clear()
    second = await finalize(client, signed)
    assert second.status == 200
    assert await first.read() == await second.read()
    path = "/panel/" + (await second.json())["presigned_url"].rsplit("/", 1)[-1]
    assert await (await client.get(path)).read() == PANEL
    assert calls == [signed["key"]]
    now[0] += DEVICE.settle + 1
    poll_path = f"/api/v1/upload/check/{DEVICE.device_key}"
    assert not (await (await client.get(poll_path)).json())["has_new_upload"]
    monkeypatch.setattr(backend.store, "save", save)
    assert not (await (await client.get(poll_path)).json())["has_new_upload"]
    persisted, _, _ = await asyncio.to_thread(backend.store.load)
    assert persisted[ident].state == "cancelled"
    assert persisted[ident].asset == b""


async def test_private_bridge_and_unsupported_routes_fail_closed(service):
    _, client, _, _ = service
    for token in ("", DEVICE.device_key, "owner-ha-token"):
        assert (await client.get("/bridge/state", headers={"Authorization": f"Bearer {token}"})).status == 401
    for path in ("/api/v1/account/setup", "/api/v1/upload/global/315/test", "/api/services", "/firmware"):
        assert (await client.post(path, json={})).status == 404
    assert (await client.put(f"/api/v1/albums/{DEVICE.device_key}", json={})).status == 405
    duplicate = '{"device_key":"fixture-device-key","user_id":"fixture-user","USER_ID":"other"}'
    assert (await client.post("/api/v1/upload/audio/presign", data=duplicate)).status == 400


@pytest.mark.parametrize("wake", [True, "1800003600", 0, -1, 1.5])
async def test_invalid_schedule(service, wake):
    _, client, _, _ = service
    assert (await client.put("/bridge/schedule", headers=AUTH, json={"next_image_utc": wake})).status == 400


async def test_size_and_palette_limits(service):
    _, client, _, _ = service
    headers = {**AUTH, "X-Fraimic-Job": "b" * 32}
    for data in (b"short", b"\x44" * len(PANEL)):
        assert (await client.post("/bridge/delivery", headers=headers, data=data)).status == 400
    signed = await presign(client)
    assert (await upload(client, signed, b"x" * (MAX_AUDIO + 16384))).status == 413


async def test_durable_restart_assets_wake_and_idempotent_delivery(tmp_path):
    path = tmp_path / "state.sqlite3"
    backend = Backend([DEVICE], "https://frame.example", path)
    headers = {**AUTH, "X-Fraimic-Job": "a" * 32}
    async with TestClient(TestServer(create_app(backend, include_bridge=True))) as client:
        assert (await client.post("/bridge/delivery", headers=headers, data=PANEL)).status == 200
        wake = int(backend.clock() + 3600)
        await client.put("/bridge/schedule", headers=AUTH, json={"next_image_utc": wake})
        ticket = backend.jobs["a" * 32].asset_ticket
    restarted = Backend([DEVICE], "https://frame.example", path)
    async with TestClient(TestServer(create_app(restarted, include_bridge=True))) as client:
        assert (await client.post("/bridge/delivery", headers=headers, data=PANEL)).status == 200
        assert len(restarted.jobs) == 1
        assert restarted.wakes[DEVICE.id] == wake
        reply = await client.get(f"/panel/{ticket}")
        assert await reply.read() == PANEL


async def test_provider_failure_does_not_retry_or_leave_audio(service):
    backend, client, _, _ = service
    calls = []

    async def fail(device, job):
        calls.append(job.id)
        raise TimeoutError("possibly billed")

    backend.process_voice = fail
    signed = await presign(client)
    await upload(client, signed)
    assert (await finalize(client, signed)).status == 503
    assert (await finalize(client, signed)).status == 410
    assert calls == [signed["key"]]
    assert backend.jobs[signed["key"]].audio == b""
    assert not backend._busy(DEVICE)


async def test_disconnected_finalize_waiter_does_not_cancel_work(service):
    backend, client, _, _ = service
    started, release = asyncio.Event(), asyncio.Event()

    async def slow(device, job):
        started.set()
        await release.wait()
        return PANEL

    backend.process_voice = slow
    signed = await presign(client)
    await upload(client, signed)
    waiting = asyncio.create_task(finalize(client, signed))
    await started.wait()
    waiting.cancel()
    await asyncio.gather(waiting, return_exceptions=True)
    release.set()
    reply = await finalize(client, signed)
    assert reply.status == 200


@pytest.mark.parametrize("failures", [1, 4])
async def test_interrupted_transfer_is_retryable_without_display_claim(service, monkeypatch, failures):
    from aiohttp import web

    backend, client, now, _ = service
    headers = {**AUTH, "X-Fraimic-Job": "e" * 32}
    await client.post("/bridge/delivery", headers=headers, data=PANEL)
    job = backend.jobs["e" * 32]
    write = web.StreamResponse.write
    failed = asyncio.Event()

    async def interrupted(reply, data):
        if reply.content_type == "application/octet-stream":
            failed.set()
            raise ConnectionResetError("synthetic lost connection")
        return await write(reply, data)

    with monkeypatch.context() as patch:
        patch.setattr(web.StreamResponse, "write", interrupted)
        for _ in range(failures):
            failed.clear()
            reply = await client.get(f"/panel/{job.asset_ticket}")
            await failed.wait()
            reply.close()
    assert job.state == "ready" and job.served_at is None
    assert job.status()["confirmed_on_panel"] is False
    reply = await client.get(f"/panel/{job.asset_ticket}")
    if failures == 4:
        assert reply.status == 410
        now[0] += DEVICE.settle + 1
        body = await (await client.get(f"/api/v1/upload/check/{DEVICE.device_key}")).json()
        assert not body["has_new_upload"]
        await presign(client)
        return
    assert await reply.read() == PANEL
    assert job.state == "served"


async def test_restart_reconciles_processing_with_same_job_identity(tmp_path):
    path = tmp_path / "state.sqlite3"
    backend = Backend([DEVICE], "https://frame.example", path)
    async with TestClient(TestServer(create_app(backend, include_bridge=True))) as client:
        signed = await presign(client)
        await upload(client, signed)
        job = backend.jobs[signed["key"]]
        job.state, job.orientation = "processing", "landscape"
        await backend._save(job)
    calls = []

    async def reconcile(device, job):
        calls.append(job.id)
        return PANEL

    backend = Backend([DEVICE], "https://frame.example", path, process_voice=reconcile)
    async with TestClient(TestServer(create_app(backend, include_bridge=True))) as client:
        reply = await finalize(client, signed)
        assert reply.status == 200
        assert calls == [signed["key"]]


async def test_expired_composition_is_never_offered(service):
    backend, client, now, _ = service
    headers = {**AUTH, "X-Fraimic-Job": "f" * 32, "X-Fraimic-Expires": str(int(now[0] + 120))}
    assert (await client.post("/bridge/delivery", headers=headers, data=PANEL)).status == 200
    now[0] += 121
    body = await (await client.get(f"/api/v1/upload/check/{DEVICE.device_key}")).json()
    assert not body["has_new_upload"]
    assert backend.jobs["f" * 32].asset == b""


def test_malformed_wav_and_incomplete_settings():
    with pytest.raises(ValueError):
        validate_wav(wav() + b"tail")
    with pytest.raises(ValueError):
        replace(DEVICE, settings={"keepAwakeEnabled": False})


async def test_private_bridge_has_separate_routes_and_shared_state(tmp_path):
    backend = Backend([DEVICE], "https://frame.example", tmp_path / "state.sqlite3")
    async with TestClient(TestServer(create_app(backend))) as device:
        async with TestClient(TestServer(create_bridge_app(backend))) as bridge:
            assert (await device.get("/bridge/state", headers=AUTH)).status == 404
            assert (await bridge.get("/api/v1/upload/check/" + DEVICE.device_key)).status == 404
            assert (await bridge.get("/bridge/state")).status == 401
            delivery = await bridge.post("/bridge/delivery", headers={**AUTH, "X-Fraimic-Job": "f" * 32}, data=PANEL)
            assert delivery.status == 200
            poll = await device.get("/api/v1/upload/check/" + DEVICE.device_key)
            assert (await poll.json())["presigned_url"] is not None


async def test_companion_calls_narrow_ha_bridge_with_original_audio(tmp_path):
    seen = []

    async def voice(request):
        assert request.headers["Authorization"] == AUTH["Authorization"]
        assert request.headers["X-Fraimic-Orientation"] == "landscape"
        assert await request.read() == wav()
        seen.append(request.headers["X-Fraimic-Job"])
        return web.Response(body=PANEL, content_type="application/octet-stream")

    ha = web.Application(client_max_size=MAX_AUDIO)
    ha.router.add_post("/api/fraimic/backend/voice", voice)
    async with TestServer(ha) as ha_server:
        device = replace(DEVICE, ha_url=str(ha_server.make_url("/")))
        backend = Backend([device], "https://frame.example", tmp_path / "state.sqlite3")
        async with TestClient(TestServer(create_app(backend))) as frame:
            signed = await presign(frame)
            assert (await upload(frame, signed)).status == 200
            reply = await finalize(frame, signed)
            assert reply.status == 200
            path = "/panel/" + (await reply.json())["presigned_url"].rsplit("/", 1)[-1]
            assert await (await frame.get(path)).read() == PANEL
            assert seen == [signed["key"]]


async def test_abandoned_ready_voice_releases_window_but_late_fetch_waits(service):
    backend, client, now, calls = service
    signed = await presign(client)
    assert (await upload(client, signed)).status == 200
    final = await (await finalize(client, signed)).json()
    path = "/panel/" + final["presigned_url"].rsplit("/", 1)[-1]
    assert (await (await client.get("/bridge/state", headers=AUTH)).json())["busy"] is True
    now[0] += 181
    assert (await (await client.get("/bridge/state", headers=AUTH)).json())["busy"] is False
    assert (await client.post("/bridge/delivery", headers={**AUTH, "X-Fraimic-Job": "e" * 32}, data=PANEL)).status == 200
    assert (await (await client.get("/api/v1/upload/check/" + DEVICE.device_key)).json())["has_new_upload"] is True
    assert (await client.get(path)).status == 409


async def test_fraimic_voice_mode_forwards_only_the_recording(tmp_path):
    vendor_calls = []

    async def ha_voice(request):
        await request.read()
        return web.Response(status=202, headers={"X-Fraimic-Forward": "fraimic"})

    async def vendor(request):
        vendor_calls.append((request.method, request.path))
        if request.path == "/api/v1/upload/audio/presign":
            assert await request.json() == IDENTITY
            return web.json_response({"success": True, "url": str(request.url.with_path("/s3")),
                                      "fields": {"key": "audio/x.wav", "policy": "signed"}, "key": "audio/x.wav"})
        if request.path == "/s3":
            form = await request.post()
            assert form["policy"] == "signed" and form["file"].file.read() == wav()
            return web.Response(status=204)
        if request.path == "/api/v1/upload/audio/finalize":
            assert await request.json() == {**IDENTITY, "key": "audio/x.wav", "orientation": "landscape"}
            # Nothing from a vendor reply, firmware included, may reach the frame.
            return web.json_response({"success": True, "presigned_url": str(request.url.with_path("/panel.bin")),
                                      "firmware": {"version": "9.9.9", "presigned_url": "https://fw.example/x.bin"}})
        if request.path == "/panel.bin":
            return web.Response(body=PANEL)
        return web.Response(status=404)

    ha = web.Application(client_max_size=MAX_AUDIO)
    ha.router.add_post("/api/fraimic/backend/voice", ha_voice)
    fraimic = web.Application()
    fraimic.router.add_route("*", "/{tail:.*}", vendor)
    async with TestServer(ha) as ha_server, TestServer(fraimic) as vendor_server:
        device = replace(DEVICE, ha_url=str(ha_server.make_url("/")))
        backend = Backend([device], "https://frame.example", tmp_path / "state.sqlite3",
                          vendor_url=str(vendor_server.make_url("/")))
        poll_path = f"/api/v1/upload/check/{DEVICE.device_key}?current_version=0.0.1"
        async with TestClient(TestServer(create_app(backend))) as frame:
            assert (await (await frame.get(poll_path)).json())["firmware"] is None
            signed = await presign(frame)
            assert (await upload(frame, signed)).status == 200
            reply = await finalize(frame, signed)
            assert reply.status == 200
            body = await reply.json()
            assert set(body) == {"status", "presigned_url"}
            assert body["presigned_url"].startswith("https://frame.example/panel/")
            assert await (await frame.get("/panel/" + body["presigned_url"].rsplit("/", 1)[-1])).read() == PANEL
            assert (await (await frame.get(poll_path)).json())["firmware"] is None
    assert vendor_calls == [
        ("POST", "/api/v1/upload/audio/presign"), ("POST", "/s3"),
        ("POST", "/api/v1/upload/audio/finalize"), ("GET", "/panel.bin"),
    ]
