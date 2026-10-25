"""Recorded requests with a durable, at-most-once provider boundary.

Only the companion retains WAVs. HA keeps job identity, provenance and frozen
panel results; no request handler owns a provider task's lifetime.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import time
import wave
from collections.abc import AsyncIterator
from functools import partial
from pathlib import Path
from typing import Any

from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .ai_art import VoiceSettings
from .ai_manager import AiArtManager, get_ai_manager
from .const import DOMAIN, viewed_size
from .coordinator import FraimicConfigEntry
from .library import get_library
from .library_model import Creation
from .render.card import result_card


def pcm_from_wav(raw: bytes) -> bytes:
    if (not 44 <= len(raw) <= 2_128_192 or raw[:4] != b"RIFF"
        or int.from_bytes(raw[4:8], "little") + 8 != len(raw)):
        raise ValueError("Invalid WAV length")
    offset, data_chunks = 12, 0
    while offset < len(raw):
        if offset + 8 > len(raw):
            raise ValueError("Truncated WAV chunk")
        size = int.from_bytes(raw[offset + 4:offset + 8], "little")
        if raw[offset:offset + 4] == b"data":
            data_chunks += 1
            if size % 2:
                raise ValueError("Unaligned PCM data")
        offset += 8 + size + size % 2
        if offset > len(raw):
            raise ValueError("Truncated WAV chunk")
    if data_chunks != 1:
        raise ValueError("Expected one PCM data chunk")
    try:
        with wave.open(io.BytesIO(raw)) as wav:
            if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getcomptype()) != (1, 2, 16000, "NONE"):
                raise ValueError("Expected mono 16-bit 16 kHz PCM")
            count = wav.getnframes()
            pcm = wav.readframes(count)
            if not 0 < count <= 66 * 16000 or len(pcm) != count * 2:
                raise ValueError("Invalid PCM sample count")
            return pcm
    except (wave.Error, EOFError) as err:
        raise ValueError("Invalid WAV") from err


class ForwardToFraimic(Exception):
    """The voice mode asks the companion to send this recording to Fraimic."""


class VoiceJobs:
    def __init__(self, hass: HomeAssistant, entry: FraimicConfigEntry) -> None:
        self.hass, self.entry = hass, entry
        self.store: Store[dict[str, Any]] = Store(hass, 1, f"{DOMAIN}.voice.{entry.entry_id}")
        self.directory = Path(hass.config.path(".storage", f"fraimic_voice_{entry.entry_id}"))
        self.jobs: dict[str, dict[str, Any]] = {}
        self.tasks: dict[str, asyncio.Task[bytes]] = {}
        self.lock = asyncio.Lock()

    async def async_setup(self) -> None:
        self.jobs = await self.store.async_load() or {}
        await self.hass.async_add_executor_job(lambda: self.directory.mkdir(parents=True, exist_ok=True, mode=0o700))
        # Processing records stay uncertain. Only an already-saved library
        # creation/frozen result can complete them without invoking providers.
        await self._cleanup()

    def _manager(self) -> AiArtManager:
        manager = get_ai_manager(self.hass)
        if manager is None:
            raise HomeAssistantError("AI art settings are not loaded")
        return manager

    def _voice(self) -> VoiceSettings:
        return self._manager().voice(self.entry.entry_id)

    def shutdown(self) -> None:
        for task in self.tasks.values():
            task.cancel()

    async def _save(self) -> None:
        await self.store.async_save(self.jobs)

    async def _cleanup(self) -> None:
        cutoff = time.time() - 86400
        for ident, job in list(self.jobs.items()):
            if job["created"] < cutoff and ident not in self.tasks:
                await self.hass.async_add_executor_job((self.directory / f"{ident}.bin").unlink, True)
                # Keep a small replay tombstone longer than companion tickets.
                self.jobs[ident] = {"created": job["created"], "state": "expired",
                                    "hash": job["hash"], "orientation": job["orientation"]}
            if job["created"] < time.time() - 8 * 86400:
                del self.jobs[ident]
        await self._save()

    async def async_process(self, ident: str, audio: bytes, orientation: str) -> bytes:
        pcm = await self.hass.async_add_executor_job(pcm_from_wav, audio)
        digest = hashlib.sha256(audio).hexdigest()
        async with self.lock:
            await self._cleanup()
            job = self.jobs.get(ident)
            if job is not None and (job["hash"] != digest or job["orientation"] != orientation):
                raise HomeAssistantError("Job content changed")
            if ident in self.tasks:
                task = self.tasks[ident]
            else:
                if self.tasks or len(self.jobs) >= 512:
                    raise HomeAssistantError("Voice capacity reached")
                if job is None:
                    job = {"created": time.time(), "state": "accepted", "hash": digest,
                           "orientation": orientation}
                    self.jobs[ident] = job
                    await self._save()
                if job["state"] == "expired":
                    raise HomeAssistantError("Voice job expired")
                if job["state"] == "accepted" and self._voice().mode == "fraimic":
                    # Recorded first: a repeat of this job gets the "may have
                    # finished" card instead of a second Fraimic request.
                    job.update(state="forwarded", mode="fraimic")
                    await self._save()
                    raise ForwardToFraimic
                task = self.entry.async_create_background_task(
                    self.hass, self._run(ident, pcm), f"fraimic-voice-{ident}"
                )
                self.tasks[ident] = task
                task.add_done_callback(lambda _: self.tasks.pop(ident, None))
        return await asyncio.shield(task)

    async def _run(self, ident: str, pcm: bytes) -> bytes:
        job = self.jobs[ident]
        panel = self.directory / f"{ident}.bin"
        scheduler = self.entry.runtime_data.scheduler
        if scheduler is not None:
            scheduler.begin_external_upload()
        try:
            async with asyncio.timeout(450):
                if job["state"] == "ready":
                    packed = await self.hass.async_add_executor_job(panel.read_bytes)
                    controller = self.entry.runtime_data.temporary_overlays
                    if controller is not None:
                        await controller.async_invalidate()
                    return packed
                library = get_library(self.hass)
                if library is None:
                    raise HomeAssistantError("Library unavailable")
                existing = next((image for image in library.images.values()
                                 if image.creation is not None
                                 and image.creation.key == (f"local:{self.entry.entry_id}", ident)), None)
                if existing is not None:
                    image_id = existing.image_id
                elif job.get("library_image"):
                    image_id = str(job["library_image"])
                elif job["state"] != "accepted":
                    # A crash while STT, generation or an intent was running
                    # cannot prove whether the provider/action completed.
                    job["outcome"] = "uncertain"
                    image_id = await self._save_card(
                        ident, "This request may already have finished. It will not run "
                        "again by itself. Check Home Assistant before asking again.",
                        label="NOT REPEATED",
                    )
                elif self._voice().mode == "fixed":
                    job["mode"] = "fixed"
                    image_id = self._voice().image
                    library.get(image_id)
                else:
                    job["state"] = "transcribing"
                    await self._save()
                    text = await self._transcribe(pcm)
                    job["transcript"] = text
                    mode = job["mode"] = self._voice().mode
                    if mode == "art":
                        job["state"] = "generating"
                        await self._save()
                        original, metadata = await self._generate(ident, text, job["orientation"])
                        image_id = await self._add_original(ident, original, metadata)
                    elif mode == "assist":
                        job["state"] = "command"
                        await self._save()
                        result = await self._command(text)
                        image_id = await self._save_card(ident, result)
                    else:
                        raise HomeAssistantError("Voice mode is not configured")
                job["library_image"] = image_id
                job["state"] = "rendering"
                await self._save()
                packed, preview, _ = await library.async_render_for_entry(image_id, self.entry)
                await self.hass.async_add_executor_job(self._write_panel, panel, packed)
                job["state"] = "ready"
                await self._save()
                backend = self.entry.runtime_data.backend
                if backend is not None:
                    image = library.get(image_id)
                    if image.creation and (image.creation.metadata or {}).get("kind") == "result_card":
                        # Player artwork is shared with non-admin HA users.
                        width, height = self._size(job["orientation"])
                        preview = await self.hass.async_add_executor_job(partial(
                            result_card, "Open this voice result in the private library.",
                            width=width, height=height, label="VOICE REQUEST",
                        ))
                    backend.set_preview(ident, preview, title="Voice request", source={"library_image": image_id})
                # The companion owns the handoff, not a confirmed display.
                # Retained older artwork must never refresh over this result.
                controller = self.entry.runtime_data.temporary_overlays
                if controller is not None:
                    await controller.async_invalidate()
                return packed
        except asyncio.CancelledError:
            raise
        except Exception as err:
            job["outcome"] = "uncertain" if job["state"] in {"generating", "command"} else "failed"
            job["state"] = "failed"
            await self._save()
            raise HomeAssistantError("Voice request failed; no automatic retry") from err
        finally:
            if scheduler is not None:
                scheduler.finish_external_upload(uploaded=False, hold=False)

    @staticmethod
    def _write_panel(path: Path, data: bytes) -> None:
        temporary = path.with_suffix(".tmp")
        with temporary.open("wb") as file:
            file.write(data)
            file.flush()
            import os
            os.fsync(file.fileno())
        temporary.replace(path)

    async def _transcribe(self, pcm: bytes) -> str:
        from homeassistant.components import stt

        voice = self._voice()
        entity = stt.async_get_speech_to_text_entity(self.hass, voice.stt)
        metadata = stt.SpeechMetadata(
            language=voice.language or self.hass.config.language,
            format=stt.AudioFormats.WAV, codec=stt.AudioCodecs.PCM,
            bit_rate=stt.AudioBitRates.BITRATE_16, sample_rate=stt.AudioSampleRates.SAMPLERATE_16000,
            channel=stt.AudioChannels.CHANNEL_MONO,
        )
        if entity is None or not entity.available or not entity.check_metadata(metadata):
            raise HomeAssistantError("Select a compatible STT entity and language")

        async def chunks() -> AsyncIterator[bytes]:
            for offset in range(0, len(pcm), 4096):
                yield pcm[offset:offset + 4096]

        result = await entity.internal_async_process_audio_stream(metadata, chunks())
        if result.result != stt.SpeechResultState.SUCCESS or not result.text or not result.text.strip():
            raise HomeAssistantError("No transcript returned")
        if len(result.text) > 8000:
            raise HomeAssistantError("Transcript too long")
        return result.text.strip()

    def _size(self, orientation: str) -> tuple[int, int]:
        """The frame's wall size, turned to the request's orientation."""
        width, height = viewed_size(self.entry)
        if (orientation == "portrait") != (height > width):
            width, height = height, width
        return width, height

    async def _generate(self, ident: str, text: str, orientation: str) -> tuple[bytes, dict[str, Any]]:
        width, height = self._size(orientation)
        image, metadata = await self._manager().async_generate(
            text, width=width, height=height, task_name=f"fraimic_{ident}",
            ai_task_entity=self._voice().ai_task_entity,
        )
        return image.data, metadata

    async def _command(self, text: str) -> str:
        from homeassistant.components import conversation

        result = await conversation.async_converse(
            self.hass, text, None, Context(),
            language=self._voice().language or self.hass.config.language,
            agent_id=self._voice().agent or "homeassistant",
        )
        speech = result.response.as_dict().get("speech", {}).get("plain", {}).get("speech")
        return str(speech or "The request completed without a text response. Check Home Assistant for the result.")

    async def _save_card(self, ident: str, text: str, *, label: str = "YOU ASKED") -> str:
        job = self.jobs[ident]
        width, height = self._size(job["orientation"])
        now = dt_util.now()
        original = await self.hass.async_add_executor_job(partial(
            result_card, text, width=width, height=height, question=job.get("transcript"),
            label=label, when=f"{now:%a} {now.day} {now:%b, %H:%M}",
        ))
        return await self._add_original(ident, original, {"kind": "result_card"})

    async def _add_original(self, ident: str, original: bytes, metadata: dict[str, Any]) -> str:
        library = get_library(self.hass)
        assert library is not None
        job = self.jobs[ident]
        creation = Creation(
            account_id=f"local:{self.entry.entry_id}", upload_id=ident,
            created_at=job["created"], transcript=job.get("transcript"),
            orientation=job["orientation"], metadata={**metadata, "frame": self.entry.entry_id},
        )
        extension = {"image/jpeg": "jpg", "image/webp": "webp"}.get(str(metadata.get("mime_type")), "png")
        image = await library.async_add_image(original, f"voice-{ident}.{extension}", creation=creation)
        return image.image_id
