# Fraimic firmware research

This is an implementation-oriented map of **Fraimic Large firmware 0.2.29,
build f1555ee5**, researched on 21–23 October 2026. It covers the stock application,
its local and cloud protocols, and ways to integrate a custom backend with this
Home Assistant integration. It is not recovered vendor source or a flashing guide.
The [Standard-model comparison](standard-model-comparison.md) separately covers
0.2.28 / 4654a1d8 and its live enrollment/voice capture. Unless labelled otherwise,
addresses and static findings in the original topic pages refer to Large.

## Start here

The [research checklist](research-todo.md) tracks the unknowns and unverified
claims across these documents, with stable task IDs and concrete validation work.
It separates checked evidence milestones from remaining research, implementation,
device tests and recovery prerequisites. The earlier cumulative table is retained
as [pass history](research-progress-2026-10-22.md); the checklist owns current status.
The [static coverage ledger](static-coverage.md) tracks the renewed producer,
initialization and application-census work. Original checklist counts do not
measure how much of the firmware has been analyzed.
The [21 October validation](validation-2026-10-21.md) records owner gallery reads,
installed HA capabilities, five library host checks and deeper firmware traces.
The [22 October continuation](validation-2026-10-22.md) adds HTTP-server lifecycle,
diagnostics, transport/parser and persistence boundaries, task ownership, input,
boot/scheduling and model comparisons. Later instruction cases cover album retry,
late poll publication, task admission and keep-awake across wake contexts. These
static/host passes do not count as device tests.
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
| [TLS durability](tls-durability.md) | Replacement leaves, omitted date checks, confirmed CA revocation, identical roots and firmware-update limits |
| [Schema versus client contract](schema-and-client-contract.md) | July/October schema differences, captured extra fields and limits of generated API models |
| [Image downloads](image-downloads.md) | Length/framing checks, restart-from-zero retries, incomplete images and cache consequences |
| [Voice](voice.md) | Recording, WAV upload, synchronous generation, cancellation, concurrency |
| [Microphone DMA](microphone-dma.md) | Circular buffers, silent queue loss, buffer reuse and allocation-failure boundaries on both builds |
| [Voice and local-control hooks](voice-local-control-hooks.md) | Stock-compatible features, normal recording entry points and firmware hooks for HA controls and no-redraw commands |
| [Physical input and gestures](input-and-gestures.md) | Tap windows, ignored double taps, held-input admission and monitor/result lifetime on both builds |
| [Rendering and concurrency](rendering-and-concurrency.md) | Buffer aliases, upload ordering, render policies, error propagation and completion signals |
| [Boot and scheduling](boot-and-scheduling.md) | Model-specific wake pins, boot classification, recording admission, timers and offline dependencies |
| [Startup and readiness](startup-and-readiness.md) | Early errors, wake-dependent waits, normal/setup worker failures and completion-token limits |
| [Initialization helpers](initialization-helpers.md) | Component retry/cleanup policies, null event-group success and model-specific memory/I2C/GPIO failures |
| [Wi-Fi recovery](wifi-recovery.md) | AP ranking, shared attempt budget, retry-worker ownership and disconnect-reason precedence |
| [Fuel gauge](fuel-gauge.md) | Profile acceptance/programming, sample consistency, model-specific charge presentation and ADC error handling |
| [Application helpers](application-helpers.md) | 130 Large helper roles, repaired decompiler gaps, telemetry presentation and retry-worker limits |
| [Storage and configuration](storage-and-configuration.md) | NVS keys, identity migration, developer mode, image files and persistence |
| [OTA and recovery](ota-and-recovery.md) | Update paths, guards, verification, failure tracking and unresolved recovery questions |
| [Firmware downloader](downloader.md) | Standalone offer check and application download while frames stay blocked from the web |
| [Diagnostics and logs](diagnostics-and-logs.md) | Visibility controls, retention/loss, previous-log storage and redaction limits |
| [Local API](local-api.md) | All 42 registered routes, diagnostics and side effects |
| [Legacy multipart uploads](multipart-uploads.md) | Binary footer parsing, interrupted-body acceptance and HTTP-200 failure pages on both models |
| [LED and workflow state](led-and-workflow-state.md) | 41-state table, priorities, protection latch and limits of visible status |
| [Home Assistant roadmap](home-assistant-roadmap.md) | Existing code to reuse, local cloud design, voice creations and staged experiments |
| [Voice feature proposal](voice-feature-proposal.md) | Creation history, explicit image/target semantics and six playlist/scene API checks |
| [Album/playlist mapping](album-playlist-mapping.md) | Proposed stock-album subset, wake-only records and nineteen isolated mutation checks |
| [Evidence and open questions](evidence-and-open-questions.md) | Confidence, analysis method, address map and research backlog |
| [Static coverage](static-coverage.md) | Supplemental checklist, 936 main-region functions plus sixteen outliers, pointer references and explicit coverage limits |
| [21 October validation](validation-2026-10-21.md) | Reproducible host checks, owner-account/HA observations and their limits |
| [22 October validation](validation-2026-10-22.md) | Transport/parser, storage, task ownership, input/wake and complete poll-body comparisons |
| [Backend emulation](backend-emulation.md) | Physical poll/album, microphone upload and confirmed one-shot panel delivery |
| [Backend deployment](backend-deployment.md) | HA views versus companion listener, actual deployment constraints and 24 isolated boundary checks |
| [Protocol extensions](protocol-extensions.md) | Proposed negotiation, sleeping jobs, no-redraw commands, state events and streaming/VAD boundaries |
| [Standard-model comparison](standard-model-comparison.md) | Model-specific firmware/panel differences, live setup, vendor voice flow and reachability failure |

