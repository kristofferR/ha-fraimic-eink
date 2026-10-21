# Voice capture and generation

[Research index](README.md)

## Stock sequence

```mermaid
sequenceDiagram
    participant User
    participant Frame
    participant API as Cloud API / proposed adapter
    participant Store as Upload endpoint
    User->>Frame: Tap, record, tap to stop
    Frame->>API: POST audio/presign (device_key, user_id)
    API-->>Frame: url, key, fields
    Frame->>Store: Multipart POST recording.wav
    Store-->>Frame: HTTP 2xx, empty body
    Frame->>API: POST audio/finalize (key, orientation, identity)
    Note over API: Transcription, generation and panel conversion
    API-->>Frame: HTTP 200 + presigned_url
    Frame->>Store: GET packed panel image
    Frame->>Frame: Render image
```

The HA adapter is proposed. Standalone fixtures have received physical-frame
recordings through local presign and plain HTTP multipart upload. A later test
returned successful finalize JSON and a fixed panel image: the stock client
downloaded it, completed its driver refresh, saved it and returned to ready.
No transcription or image generation was invoked. Because the same test card
was already displayed, the owner could not independently distinguish the second
refresh. See the [combined device result](backend-emulation.md#combined-voiceimage-device-result-c09).

Successful local captures were 4.608, 5.888 and 4.992 seconds, all matching the
format below. The earlier capture-only fixture intentionally returned HTTP 409
at finalize; the final test returned HTTP 200. Both observed valid finalize
requests specified `landscape` orientation.

The separate [Standard 0.2.28 capture](standard-model-comparison.md#poll-and-voice-observations)
completed a real vendor-generated image, confirmed by its owner. Its direct
storage upload returned HTTP 204; finalize omitted `status` and still completed.
This is additional model-scoped evidence for the shared contract, not a local
generation test or proof of every upload status on Large.

## Capture and timing

| Property | Recovered behavior |
| --- | --- |
| Container | RIFF/WAV, 44-byte header |
| Audio | PCM, signed 16-bit, mono, 16,000 Hz |
| Throughput | 32,000 audio bytes/second |
| Buffer capacity exposed to recorder | 2,120,000 bytes, including reserved header |
| Outer recording deadline | 6,000 ticks at 10 ms, approximately 60 seconds |
| Initial button suppression | 200 ticks, approximately two seconds |
| Completion | Single tap after suppression |
| Cancellation | More than two taps in the detected group |
| Deadline without completion | Stop recording and fail; do not upload |

Capture starts at `0x4201fed0`. `0x42010994` checks `voiceRecordingEnabled`,
starts the recording task and waits for completion. `0x42011314` handles the
button/stop/cancel outcomes. `0x420201d4` writes the WAV header in place and returns
the existing buffer. Approximately 1.92 MB of audio fits within 60 seconds; this
is a sizing estimate, not a guarantee of a successfully submitted exact-duration
recording. Silence is not the stock completion signal.

The microphone/image buffer is [shared](hardware-and-layout.md#one-psram-buffer-serves-audio-and-images).
Do not introduce image downloads during recording or reuse that memory before
audio transmission finishes. A separate WAV allocation is not implicit in the
header-generation function.

## Presign

`0x420266d8` sends:

```http
POST /api/v1/upload/audio/presign
Content-Type: application/json
```

```json
{ "device_key": "<device_key>", "user_id": "<user_id>" }
```

Illustrative response:

```json
{
  "url": "https://frame.example/audio/job-123",
  "key": "job-123/recording.wav",
  "fields": { "ticket": "<job-scoped-upload-ticket>" }
}
```

The upload routine `0x42026b9c` builds an ordinary multipart form, copying
string-valued members of `fields` and adding the file field `file`, filename
`recording.wav`. It is not an S3 SDK and does not inherently require S3 storage.
The status check accepts 200–299, but it runs **after a faulty response-length
check**. Return an empty upload response; a successful status alone is insufficient.

Supply a real JSON object for `fields`. An absent field becomes an empty serialized
string and fails the later parse. A real `{}` object was accepted by the physical
frame, which uploaded a valid WAV to an ordinary local HTTP service. No S3 server
or S3-specific form fields were needed. A scoped upload ticket gives the adapter
a useful authorization boundary.

### Upload acknowledgment must have an empty body

The live fixture first returned HTTP 200 with a 15-byte JSON acknowledgment after
successfully storing the WAV. The frame logged `Failed to fetch headers after
streaming upload: ERROR` and did not call finalize.

GNU disassembly identifies the cause: `0x420271f8` calls the header reader at
`0x4206d890`, `0x420271fb` saves the low return word, and `0x42027200` proceeds only
when it is zero. Nonzero results go through `esp_err_to_name` at `0x42027248`.
However, the SDK's
[`esp_http_client_fetch_headers`](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/esp_http_client/include/esp_http_client.h)
returns a body length or a negative error, not an `esp_err_t` success code.
The HTTP status getter at `0x42027276` and 200–299 comparison at `0x420272b0`
come afterward. Thus a valid positive response length is misclassified as failure.

For the local upload sink use HTTP 200 with `Content-Length: 0` and no body.
The follow-up physical recording accepted exactly that response and reached
finalize, confirming the remedy on this build.
This is specific to the multipart upload acknowledgment: presign/finalize JSON
still needs a **positive** explicit length. Missing/chunked length can also yield
zero in the SDK, but those variants have not been validated on this frame and
are unnecessary for the simple empty acknowledgment.

This corrects the earlier claim that any 2xx response suffices. The first Ghidra
export truncated the upload function before this check; live validation exposed
the missing condition.

## Finalize

`0x42027380` sends:

```http
POST /api/v1/upload/audio/finalize
Content-Type: application/json
```

```json
{
  "device_key": "<device_key>",
  "user_id": "<user_id>",
  "key": "job-123/recording.wav",
  "orientation": "landscape"
}
```

This example matches the observed frame request. Portrait orientation was not
exercised in the physical tests above.

A stock-compatible result is HTTP 200 with a ready image URL:

```json
{
  "status": "completed",
  "presigned_url": "https://frame.example/panel/job-123.bin"
}
```

The parser copies `status` if supplied, otherwise defaults to `completed`. It
does not implement a job-status polling protocol. The image URL is required for
this successful path; `202` and a job ID do not queue work on the frame.
Other server fields such as `upload_public_id` do not establish firmware-level
job identity or display confirmation.

The upload worker at `0x42010108` does not inspect the copied status string.
After successful finalize and a cancellation check, it copies only the URL into
the shared result and signals success. GNU instructions at `0x42010428`–
`0x4201044d` confirm that copy/result assignment. A response containing a valid
URL and `status: "processing"` therefore does not implement a waiting state in
this recovered path. This is static evidence; that response variant has not been
sent to the frame. Return a URL only when its complete panel asset is ready.

The Standard live response demonstrated that omission: it contained `success`,
`message`, null `upload_public_id` and `presigned_url`, with no `status`, and the
frame downloaded/rendered the result. Neither its presign nor finalize response
included a transcript or final generation prompt.

The shown two-field response was accepted on the physical frame with an explicit
110-byte body and an ordinary local HTTPS asset URL. No AWS query parameters or
S3 service were needed. Firmware log phrases such as “AI processing” and “raw AWS
presigned URL” describe its fixed workflow labels, not services used by this test.

| Stage | Limit / requirement |
| --- | --- |
| Presign HTTP timeout | 30,000 ms |
| Finalize HTTP timeout | 600,000 ms |
| Outer upload task wait | Approximately 15 minutes |
| Presign/finalize JSON body read | At most 4,095 bytes |
| Copied URL | At most 1,535 bytes plus NUL |
| Copied object key | At most 255 bytes plus NUL |
| Body framing | Explicit positive `Content-Length`; avoid chunked JSON |

Hold finalize until the panel asset is ready. Align reverse-proxy timeouts with
the long request. Persist the job and deduplicate finalize calls so a retry does
not pay for another generation or create duplicate library entries.

## Cancellation and scheduled-content races

The following is a deeper **static** trace of Large 0.2.29, not a completed
physical cancellation test. Two task entries absent from the earlier Ghidra
function list were verified against GNU disassembly and the task-create literals:
`0x42010108` is the presign/upload/finalize worker; `0x420104a8` is the separate
image-download worker. `0x42011adc` orchestrates them and the renderer.

### Gesture and cancellation flag

The button monitor `0x4200f770` runs in recording mode `1` or processing mode `2`.
It ignores additional press edges less than 100 ms apart and groups edges within
800 ms of the first. The third qualifying edge immediately triggers cancellation;
single/double taps do not take that processing-mode branch. These are recovered
thresholds, not measured physical gesture tolerances.

In processing mode it sets the byte at `0x3fca6b19` and calls `0x42025ea8`, the
HTTP-abort manager. The main loop switches to that mode after the recording's
completion indication. For a controlled test, wait until the fixture has received
finalize before cueing the three taps; tapping during the preceding transition
would test a different boundary.

### Which stages can abort their socket

| Stage | Recovered cancellation behavior |
| --- | --- |
| Presign | Registers its client after writing the request, around the response-header wait; unregisters before reading JSON |
| Multipart WAV upload | Registers around acknowledgment-header reading after sending the body; the worker also checks the processing flag when the routine returns, before invoking finalize |
| Finalize | Same registration window as presign: header wait covered; connection setup, request write and subsequent JSON read are outside that window |
| Panel download | Registers after connection opening and remains registered through headers/body; abort flag can produce invalid-state (`0x103`) and end download retries |
| Before rendering | The main flow checks the processing flag after a successful download and skips rendering when set |
| Rendering already started | No processing-flag check was found in the recovered render worker; the orchestration waits for its completion semaphore |

For finalize, the GNU-verified sequence at `0x420275f3` / `0x420275f8` /
`0x420275fd` is register → fetch headers → unregister. Only a negative header
result plus the abort-manager flag takes its explicit aborted return. The upload
worker independently checks the processing flag after each successful stage, so
a cancel arriving as a successful response completes can still prevent the next
stage. It has no retry loop around presign, upload or finalize; the download
worker separately allows up to three attempts for ordinary failures.

The earlier decompiler export omitted the upload routine's acknowledgment tail.
A raw direct-call scan, cross-checked with GNU instructions, found the additional
register/fetch/unregister sequence at `0x420271f3` / `0x420271f8` / `0x420271fd`.
Its nonzero header-result branch checks the abort flag before classifying the
result as an ordinary error. The gap is during WAV transmission, not the entire
upload operation. This is also why the documented response-length bug must be
interpreted alongside cancellation state.

The HTTP manager has **one global client slot**, at `0x3fcabcd0`. Registering
another client logs that it is overwriting an active one; unregistering clears
the slot without comparing an owner/job ID. Its mutex protects slot access, not
an entire workflow. This establishes an ownership limitation, not a reproduced
collision. An emulator should avoid introducing concurrent content producers.

`0x42025ea8` calls the SDK cancellation primitive at `0x4206db7c`, which matches
[ESP-IDF 5.4.1's `esp_http_client_cancel_request`](https://raw.githubusercontent.com/espressif/esp-idf/v5.4.1/components/esp_http_client/esp_http_client.c).
It acts on the transport; it sends no application-level cancellation message.
The wrapper marks its abort flag even when the SDK call fails, and can return
success when no client is registered. Neither that return nor an LED pattern
proves that the backend stopped work.

A server-observed disconnect also cannot distinguish intentional cancellation
from lost Wi-Fi or a client timeout. Keep durable job state and a bounded lifetime;
make finalize idempotent and retain a completed original even if delivery loses
its connection. Explicit cancel/result messages require a firmware extension.
Receiving the WAV alone is not proof the device will call finalize.

### Timeout and error boundaries still needing validation

The 15-minute outer upload wait does not retain an upload-task handle or perform
the explicit abort/join sequence used for download timeout. Its task context and
result pointer refer to the caller's stack. Whether a worker can still access
that state after the timeout is a remaining lifetime question, not a reproduced
crash. Do not use a 15-minute stall on the physical frame as the first experiment.

The download timeout requests HTTP abort, waits another 500 ticks (about five
seconds), then can force-delete its retained task. A cancelled download that
returns an error follows the main flow's generic download-failure branch;
the explicit before-render cancellation branch follows successful download.
Consequently an error indication alone is insufficient to classify cancellation.
Physical timing, cleanup, socket closure, stale-result behavior and every retry
boundary remain open under C07/C08/D05.

### Prepared bounded finalize experiment

A private fixture accepts one local recording and holds finalize for at most
45 seconds. It observes peer disconnect and otherwise returns intentional
HTTP 409. It never returns an image URL, invokes transcription/generation or
offers firmware. Device access requires explicit arming; the host-only run was
unarmed and changed no frame/network configuration.

Five real TLS host checks using a 3,244-byte synthetic silent WAV passed: bounded
delay, terminal result replay after delay, concurrent-finalize rejection, early
peer disconnect, and terminal replay after disconnect. These validate the test
instrument, not stock-frame cancellation. The listener was stopped afterward;
the owner deferred the recording/three-tap test and requested static research.

Fixture SHA-256:
`4df7e41a2c3d3f2ea61ac62e80d7ca79ae46fee48f683f504010d0c7df55c8c7`.

### Scheduled content can interrupt recording

The background poll worker `0x42025aec` can interrupt an active recording when
server work is pending. The backend only learns about the voice job at presign,
after recording ends. Furthermore every poll reports `is_periodic_poll=false`.
A server-side lock beginning at presign cannot protect the earlier recording.

**Proposed firmware additions:** `recording_started`, `recording_stopped`,
`busy`, `cancel_requested`, and `render_complete` events with job/content IDs.
Use one scheduler to arbitrate routine content and voice; protect the shared
buffer at every entry point, including local HTTP uploads.

## Local speech and HA integration

The audio matches the common HA STT input format. A backend can parse the WAV,
invoke configured STT, then route the transcript to existing artwork, dashboard
rendering or image generation. An external Assist client uses WebSocket pipeline
messages and raw PCM, so the Fraimic HTTP upload still needs an adapter. See the
[Assist pipeline protocol](https://contributors.home-assistant.io/core/internals/assist-pipelines/)
and [STT entity formats](https://contributors.home-assistant.io/core/entities/stt/).

### Installed-provider check and WAV boundary

Read-only inspection of the owner's HA 2026.10.2 found Home Assistant Cloud and
Google AI STT. Both advertise 16 kHz, 16-bit mono PCM/WAV and Norwegian Bokmål;
no Wyoming/local STT integration was configured. No recording or transcription
request was sent during this check.

The authenticated HA `/api/stt/<provider>` view validates `X-Speech-Content`
metadata and passes body chunks to the provider. It does not strip a WAV header.
In this exact version, [Google AI STT](https://raw.githubusercontent.com/home-assistant/core/2026.10.2/homeassistant/components/google_generative_ai_conversation/stt.py)
collects the stream and wraps WAV-labeled input as raw PCM. Its
[conversion helper](https://raw.githubusercontent.com/home-assistant/core/2026.10.2/homeassistant/components/google_generative_ai_conversation/helpers.py)
does not detect an existing RIFF header.

A host fixture using that actual helper confirmed that passing a complete WAV
adds another header and treats the original 44 bytes as 22 extra audio samples.
Parse the Fraimic WAV, validate its PCM format and pass PCM to this provider;
do not blindly remove 44 bytes from arbitrary uploaded WAV files. This is a
container-boundary test, not a transcription quality test or proof every STT
provider has the same stream contract. See the [validation record](validation-2026-10-21.md).

Keep generated originals, transcripts, provider/job identity and edit lineage in
the HA library. A local transport can still call hosted AI; fully offline creation
also needs local STT and generation engines. Heavy inference belongs on a capable
server, not the ESP32.

A pure control command currently still needs an image result to follow the stock
success path. Async generation that sleeps while working, no-redraw success,
streaming speech recognition and automatic end-of-speech capture are proposed
protocol/firmware extensions, not existing stock features.
