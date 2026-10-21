# Fraimic firmware research

This is an implementation-oriented map of **Fraimic Large firmware 0.2.29,
build f1555ee5**, researched on 21–22 October 2026. It covers the stock application,
its local and cloud protocols, and ways to integrate a custom backend with this
Home Assistant integration. It is not recovered vendor source or a flashing guide.
The [Standard-model comparison](standard-model-comparison.md) separately covers
0.2.28 / 4654a1d8 and its live enrollment/voice capture. Unless labelled otherwise,
addresses and static findings in the original topic pages refer to Large.

## Start here

The [research checklist](research-todo.md) tracks the unknowns and unverified
claims across these documents, with stable task IDs and concrete validation work.
The [21 October validation](validation-2026-10-21.md) records owner gallery reads,
installed HA capabilities, five library host checks and deeper firmware traces.
The [22 October continuation](validation-2026-10-22.md) adds HTTP-server lifecycle,
factory-diagnostic findings and 25 host poll-parser cases without device tests.
The [local-backend experiment](backend-emulation.md) then demonstrated locally
generated poll and album responses on the physical frame, without firmware changes.
It also captured the microphone locally, then completed successful finalize,
download, driver refresh and caching with a fixed six-colour card. The earlier
poll-delivered card was visually confirmed; the later voice test reused identical
pixels, so its second refresh is confirmed by logs rather than an observed change.
No transcription or AI generation was invoked.

| Document | Contents |
| --- | --- |
| [Identity and hardware](hardware-and-layout.md) | Exact image fingerprint, memory segments, panel format, wiring and shared buffers |
| [Cloud protocol](cloud-protocol.md) | API selectors, poll response semantics, system screens, transport requirements |
| [Image downloads](image-downloads.md) | Length/framing checks, restart-from-zero retries, incomplete images and cache consequences |
| [Voice](voice.md) | Recording, WAV upload, synchronous generation, cancellation, concurrency |
| [Rendering and concurrency](rendering-and-concurrency.md) | Buffer aliases, upload ordering, render policies, error propagation and completion signals |
| [Boot and scheduling](boot-and-scheduling.md) | Wake reasons, timers, time synchronization, sleep and offline dependencies |
| [Storage and configuration](storage-and-configuration.md) | NVS keys, identity migration, developer mode, image files and persistence |
| [OTA and recovery](ota-and-recovery.md) | Update paths, guards, verification, failure tracking and unresolved recovery questions |
| [Local API](local-api.md) | All 42 registered routes, diagnostics and side effects |
| [LED and workflow state](led-and-workflow-state.md) | 41-state table, priorities, protection latch and limits of visible status |
| [Home Assistant roadmap](home-assistant-roadmap.md) | Existing code to reuse, local cloud design, voice creations and staged experiments |
| [Evidence and open questions](evidence-and-open-questions.md) | Confidence, analysis method, address map and research backlog |
| [21 October validation](validation-2026-10-21.md) | Reproducible host checks, owner-account/HA observations and their limits |
| [22 October validation](validation-2026-10-22.md) | HTTP-server and diagnostic traces; 25 host poll-parser cases and error semantics |
| [Backend emulation](backend-emulation.md) | Physical poll/album, microphone upload and confirmed one-shot panel delivery |
| [Standard-model comparison](standard-model-comparison.md) | Model-specific firmware/panel differences, live setup, vendor voice flow and reachability failure |

Machine-readable references: [firmware identity](firmware-identity.json),
[route registrations](route-registrations.json),
[selected addresses](address-map.json), and
[model comparison with type-only live schemas](model-comparison.json).
The [LED state table](led-states.json) preserves the Large build's numeric records.

The [existing frame API reference](../frame-api/routes.md) describes tested
HTTP behavior across multiple firmware versions. The
[cloud API reference](../fraimic-cloud-api/routes.md) and its OpenAPI snapshot
describe the server. These firmware notes explain how this particular client
actually uses those interfaces. Server schemas are not a substitute for client
parser behavior.

