# Fraimic firmware research

This is an implementation-oriented map of **Fraimic Large firmware 0.2.29,
build f1555ee5**, researched on 21 October 2026. It covers the stock application,
its local and cloud protocols, and ways to integrate a custom backend with this
Home Assistant integration. It is not recovered vendor source or a flashing guide.

## Start here

The [research checklist](research-todo.md) tracks the unknowns and unverified
claims across these documents, with stable task IDs and concrete validation work.
The [latest validation pass](validation-2026-10-21.md) records owner gallery reads,
installed HA capabilities, five library host checks and deeper firmware traces.

| Document | Contents |
| --- | --- |
| [Identity and hardware](hardware-and-layout.md) | Exact image fingerprint, memory segments, panel format, wiring and shared buffers |
| [Cloud protocol](cloud-protocol.md) | API selectors, poll response semantics, system screens, transport requirements |
| [Voice](voice.md) | Recording, WAV upload, synchronous generation, cancellation, concurrency |
| [Rendering and concurrency](rendering-and-concurrency.md) | Buffer aliases, upload ordering, render policies, error propagation and completion signals |
| [Boot and scheduling](boot-and-scheduling.md) | Wake reasons, timers, time synchronization, sleep and offline dependencies |
| [Storage and configuration](storage-and-configuration.md) | NVS keys, identity migration, developer mode, image files and persistence |
| [OTA and recovery](ota-and-recovery.md) | Update paths, guards, verification, failure tracking and unresolved recovery questions |
| [Local API](local-api.md) | All 42 registered routes, diagnostics and side effects |
| [Home Assistant roadmap](home-assistant-roadmap.md) | Existing code to reuse, local cloud design, voice creations and staged experiments |
| [Evidence and open questions](evidence-and-open-questions.md) | Confidence, analysis method, address map and research backlog |
| [21 October validation](validation-2026-10-21.md) | Reproducible host checks, owner-account/HA observations and their limits |

Machine-readable references: [firmware identity](firmware-identity.json),
[route registrations](route-registrations.json), and
[selected addresses](address-map.json).

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
   defaults. Missing next-image time in a successful poll clears the saved schedule.
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

## Current boundary

The owner-scoped investigation recovered the matching stock app and demonstrated
that the frame accepted a test certificate chain for its normal API hostname.
Temporary interception was removed. **No custom firmware has been flashed and no
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
