# Voice and local-control hooks

[Research index](README.md) · [Voice transport](voice.md) · [Local API](local-api.md) · [HA reuse](home-assistant-roadmap.md)

The useful stock-firmware path is **tap, speak, receive a locally selected or
rendered image**. The response can be existing artwork, the next playlist item or
a dashboard. The local fixed-card experiment already demonstrated the transport;
speech recognition, intent handling and HA delivery coordination remain to build.
No new recording, provider call or firmware change was performed for this pass.

Remote microphone controls need a firmware extension. This pass maps the normal
voice entry points on both pinned builds and checks the difference between
finishing a request and merely stopping capture. These are research anchors for
the exact applications, not stable APIs or a deployable patch.

## Useful features and their boundaries

| Feature | Stock-compatible behavior | Remaining work |
| --- | --- | --- |
| “Show my calendar” or a configured dashboard | Transcribe completed WAV, render the selected screen, return its panel asset from finalize | Speech/intent adapter, target resolution and render-only delivery coordination |
| “Show the next picture” or select saved artwork | Resolve the frame's queue/library selection and return one frozen panel artifact | Pull delivery that advances the queue once without also pushing the image |
| Voice-created artwork with transcript/prompt/history | Keep recording, transcript, final prompt and original under a backend job ID | Durable job/library integration and the deferred image-provider choice |
| HA command with a meaningful result card | Execute a supported action and render its result | Command policy, deduplication and an intentional artwork-replacement choice |
| HA command preserving the current artwork | No clean stock finalize result | Firmware no-image success branch; empty URL, 204 or a status string is insufficient |
| HA start, finish or cancel for normal voice | No corresponding route in the recovered 42 registrations | Firmware command path into the normal voice lifecycle |
| Allow future voice recordings | Apply `voiceRecordingEnabled` through a complete backend settings snapshot | Backend preference UI and poll delivery; this is not immediate mute or active-job cancellation |
| Automatic end-of-speech | Backend receives WAV only after capture ends | Device VAD, or streaming plus live finish control |
| Spoken response from the frame | No speech-output path identified in either app | Physical output capability remains unestablished |

Dashboard and existing-artwork requests do not need an image-generation provider.
They still need STT for microphone input. The previously inspected HA setup used
cloud STT, so a local backend does not itself establish fully offline speech.
Provider selection remains deferred.