## Evidence labels

- **Observed:** read from the owned physical frame or an owner-scoped transaction.
- **Static:** supported by instructions, constants, tables or call references in
  the exact image below; not necessarily exercised on the frame.
- **Inferred:** a consequence of the observed/static behavior, still to validate.
- **Proposed:** useful future behavior, not implemented by this documentation.
- **Unknown:** evidence is insufficient; do not assume a capability exists.

Unless a section says otherwise, firmware internals below are **static** findings.
Addresses are virtual addresses in this exact app, not flash offsets or stable
addresses across releases. Function names are analytical descriptions.

## Most consequential findings

1. One central API selector covers polling, voice, account setup, system-screen
   lookup and the album proxy. Web-app and authentication selectors are separate.
2. A custom API URL alone does not remove the public connectivity probe or NTP
   dependencies. Already-paired operation is simpler than independent enrollment.
3. `device_settings` is a snapshot. A partial object resets omitted switches to
   defaults. Parsed HTTP 200 JSON without a valid next-image time clears the saved
   schedule; suppressed network/HTTP errors preserve it.
4. Voice finalization must return the image synchronously. Stock firmware does not
   understand `202 + job ID`, and an abandoned 60-second recording is not uploaded.
5. Recording and image downloads use the same PSRAM allocation. Recording,
   uploading and rendering need coordinated ownership of that memory.
6. `autoUpdateEnabled` is stored and displayed but is not consulted by the
   recovered OTA decision path. The backend must control firmware offers.
7. HTTP image acceptance does not prove durable caching or completed display.
   A render-complete event with a content ID would materially improve HA state.
8. The display buffer aliases the audio/image allocation too. Render WAIT happens
   after HTTP reception, and the worker's completion semaphore also signals failure.
   `display.last_refresh` records maintenance history, not every image delivery.
9. Owner-authenticated gallery reads expose voice transcripts and originals;
   device-key Bearer access does not. HA's library can render without sending,
   but an importer needs explicit deduplication and image-provider setup.
10. WAN-probe failures can enable fallback AP/failover despite a healthy LAN backend.
    Bare `GET /action` defaults to reset and must never be used as a passive probe.
11. Local microphone upload works with an ordinary HTTP sink and empty form fields.
    Its acknowledgment must have no body: firmware mistakes a positive response
    length for an error, even with HTTP 200. Empty acknowledgment reaches finalize.
12. Large's tested poll path rejects untrusted and wrong-host certificates. Standard
    accepted the normal-hostname test chain, but its negative cases remain untested.
13. Standard's blocked public reachability probe caused AP failover and an aborted
    image transfer. A temporary exception restored operation; that exception was
    removed. A custom API URL alone is insufficient for offline operation.

## Current boundary

The owner-scoped investigation recovered the matching stock app and demonstrated
that the frame accepted a test certificate chain for its normal API hostname.
A later standalone server answered real polls and album reads using local data.
Local microphone capture, a separate test-card display and the combined
voice-to-fixed-image protocol/driver sequence also succeeded.
Temporary interception was removed after each bounded experiment. The enclosure
remains closed at the owner's request. **No custom firmware has been flashed and no
custom boot or rollback has been demonstrated.** The application download is not
a full flash backup, and eFuse/bootloader security state remains unknown.

This directory contains documentation and sanitized metadata. It contains no
device key, account token, Wi-Fi password, recordings, signed download URLs,
private certificate material, original firmware binary, or bulk decompilation.
Do not add those artifacts to this repository.

## Maintaining this research

Keep findings tied to the image hash and an address or reproducible observation.
Put contradictory findings and changed behavior in the relevant page, rather than
silently generalizing a result from one frame or firmware to all models. See the
[research method](evidence-and-open-questions.md) before interpreting Ghidra output.