Machine-readable references: [firmware identity](firmware-identity.json),
[route registrations](route-registrations.json),
[handler contract coverage](route-contract-coverage.json),
[selected addresses](address-map.json), and
[model comparison with type-only live schemas](model-comparison.json).
The [LED state table](led-states.json) preserves the Large build's numeric records.
The [audio-path coverage](audio-output-coverage.json) records model-specific
microphone/LED configuration and the limits of the output-path search.
The [panel-command coverage](panel-command-coverage.json) records fixed command
payloads and the bounded search for partial-update/waveform callers on both models.
The [buffer-memory evaluation](buffer-memory-evaluation.json) compares saved
free/largest-block readings with full-image and maximum-WAV copy requirements.
The [Large](outbound-dependencies.json) and
[Standard](standard-outbound-dependencies.json) outbound dependency inventories
separate client call sites, selectors, dynamic URL sources and non-request URL literals.

Validate documentation links, JSON, checklist counts/statuses and evidence links
with `bun scripts/validate_firmware_docs.mjs` from the repository root. The
[validator](../../scripts/validate_firmware_docs.mjs) accepts an optional repository
path. Research maintainers can set `FRAIMIC_RESEARCH_DEVICE_KEY_FILE` to a private
credential file for an additional exact-match leak check; its contents are never
printed. Completion IDs are derived from the checklist, not frozen in the script.

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
14. The complete poll application bodies match across both models except fallback
    version/model strings. One stock-protocol adapter can share that contract,
    while retaining model-specific assets and external-helper limits.
15. Poll retry is not a delivery receipt. A late result can be cleared while its
    old task blocks retry creation; the starter's check/create guard is not atomic.
    These are scripted instruction findings, not observed concurrent failures.
16. Keep-awake can affect the next ordinary idle check without reboot. Album wake
    follows a separate sleep path, so that setting alone does not establish an
    interactive awake window.
17. Both pinned verifiers omit certificate date checks and attach the same root
    bundle with no CRL. The CA revocation predates successful frame tests.
    [TLS durability](tls-durability.md) separates those findings from future
    firmware changes and still-untested physical fresh-key rotation.

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