Use the [render-only boundary](home-assistant-roadmap.md#delivery-helpers-have-additional-side-effects)
to prepare a stock voice result. The ordinary render-and-upload helper and scene
send method already dispatch to frames; calling either and then returning the
same image from finalize creates two delivery paths. Keep the original/library
record separate from model-specific panel bytes. Serving an asset does not
confirm physical display.
Standard's optional render counters add aggregate diagnostics, but their
[driver coverage and timing](rendering-and-concurrency.md#standard-counters-cover-the-final-ready-pin-waits)
do not supply a per-job acknowledgment. Preserve a separate backend delivery
state until explicit device-side identity/outcome events exist.

## Normal voice admission

The exact-reference census finds one direct main-loop caller of the recording
wrapper per build. The recording-control task has one initialized function
pointer, loaded by that wrapper. Capture start has one recovered direct caller,
the control task. WAV construction is called from the processing orchestrator,
which also has one recovered main-loop caller. These selected calls/loads and
pointer values were checked against app bytes and complete GNU control-flow maps.

| Boundary | Large 0.2.29 | Standard 0.2.28 |
| --- | --- | --- |
| Idle input admission | `0x4201163c` | `0x4201159c` |
| Recording wrapper | `0x42010994` | `0x420106d0` |
| Main's recording call | `0x42013b99` | `0x42013b19` |
| Recording-control task | `0x42011314` | `0x42011274` |
| Microphone start | `0x4201fed0` | `0x4201fea0` |
| Microphone stop | `0x42020090` | `0x42020060` |
| WAV construction | `0x420201d4` | `0x420201a4` |
| Upload/download/render orchestrator | `0x42011adc` | `0x42011a3c` |
| Main's processing call | `0x42013c15` | `0x42013b95` |

The census does not exclude arbitrary computed calls. Standard's earlier Ghidra
split attributed its main call sites to a fragment at `0x42013a80`; the complete
GNU map places them inside the actual main function at `0x42012770`.

The [factory microphone controls](local-api.md#factory-diagnostic-contract) are
different. `mic_start` launches the statistics worker; `mic_stats` reports block
min/max/amplitude and a factory-active flag. It reuses its sample buffer without
creating a WAV or entering normal upload. `mic_stop` stops that factory worker.
These are not hidden start/finish/download endpoints for a normal voice job.
Ordinary `/api/info` also lacks recording/busy/job state.
The later [microphone ownership audit](local-api.md#factory-and-normal-microphone-capture-can-both-be-admitted)
finds asymmetric admission: factory then normal capture can create two readers
of one I2S channel, and factory stop can return before its worker exits. Keep
factory diagnostics outside the normal voice-command path.
Ordinary taps have an additional [factory-mode admission guard](input-and-gestures.md#factory-mode-guards-idle-admission-not-capture-ownership).
It qualifies the usual page-then-tap sequence, but direct diagnostic POSTs do
not require that mode, and a mode change after the input check is not a capture
reservation. The helper overlap cases remain distinct from physical observation.
The [channel-disable trace](voice.md#channel-disable-is-not-worker-termination)
adds the cleanup boundary: normal voice cleanup does not terminate a factory
worker, and later re-enable can give that existing reader access again. Device
control needs confirmed worker exit as well as channel disable.
The [factory page itself](local-api.md#factory-page-state-does-not-confirm-microphone-ownership)
does not supply that confirmation: it forgets activity on reload, ignores the
statistics `active` flag and resets local state even when stop fails. Its
21/31 requests-per-second idle/microphone intervals are programmed rates,
not a measured traffic or energy baseline. Do not reuse this UI state as a job event.

Existing local controls do not uniformly protect this lifecycle. Standard
0.2.28's refresh endpoint lacks Large's early recording/LED-protection guard;
both builds can enter restart/refresh after a JSON-serialization error response.
The [local-control comparison](local-api.md#standard-refresh-lacks-the-early-busy-guard)
therefore belongs in HA admission/retry design. Withholding cloud image offers
does not arbitrate an independent local refresh request.

## Finish is a workflow operation

The wrapper drains its completion semaphore, launches recording control, then
waits up to 6,000 ticks for completion. The normal single-tap path stops capture,
cleans up the microphone and gives that semaphore. Cancellation additionally
sets its flag. Main enters processing through the wrapper's zero-result branch;
voice enablement remains a separate admission gate.

Four byte-checked instruction cases on **each build** check this relationship:

| Scripted control condition | Completion signal | Wrapper result |
| --- | --- | --- |
| Pending finish, capture active | One | `0`, eligible for processing |
| Pending cancel, capture active | One, with cancellation flag | `0x103`, cancelled |
| Capture inactive at first state check | None | `-1` after modeled outer timeout |
| Capture-start helper fails | One, with failure flag | `-1`, failed |

The inactive branch cleans up and exits its task without signaling completion.
A remote finish operation therefore cannot consist solely of calling microphone
stop: it needs the explicit completion path and result semantics. A factory flag
or LED change does not supply that handoff either.

These eight cases execute the wrapper, control task and monitor-start instructions,
covering **456 distinct instructions per build**. Microphone/task/mutex/semaphore
outcomes are synthetic. The host returns timeout immediately; no real 60-second
wait, audio, scheduling or network operation is measured. See the
[numeric evidence](voice-control-cases.json) and
[validation](validation-2026-10-22.md#voice-and-local-control-hooks-a06h05e01e02).

## Firmware hooks with useful outcomes

### Voice enablement is an admission preference

The stock flag is checked when the outer wrapper admits a new recording. The
settings applicator updates its RAM byte immediately, before saving, but does
not stop capture, signal completion or cancel an upload. Three additional
instruction cases per build verify:

- Disable before admission: no capture task starts, without requiring reboot.
- Disable with a failed NVS save: the next admission is still blocked in RAM;
  persistence across reboot is not established by that result.
- Disable during admitted capture: the ordinary finish still returns success;
  the following admission is blocked. The preference alone does not cancel the
  recording already in progress.

The getter has three recovered callers per build: recording admission, HTML
device information and JSON device information. Exact references to the backing
byte are confined to the getter, settings loader, saver and applicator in this
census. The factory microphone starter does not consult this preference. These
findings support **“allow voice recordings”**, not **“microphone muted”**, as an
HA control label. Neither the flag nor its status response proves an electrical
microphone shutdown.

An emulator can deliver this switch in the next completed poll's full
`device_settings` object; it is not an immediate LAN stop endpoint. Preserve the
other three switches: an incomplete object supplies firmware defaults and can
change unrelated preferences. Backend intent, frame-applied state and durable
state should remain distinct. Sleep/network availability and poll timing still
determine when a backend change reaches the frame.

These cases execute 394 distinct instructions per build using the real applicator,
getter and recording/control paths. The mid-capture change is injected at a
state query, with microphone/task/persistence stubs. It is not a live overlapping
poll test. [Results](voice-preference-cases.json) and
[validation](validation-2026-10-22.md#voice-preference-admission-a06c02h05e01e02)
record the scope. Actual cancellation still needs the separate workflow hook.

### Proposed command and result hooks

These are implementation directions, not enabled features:

1. **A normal voice command path.** Queue authenticated start/finish/cancel
   requests for the lifecycle owner, with request/job identity. Start only while
   awake and eligible; retain voice enablement and display/OTA arbitration.
   Do not call the blocking wrapper from the single HTTP-server task. Physical
   taps and HA requests should share admission logic, with distinct finish and
   cancel outcomes.
2. **Actual workflow state.** Emit recording after capture starts, then stopped,
   processing and terminal outcomes for that job. Supply a current snapshot for
   reconnecting HA clients. This supports listening/working controls and backend
   scheduling holds; device arbitration still handles content already offered.
3. **Successful no-image completion.** Carry a distinct finalize result through
   the upload worker into the orchestrator, skip download/render, and complete
   normally. The current worker discards finalize's status string and keeps only
   the URL, so changing its JSON parser alone cannot do this. Negotiate the
   extension separately from stock clients.

These changes can retain the existing microphone/network/display drivers without
requiring streaming first. No-image completion would let the frame serve as an HA
voice input while preserving its artwork. Later streaming/VAD can reuse the same
finish semantics, with the additional requirements in the
[protocol proposal](protocol-extensions.md).

None remotely wakes deep sleep. Firmware boot acceptance, backup and recovery
remain unresolved; this map is not a flashing procedure.
