# Proposed voice protocol extensions

[Research index](README.md) · [HA roadmap](home-assistant-roadmap.md#extension-boundaries) · [Example messages](extension-examples.json)

These are **design examples for future firmware**, not endpoints or features
present on the two stock builds. The compatibility fixture runs eight examples
through the recovered stock finalize parser and checks eighteen proposed policy
properties. It does not implement or validate an extension on a frame.

## Keep the stock contract separate

Keep `/api/v1/` responses unchanged for a client that has not explicitly
negotiated extensions. Stock finalize needs one final HTTP 200 with a ready,
nonempty `presigned_url`, an exact positive Content-Length and a short complete
JSON body. It does not implement a queued job, successful no-image result or
asynchronous status polling. In particular:

| Proposed shortcut | Recovered stock result |
| --- | --- |
| `status: processing` plus a URL | URL is accepted; the status does not defer download |
| `status: failed` plus a URL | URL is still accepted |
| Empty URL for command success | Parser accepts the empty string; it does not become clean no-redraw success |
| Queued job or no-image success without `presigned_url` | Finalize field parser rejects |
| Nested v2 image result | Rejected by the stock parser |
| Capability list added beside a legacy URL | URL parses normally; no negotiation occurs |

The fixture uses HTTP-200 field parsing only; the earlier
[status/framing pass](voice.md#finalize-http-status-framing-and-failure-ordering)
already establishes rejection of HTTP 202 and the synchronous transport rules.
These observations support protocol separation, not attempts to trick an old
client into accepting a new state.

## Negotiation proposal

A future client uses an owner-configured origin and a distinct `/local/v2/`
namespace. An authenticated `hello` advertises supported major versions,
implemented capabilities, a new boot identifier and any persisted pending jobs.
The backend selects a common major and the **intersection** of capabilities,
returning a session identifier. Version 2 is a proposed identifier, not a vendor
version or a claim that version 1 has an existing negotiation mechanism.

The [examples](extension-examples.json) cover `state_events`, `render_result`,
`async_jobs`, `no_image_result`, `pcm_stream` and `vad_stop`. Unknown capabilities
are ignored, unsupported majors are not selected, and an absent hello leaves
the client on the legacy contract. Firmware version strings, a successful TLS
connection and ignored settings keys cannot substitute for negotiation.

Bind the session to an authenticated, enrolled frame. Examples omit transport
credentials; the actual per-frame provisioning mechanism still belongs to
implementation. Never give the frame an HA administrator token. Validate major,
session, job identity, bounded strings and message types before acting. Events
need duplicate/out-of-order handling keyed by boot and sequence; a gap should
trigger state reconciliation, not an invented transition.

Re-negotiate after either peer loses session state. Recover an existing job by
its persisted ID rather than silently replaying a v2 command through the v1
generation path. Any legacy fallback is an explicit client policy before a job
starts; it must not duplicate an action whose outcome is unknown.

## Capability contracts

| Capability | Proposed behavior | Stock fallback / boundary |
| --- | --- | --- |
| State events | Recording start/stop, processing and cancel transitions carry boot/sequence/job identity. `cancel_requested` is distinct from `cancelled`; terminal cancellation requires worker exit and buffer release. | Infer only what stock API requests show. No “recording started” claim from a later presign. |
| Render result | Carry job and content IDs, a driver outcome and separate power-safe state. Deduplicate events and reject stale/wrong-job results. | Label delivery unconfirmed. A served asset, semaphore or maintenance timestamp is insufficient. |
| Async jobs | V2 finalize may return 202 with stable job ID, resume time and expiry. Persist the job before sleeping; resume by that ID and never regenerate merely because a URL expires. | Hold v1 finalize until an image is ready or return a finite error. |
| No-image success | A distinct `command_complete` state with `result.kind: none`; the client returns to ready without downloading or rendering. | Restrict commands to those with a meaningful image result, or report unsupported behavior. Do not resend the current image as “no redraw”. |
| PCM streaming | A negotiated format, bounded ordered chunks and explicit finish; deduplicate identical chunks and reject conflicts/gaps or reconcile a resumable offset. | Accept the completed WAV using the existing presign/upload/finalize flow. |
| VAD stop | Device VAD, or a negotiated live control channel, ends capture with a reason such as `vad_silence`; silence/no-speech is separate from user cancel and maximum duration. | Manual stop or existing firmware timeout; server STT after WAV upload cannot stop earlier capture. |

The render example uses `driver_completed`, deliberately separate from optical
confirmation. It becomes useful only after driver errors are propagated and
completion belongs to the stated content. A failure with unsafe power state must
never be converted into success because the worker exited. The two render records
in the example file illustrate alternative outcomes, not a valid success-then-
failure sequence for one attempt.

Recording events let the backend withhold future scheduled offers. They still
cannot recall a poll response already issued; the frame must arbitrate pending
content before interrupting capture. Job cancellation must not clear another
job's flag or free a buffer used by an old worker. The
[two-job model](voice.md#bounded-two-job-ownership-and-completion-model) explains
why adding event messages alone does not repair ownership.

### Sleeping jobs

The example uses an injected clock, a wake 120 seconds ahead and a later expiry.
Its eligibility check requires the same job ID already persisted, a future wake
with more than 30 seconds of lead and expiry after wake. This preserves the known
stock scheduling margin as a conservative example, not a hardware-tested new
scheduler. Invalid clock, failed persistence or an expired deadline must not
become permission to sleep and forget the job.

At wake, reconcile that job with the backend and choose between ready artwork,
continued waiting, failure, cancellation and expiry. Arbitrate its wake with
playlist and maintenance deadlines. Store the original independently from its
delivery: an expired or cancelled delivery does not require deleting completed
artwork. Firmware/job persistence and the new wake path remain unimplemented.

### Streaming and end-of-speech

The synthetic PCM example is mono signed 16-bit little-endian at 16 kHz. A
32,000-byte chunk represents one second; the illustrative 1,920,000-byte total
limit represents 60 seconds. These are **proposed bounds**, not measurements or
newly discovered stock limits. The finish record declares last sequence, total
bytes and stop reason; real transfer integrity also needs verification against
the received bytes. Do not forward a WAV header as raw PCM.

Streaming needs bounded backpressure, cancellation and an owned recording buffer.
Do not let a poll download reuse Large's shared audio/image allocation while
streaming still owns it. If the connection drops, either retain bounded chunks
for an explicit resume policy or fail that same job. Do not silently start a new
paid STT/generation operation. VAD thresholds, noise behavior and whether streaming
is worth the memory/latency tradeoff need microphone measurements and an owner
feature choice; this research does not choose a provider or enable a command.

## Evidence and remaining work

**26 checks passed:** eight reconstructed stock-parser cases with actual pinned
cJSON under address/undefined-behavior sanitizers, plus eighteen proposed-policy
and message-example assertions. The latter check negotiation intersection,
persist-before-sleep/expired wake, duplicate/stale/wrong-job events, cancellation
ownership declarations, separate render/power outcomes and ordered bounded PCM
examples. They are design consistency checks, not proof of reliable storage,
authenticated transport, event ordering or working VAD.

All six extensions have a legacy boundary and a concrete message/state example.
This completes A06's available design/host milestone. Its device criterion stays
deferred until selected features are implemented and a recovery path exists.
See [validation hashes](validation-2026-10-22.md#extension-negotiation-and-stock-compatibility-a06).
